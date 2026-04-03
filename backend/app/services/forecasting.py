from __future__ import annotations

import hashlib
import json
import math
import warnings
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Iterable, Optional

import numpy as np
import pandas as pd
import psycopg2.extras
from scipy.stats import norm
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from statsmodels.tsa.statespace.sarimax import SARIMAX

try:  # pragma: no cover - optional dependency
    from prophet import Prophet
except ImportError:  # pragma: no cover - optional dependency
    Prophet = None  # type: ignore[assignment]


SUPPORTED_FORECAST_MODELS = ("auto", "baseline", "sarima", "prophet", "ensemble")
SUPPORTED_DRIVER_PROFILES = ("off", "labor", "retail_housing", "balanced")
SUPPORTED_SERIES_SCOPES = ("municipal", "naics")
ADVANCED_HISTORY_REQUIREMENTS = {
    "sales": 36,
    "use": 36,
    "lodging": 24,
}
NAICS_MIN_RECENT_SHARE = 0.01
FORECAST_CACHE_VERSION = 1
MODEL_PRIORITY = {
    "baseline": 0,
    "sarima": 1,
    "prophet": 2,
    "ensemble": 3,
}
OKLAHOMA_STATE_KEY = "OK"


@dataclass
class ModelArtifacts:
    forecast_points: list[dict[str, Any]]
    parameters: dict[str, Any]
    uses_indicators: bool
    indicator_effects: list[dict[str, Any]]


def _json_value(value: Any) -> psycopg2.extras.Json:
    return psycopg2.extras.Json(value, dumps=lambda item: json.dumps(item, default=str))


def ensure_forecast_schema(cur: Any) -> None:
    """Create the forecasting support tables if they do not exist yet."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS forecast_runs (
            id BIGSERIAL PRIMARY KEY,
            copo VARCHAR(10) NOT NULL,
            tax_type VARCHAR(20) NOT NULL,
            activity_code VARCHAR(10),
            series_scope VARCHAR(20) NOT NULL,
            requested_model VARCHAR(20) NOT NULL,
            selected_model VARCHAR(20) NOT NULL,
            horizon_months INTEGER NOT NULL,
            lookback_months INTEGER,
            confidence_level NUMERIC(6,4) NOT NULL,
            indicator_profile VARCHAR(30) NOT NULL,
            training_start DATE,
            training_end DATE,
            feature_set JSONB,
            model_parameters JSONB,
            explanation JSONB,
            data_quality JSONB,
            response_payload JSONB,
            series_signature TEXT,
            cache_version INTEGER NOT NULL DEFAULT 1,
            selected BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "ALTER TABLE forecast_runs ADD COLUMN IF NOT EXISTS response_payload JSONB",
        "ALTER TABLE forecast_runs ADD COLUMN IF NOT EXISTS series_signature TEXT",
        "ALTER TABLE forecast_runs ADD COLUMN IF NOT EXISTS cache_version INTEGER NOT NULL DEFAULT 1",
        """
        CREATE TABLE IF NOT EXISTS forecast_predictions (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            model_type VARCHAR(20) NOT NULL,
            target_date DATE NOT NULL,
            projected_value NUMERIC(15,2) NOT NULL,
            lower_bound NUMERIC(15,2) NOT NULL,
            upper_bound NUMERIC(15,2) NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_backtests (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            model_type VARCHAR(20) NOT NULL,
            mape NUMERIC(10,4),
            smape NUMERIC(10,4),
            mae NUMERIC(15,4),
            rmse NUMERIC(15,4),
            coverage NUMERIC(10,4),
            fold_count INTEGER NOT NULL DEFAULT 0,
            holdout_description TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS economic_indicators (
            id BIGSERIAL PRIMARY KEY,
            geography_type VARCHAR(20) NOT NULL,
            geography_key VARCHAR(80) NOT NULL,
            indicator_family VARCHAR(30) NOT NULL,
            indicator_name VARCHAR(80) NOT NULL,
            period_date DATE NOT NULL,
            value NUMERIC(15,4) NOT NULL,
            source_name VARCHAR(120),
            source_vintage DATE,
            is_forecast BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSONB
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_forecast_runs_lookup ON forecast_runs (copo, tax_type, selected_model, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_forecast_runs_scope ON forecast_runs (activity_code, series_scope, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_forecast_runs_cache_lookup ON forecast_runs (copo, tax_type, activity_code, series_scope, requested_model, horizon_months, lookback_months, confidence_level, indicator_profile, cache_version, series_signature, created_at DESC) WHERE response_payload IS NOT NULL",
        "CREATE INDEX IF NOT EXISTS idx_forecast_predictions_run_model ON forecast_predictions (run_id, model_type, target_date)",
        "CREATE INDEX IF NOT EXISTS idx_forecast_backtests_run_model ON forecast_backtests (run_id, model_type)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_indicators_unique ON economic_indicators (geography_type, geography_key, indicator_family, indicator_name, period_date)",
        "CREATE INDEX IF NOT EXISTS idx_economic_indicators_lookup ON economic_indicators (indicator_family, geography_type, geography_key, period_date)",
    ]

    for statement in statements:
        cur.execute(statement)


def calendarize_series(points: Iterable[tuple[date, float]]) -> pd.Series:
    """Normalize monthly observations to a month-end calendar series."""
    frame = pd.DataFrame(points, columns=["period_date", "value"])
    if frame.empty:
        return pd.Series(dtype=float)

    frame["period_date"] = pd.to_datetime(frame["period_date"]).dt.to_period("M").dt.to_timestamp("M")
    frame["value"] = frame["value"].astype(float)
    series = frame.groupby("period_date")["value"].sum().sort_index()
    full_index = pd.date_range(series.index.min(), series.index.max(), freq="ME")
    return series.reindex(full_index)


def assess_series_quality(
    series: pd.Series,
    tax_type: str,
    *,
    current_period: Optional[pd.Timestamp] = None,
) -> dict[str, Any]:
    """Compute data-quality diagnostics used by model selection and the UI."""
    normalized = series.sort_index()
    observed = normalized.dropna()
    current_period = current_period or pd.Timestamp.now().to_period("M").to_timestamp("M")

    if observed.empty:
        min_history = ADVANCED_HISTORY_REQUIREMENTS.get(tax_type, 36)
        return {
            "observation_count": 0,
            "expected_months": 0,
            "minimum_history_required": min_history,
            "latest_observation": None,
            "stale_months": None,
            "missing_month_count": 0,
            "missing_months": [],
            "has_unresolved_gaps": False,
            "is_sparse_history": True,
            "advanced_models_allowed": False,
            "warnings": ["No historical observations are available for this series."],
        }

    missing_months = [
        ts.strftime("%Y-%m")
        for ts, value in normalized.items()
        if pd.isna(value)
    ]
    min_history = ADVANCED_HISTORY_REQUIREMENTS.get(tax_type, 36)
    latest_observation = observed.index.max()
    stale_months = (
        (current_period.year - latest_observation.year) * 12
        + (current_period.month - latest_observation.month)
    )
    is_sparse = len(observed) < min_history
    has_unresolved_gaps = len(missing_months) > 0
    warnings_list: list[str] = []

    if has_unresolved_gaps:
        sample = ", ".join(missing_months[:6])
        more = "" if len(missing_months) <= 6 else f" (+{len(missing_months) - 6} more)"
        warnings_list.append(
            f"Historical coverage has {len(missing_months)} unresolved month gap(s): {sample}{more}. Advanced models are held back until the missing months are reconciled."
        )
    if stale_months > 1:
        warnings_list.append(
            f"The latest observation is {stale_months} month(s) behind the current reporting period."
        )
    if is_sparse:
        warnings_list.append(
            f"This {tax_type} series has {len(observed)} observed months; advanced models require at least {min_history}."
        )

    return {
        "observation_count": int(len(observed)),
        "expected_months": int(len(normalized)),
        "minimum_history_required": int(min_history),
        "latest_observation": latest_observation.date(),
        "stale_months": int(stale_months),
        "missing_month_count": int(len(missing_months)),
        "missing_months": missing_months,
        "has_unresolved_gaps": has_unresolved_gaps,
        "is_sparse_history": is_sparse,
        "advanced_models_allowed": (not has_unresolved_gaps and not is_sparse and observed.nunique() > 1),
        "warnings": warnings_list,
    }


def build_forecast_package(
    cur: Any,
    *,
    copo: str,
    tax_type: str,
    requested_model: str,
    horizon_months: int,
    lookback_months: Optional[int],
    confidence_level: float,
    indicator_profile: str,
    activity_code: Optional[str] = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Build a municipality or NAICS forecast package with explainability."""
    ensure_forecast_schema(cur)

    scope = "naics" if activity_code else "municipal"
    context = _get_jurisdiction_context(cur, copo)
    series, series_meta = _load_series(cur, copo, tax_type, activity_code)
    if lookback_months:
        series = series.iloc[-lookback_months:]

    if series.dropna().empty:
        empty = _empty_forecast_response(
            copo=copo,
            tax_type=tax_type,
            requested_model=requested_model,
            indicator_profile=indicator_profile,
            series_scope=scope,
            activity_code=activity_code,
        )
        if persist:
            _persist_run(cur, empty, series_signature=_series_signature(series))
        return empty

    filled_series = series.interpolate(limit_direction="both").ffill().bfill()
    quality = assess_series_quality(series, tax_type)
    quality["series_scope"] = scope
    quality["series_start"] = filled_series.index.min().date()
    quality["series_end"] = filled_series.index.max().date()
    quality["activity_code"] = activity_code
    quality["activity_description"] = series_meta.get("activity_description")
    historical_points = _serialize_historical_points(series)
    series_signature = _series_signature(series)

    if scope == "naics":
        share_info = _fetch_naics_share(cur, copo, tax_type, activity_code)
        quality["recent_revenue_share_pct"] = share_info["recent_share_pct"]
        if share_info["recent_share_pct"] is not None and share_info["recent_share_pct"] < NAICS_MIN_RECENT_SHARE * 100:
            quality["advanced_models_allowed"] = False
            quality["warnings"].append(
                f"NAICS series {activity_code} represents only {share_info['recent_share_pct']:.2f}% of the trailing 12-month tax base, so only the baseline fallback is used."
            )

    cached = _load_cached_run(
        cur,
        copo=copo,
        tax_type=tax_type,
        activity_code=activity_code,
        series_scope=scope,
        requested_model=requested_model,
        horizon_months=horizon_months,
        lookback_months=lookback_months,
        confidence_level=confidence_level,
        indicator_profile=indicator_profile,
        series_signature=series_signature,
    )
    if cached is not None:
        cached.setdefault("historical_points", historical_points)
        return cached

    indicator_bundle = _load_indicator_bundle(
        cur,
        copo=copo,
        county_name=context.get("county_name"),
        indicator_profile=indicator_profile,
        index=filled_series.index,
        horizon_months=horizon_months,
    )

    seasonality_summary = _summarize_seasonality(filled_series)
    trend_summary = _summarize_trend(filled_series)
    top_industries = _fetch_top_industry_drivers(cur, copo, tax_type) if scope == "municipal" and tax_type in {"sales", "use"} else []
    candidate_results = _evaluate_models(
        series=series,
        filled_series=filled_series,
        tax_type=tax_type,
        requested_model=requested_model,
        confidence_level=confidence_level,
        horizon_months=horizon_months,
        quality=quality,
        indicator_bundle=indicator_bundle,
    )

    selected_model, selection_reason = _select_model(candidate_results, requested_model)
    selected_result = candidate_results[selected_model]

    for comparison in candidate_results.values():
        comparison["selected"] = comparison["model"] == selected_model

    explainability = _build_explainability(
        selected_result=selected_result,
        candidate_results=candidate_results,
        quality=quality,
        trend_summary=trend_summary,
        seasonality_summary=seasonality_summary,
        selection_reason=selection_reason,
        indicator_bundle=indicator_bundle,
        top_industries=top_industries,
        requested_model=requested_model,
        selected_model=selected_model,
        series_meta=series_meta,
        tax_type=tax_type,
        scope=scope,
        activity_code=activity_code,
    )

    eligible_models = [
        name
        for name, result in candidate_results.items()
        if result["status"] in {"available", "fallback"}
    ]
    forecast_points = selected_result["forecast_points"]
    response = {
        "copo": copo,
        "tax_type": tax_type,
        "model": selected_model,
        "forecasts": forecast_points,
        "selected_model": selected_model,
        "requested_model": requested_model,
        "eligible_models": eligible_models,
        "forecast_points": forecast_points,
        "backtest_summary": selected_result["backtest"],
        "model_comparison": list(candidate_results.values()),
        "explainability": explainability,
        "data_quality": quality,
        "series_scope": scope,
        "activity_code": activity_code,
        "activity_description": series_meta.get("activity_description"),
        "historical_points": historical_points,
        "horizon_months": horizon_months,
        "lookback_months": lookback_months,
        "confidence_level": confidence_level,
        "indicator_profile": indicator_profile,
    }

    if persist:
        response["run_id"] = _persist_run(cur, response, series_signature=series_signature)

    return response


def _get_jurisdiction_context(cur: Any, copo: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT copo, name, jurisdiction_type, county_name
        FROM jurisdictions
        WHERE copo = %s
        """,
        (copo,),
    )
    row = cur.fetchone()
    return dict(row) if row else {"copo": copo, "name": copo, "jurisdiction_type": "city", "county_name": None}


def _load_series(cur: Any, copo: str, tax_type: str, activity_code: Optional[str]) -> tuple[pd.Series, dict[str, Any]]:
    if activity_code:
        cur.execute(
            """
            SELECT
                (make_date(year, month, 1) + INTERVAL '1 month - 1 day')::date AS period_date,
                sector_total AS value,
                MAX(activity_code_description) OVER () AS activity_description
            FROM naics_records
            WHERE copo = %s AND tax_type = %s AND activity_code = %s
            ORDER BY year, month
            """,
            (copo, tax_type, activity_code),
        )
    else:
        cur.execute(
            """
            SELECT voucher_date AS period_date, returned AS value
            FROM ledger_records
            WHERE copo = %s AND tax_type = %s
            ORDER BY voucher_date
            """,
            (copo, tax_type),
        )

    rows = cur.fetchall()
    if not rows:
        return pd.Series(dtype=float), {}

    if activity_code:
        points = [(row["period_date"], float(row["value"])) for row in rows]
        activity_description = rows[0].get("activity_description")
        return calendarize_series(points), {"activity_description": activity_description}

    points = [(row["period_date"], float(row["value"])) for row in rows]
    return calendarize_series(points), {}

def _fetch_naics_share(cur: Any, copo: str, tax_type: str, activity_code: Optional[str]) -> dict[str, Optional[float]]:
    if not activity_code:
        return {"recent_share_pct": None}

    cur.execute(
        """
        WITH last_period AS (
            SELECT MAX(make_date(year, month, 1))::date AS latest_month
            FROM naics_records
            WHERE copo = %s AND tax_type = %s
        )
        SELECT
            SUM(CASE WHEN activity_code = %s THEN sector_total ELSE 0 END) AS activity_total,
            SUM(sector_total) AS total_revenue
        FROM naics_records nr
        CROSS JOIN last_period lp
        WHERE nr.copo = %s
          AND nr.tax_type = %s
          AND make_date(nr.year, nr.month, 1) >= (lp.latest_month - INTERVAL '11 months')
        """,
        (copo, tax_type, activity_code, copo, tax_type),
    )
    row = cur.fetchone()
    if not row or not row["total_revenue"]:
        return {"recent_share_pct": None}
    share = float(row["activity_total"] or 0) / float(row["total_revenue"])
    return {"recent_share_pct": round(share * 100, 2)}


def _serialize_historical_points(series: pd.Series) -> list[dict[str, Any]]:
    observed = series.dropna()
    return [
        {
            "date": pd.Timestamp(timestamp).date(),
            "value": round(float(value), 2),
        }
        for timestamp, value in observed.items()
    ]


def _series_signature(series: pd.Series) -> str:
    normalized = series.sort_index()
    digest = hashlib.sha256()
    for timestamp, value in normalized.items():
        digest.update(pd.Timestamp(timestamp).strftime("%Y-%m-%d").encode("utf-8"))
        digest.update(b"|")
        if pd.isna(value):
            digest.update(b"null")
        else:
            digest.update(f"{float(value):.6f}".encode("utf-8"))
        digest.update(b";")
    return digest.hexdigest()


def _coerce_cached_date(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return value
    return value


def _normalize_cached_points(items: Any, *, date_key: str) -> list[Any]:
    if not isinstance(items, list):
        return []
    normalized: list[Any] = []
    for item in items:
        if isinstance(item, dict):
            cloned = dict(item)
            cloned[date_key] = _coerce_cached_date(cloned.get(date_key))
            normalized.append(cloned)
        else:
            normalized.append(item)
    return normalized


def _normalize_cached_response(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["forecast_points"] = _normalize_cached_points(payload.get("forecast_points", []), date_key="target_date")
    normalized["forecasts"] = _normalize_cached_points(payload.get("forecasts", []), date_key="target_date")
    normalized["historical_points"] = _normalize_cached_points(payload.get("historical_points", []), date_key="date")

    if isinstance(payload.get("data_quality"), dict):
        data_quality = dict(payload["data_quality"])
        for key in ("latest_observation", "series_start", "series_end"):
            data_quality[key] = _coerce_cached_date(data_quality.get(key))
        normalized["data_quality"] = data_quality

    if isinstance(payload.get("model_comparison"), list):
        normalized["model_comparison"] = [
            {
                **item,
                "forecast_points": _normalize_cached_points(item.get("forecast_points", []), date_key="target_date"),
            }
            if isinstance(item, dict)
            else item
            for item in payload["model_comparison"]
        ]

    return normalized


def _load_cached_run(
    cur: Any,
    *,
    copo: str,
    tax_type: str,
    activity_code: Optional[str],
    series_scope: str,
    requested_model: str,
    horizon_months: int,
    lookback_months: Optional[int],
    confidence_level: float,
    indicator_profile: str,
    series_signature: str,
) -> Optional[dict[str, Any]]:
    cur.execute(
        """
        SELECT response_payload
        FROM forecast_runs
        WHERE copo = %s
          AND tax_type = %s
          AND ((activity_code IS NULL AND %s IS NULL) OR activity_code = %s)
          AND series_scope = %s
          AND requested_model = %s
          AND horizon_months = %s
          AND ((lookback_months IS NULL AND %s IS NULL) OR lookback_months = %s)
          AND confidence_level = %s
          AND indicator_profile = %s
          AND cache_version = %s
          AND series_signature = %s
          AND response_payload IS NOT NULL
        ORDER BY created_at DESC, id DESC
        LIMIT 1
        """,
        (
            copo,
            tax_type,
            activity_code,
            activity_code,
            series_scope,
            requested_model,
            horizon_months,
            lookback_months,
            lookback_months,
            confidence_level,
            indicator_profile,
            FORECAST_CACHE_VERSION,
            series_signature,
        ),
    )
    row = cur.fetchone()
    if not row:
        return None
    payload = row.get("response_payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    return _normalize_cached_response(payload) if isinstance(payload, dict) else None


def _fetch_top_industry_drivers(cur: Any, copo: str, tax_type: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        WITH last_period AS (
            SELECT MAX(make_date(year, month, 1))::date AS latest_month
            FROM naics_records
            WHERE copo = %s AND tax_type = %s
        ),
        ranked AS (
            SELECT
                activity_code,
                MAX(activity_code_description) AS activity_description,
                SUM(sector_total) AS trailing_12_total
            FROM naics_records nr
            CROSS JOIN last_period lp
            WHERE nr.copo = %s
              AND nr.tax_type = %s
              AND make_date(nr.year, nr.month, 1) >= (lp.latest_month - INTERVAL '11 months')
            GROUP BY activity_code
        ),
        totals AS (
            SELECT SUM(trailing_12_total) AS grand_total
            FROM ranked
        )
        SELECT
            r.activity_code,
            r.activity_description,
            r.trailing_12_total,
            CASE
                WHEN t.grand_total IS NULL OR t.grand_total = 0 THEN NULL
                ELSE ROUND((r.trailing_12_total / t.grand_total) * 100.0, 2)
            END AS share_pct
        FROM ranked r
        CROSS JOIN totals t
        ORDER BY r.trailing_12_total DESC
        LIMIT 5
        """,
        (copo, tax_type, copo, tax_type),
    )
    rows = cur.fetchall()
    drivers: list[dict[str, Any]] = []
    for row in rows:
        drivers.append(
            {
                "activity_code": row["activity_code"],
                "activity_description": row["activity_description"],
                "share_pct": float(row["share_pct"]) if row["share_pct"] is not None else None,
                "trailing_12_total": round(float(row["trailing_12_total"]), 2),
            }
        )
    return drivers


def _load_indicator_bundle(
    cur: Any,
    *,
    copo: str,
    county_name: Optional[str],
    indicator_profile: str,
    index: pd.DatetimeIndex,
    horizon_months: int,
) -> dict[str, Any]:
    if indicator_profile == "off":
        return {
            "historical_exog": None,
            "future_exog": None,
            "drivers": [],
            "summary": "Driver integration is turned off for this forecast run.",
        }

    requested_families = {
        "labor": ["labor"],
        "retail_housing": ["retail", "housing"],
        "balanced": ["labor", "retail", "housing"],
    }[indicator_profile]

    provenance: list[dict[str, Any]] = []
    rows_by_feature: dict[str, list[dict[str, Any]]] = defaultdict(list)
    # County name in jurisdictions is "Canadian" but economic_indicators
    # stores "Canadian County" — append " County" for the lookup
    county_key = f"{county_name} County" if county_name else None
    fallback_order = [
        ("city", copo),
        ("county", county_key),
        ("state", OKLAHOMA_STATE_KEY),
    ]

    for family in requested_families:
        family_rows: list[dict[str, Any]] = []
        for geography_type, geography_key in fallback_order:
            if not geography_key:
                continue
            cur.execute(
                """
                SELECT
                    geography_type,
                    geography_key,
                    indicator_family,
                    indicator_name,
                    period_date,
                    value,
                    source_name,
                    source_vintage
                FROM economic_indicators
                WHERE geography_type = %s
                  AND geography_key = %s
                  AND indicator_family = %s
                  AND period_date BETWEEN %s AND %s
                ORDER BY period_date
                """,
                (
                    geography_type,
                    geography_key,
                    family,
                    index.min().date(),
                    (index.max() + pd.offsets.MonthEnd(horizon_months)).date(),
                ),
            )
            family_rows = [dict(row) for row in cur.fetchall()]
            if family_rows:
                for row in family_rows:
                    feature_key = f"{family}__{row['indicator_name']}"
                    rows_by_feature[feature_key].append(row)
                provenance.append(
                    {
                        "family": family,
                        "geography_scope": geography_type,
                        "geography_key": geography_key,
                        "source_name": family_rows[-1].get("source_name"),
                        "source_vintage": family_rows[-1].get("source_vintage"),
                    }
                )
                break

    if not rows_by_feature:
        requested_text = ", ".join(requested_families)
        return {
            "historical_exog": None,
            "future_exog": None,
            "drivers": [],
            "summary": f"Driver profile '{indicator_profile}' requested {requested_text} indicators, but no economic_indicators rows were available at city, county, or Oklahoma statewide scope.",
        }

    historical_exog = pd.DataFrame(index=index)
    future_index = pd.date_range(index.max() + pd.offsets.MonthEnd(1), periods=horizon_months, freq="ME")
    future_exog = pd.DataFrame(index=future_index)

    for feature_key, rows in rows_by_feature.items():
        frame = pd.DataFrame(rows)
        frame["period_date"] = pd.to_datetime(frame["period_date"]).dt.to_period("M").dt.to_timestamp("M")
        frame["value"] = frame["value"].astype(float)
        feature_series = frame.groupby("period_date")["value"].last().sort_index()
        aligned = feature_series.reindex(index).ffill().bfill()
        if aligned.isna().all():
            continue
        std = float(aligned.std()) if not math.isnan(float(aligned.std())) else 0.0
        if std == 0:
            scaled = pd.Series(np.zeros(len(aligned)), index=index)
        else:
            scaled = (aligned - aligned.mean()) / std
        historical_exog[feature_key] = scaled
        latest_value = float(scaled.iloc[-1]) if len(scaled) else 0.0
        future_exog[feature_key] = latest_value

    if historical_exog.empty:
        return {
            "historical_exog": None,
            "future_exog": None,
            "drivers": provenance,
            "summary": "Indicator rows were found, but they could not be aligned cleanly to the monthly revenue index.",
        }

    summary_parts = []
    for item in provenance:
        source_name = item["source_name"] or "Unknown source"
        summary_parts.append(f"{item['family']} from {item['geography_scope']} scope ({source_name})")

    return {
        "historical_exog": historical_exog,
        "future_exog": future_exog,
        "drivers": provenance,
        "summary": "Indicator profile uses " + ", ".join(summary_parts) + ". Future exogenous values are held flat at the latest observed level.",
    }


def _evaluate_models(
    *,
    series: pd.Series,
    filled_series: pd.Series,
    tax_type: str,
    requested_model: str,
    confidence_level: float,
    horizon_months: int,
    quality: dict[str, Any],
    indicator_bundle: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    historical_exog = indicator_bundle.get("historical_exog")
    future_exog = indicator_bundle.get("future_exog")

    baseline_artifacts = _fit_baseline_model(filled_series, horizon_months, confidence_level)
    baseline_backtest = _backtest_model(
        "baseline",
        filled_series,
        confidence_level,
        fit_callable=lambda train, steps, conf, train_exog, next_exog: _fit_baseline_model(train, steps, conf),
    )
    candidates["baseline"] = _comparison_payload(
        model="baseline",
        status="available",
        reason="Seasonal trend fallback is always available.",
        artifacts=baseline_artifacts,
        backtest=baseline_backtest,
    )

    if quality["advanced_models_allowed"]:
        sarima_artifacts = _fit_sarima_model(
            filled_series,
            horizon_months,
            confidence_level,
            historical_exog=historical_exog,
            future_exog=future_exog,
        )
        sarima_backtest = _backtest_model(
            "sarima",
            filled_series,
            confidence_level,
            historical_exog=historical_exog,
            fit_callable=lambda train, steps, conf, train_exog, next_exog: _fit_sarima_model(
                train,
                steps,
                conf,
                historical_exog=train_exog,
                future_exog=next_exog,
            ),
        )
        candidates["sarima"] = _comparison_payload(
            model="sarima",
            status="available",
            reason="SARIMA passed the history and data-quality gates.",
            artifacts=sarima_artifacts,
            backtest=sarima_backtest,
        )
    else:
        candidates["sarima"] = _unavailable_payload(
            "sarima",
            "Advanced models are disabled because this series is sparse, stale, or has unresolved month gaps.",
        )

    if Prophet is not None and quality["advanced_models_allowed"]:
        prophet_artifacts = _fit_prophet_model(
            filled_series,
            horizon_months,
            confidence_level,
            historical_exog=historical_exog,
            future_exog=future_exog,
        )
        prophet_backtest = _backtest_model(
            "prophet",
            filled_series,
            confidence_level,
            historical_exog=historical_exog,
            fit_callable=lambda train, steps, conf, train_exog, next_exog: _fit_prophet_model(
                train,
                steps,
                conf,
                historical_exog=train_exog,
                future_exog=next_exog,
            ),
        )
        candidates["prophet"] = _comparison_payload(
            model="prophet",
            status="available",
            reason="Prophet is installed and the series passed advanced-model eligibility.",
            artifacts=prophet_artifacts,
            backtest=prophet_backtest,
        )
    elif Prophet is None:
        candidates["prophet"] = _unavailable_payload(
            "prophet",
            "Prophet is not installed in the current backend environment.",
        )
    else:
        candidates["prophet"] = _unavailable_payload(
            "prophet",
            "Prophet is available but this series did not pass the advanced-model eligibility gates.",
        )

    candidates["ensemble"] = _build_ensemble_payload(candidates)
    return candidates


def _comparison_payload(
    *,
    model: str,
    status: str,
    reason: str,
    artifacts: ModelArtifacts,
    backtest: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "status": status,
        "selected": False,
        "reason": reason,
        "uses_indicators": artifacts.uses_indicators,
        "parameters": artifacts.parameters,
        "forecast_points": artifacts.forecast_points,
        "backtest": backtest,
        "indicator_effects": artifacts.indicator_effects,
        "backtest_points": backtest.get("_points", []),
    }


def _unavailable_payload(model: str, reason: str) -> dict[str, Any]:
    return {
        "model": model,
        "status": "unavailable",
        "selected": False,
        "reason": reason,
        "uses_indicators": False,
        "parameters": {},
        "forecast_points": [],
        "backtest": _empty_backtest(reason),
        "indicator_effects": [],
        "backtest_points": [],
    }


def _build_ensemble_payload(candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    non_baseline_available = [
        item
        for name, item in candidates.items()
        if name in {"sarima", "prophet"} and item["status"] == "available"
    ]

    if len(non_baseline_available) < 2:
        best_single = _best_available_model(candidates)
        return {
            "model": "ensemble",
            "status": "fallback",
            "selected": False,
            "reason": f"Ensemble requires at least two eligible non-baseline models. Falling back to {best_single}.",
            "uses_indicators": candidates[best_single]["uses_indicators"],
            "parameters": {"fallback_model": best_single},
            "forecast_points": candidates[best_single]["forecast_points"],
            "backtest": candidates[best_single]["backtest"],
            "indicator_effects": candidates[best_single]["indicator_effects"],
            "backtest_points": candidates[best_single].get("backtest_points", []),
        }

    weights = _inverse_mape_weights(non_baseline_available)
    combined_points = _blend_forecast_points(non_baseline_available, weights)
    combined_backtest = _blend_backtest_points(non_baseline_available, weights)

    return {
        "model": "ensemble",
        "status": "available",
        "selected": False,
        "reason": "Weighted inverse-MAPE blend of the available non-baseline models.",
        "uses_indicators": any(item["uses_indicators"] for item in non_baseline_available),
        "parameters": {
            "weights": {item["model"]: round(weights[item["model"]], 4) for item in non_baseline_available},
        },
        "forecast_points": combined_points,
        "backtest": combined_backtest,
        "indicator_effects": [
            effect
            for item in non_baseline_available
            for effect in item.get("indicator_effects", [])
        ],
        "backtest_points": combined_backtest.get("_points", []),
    }

def _select_model(candidates: dict[str, dict[str, Any]], requested_model: str) -> tuple[str, str]:
    available = [
        item for item in candidates.values()
        if item["status"] in {"available", "fallback"} and item["forecast_points"]
    ]

    if requested_model != "auto":
        requested = candidates[requested_model]
        if requested["status"] in {"available", "fallback"} and requested["forecast_points"]:
            return requested_model, requested["reason"]
        fallback = _best_available_model(candidates)
        return fallback, f"Requested model '{requested_model}' was unavailable, so the forecast fell back to {fallback}."

    ranked = sorted(
        available,
        key=lambda item: (
            math.inf if item["backtest"]["mape"] is None else item["backtest"]["mape"],
            math.inf if item["backtest"]["smape"] is None else item["backtest"]["smape"],
            math.inf if item["backtest"]["mae"] is None else item["backtest"]["mae"],
            MODEL_PRIORITY.get(item["model"], 99),
        ),
    )
    selected = ranked[0]
    mape = selected["backtest"]["mape"]
    if mape is None:
        return selected["model"], f"Auto mode selected {selected['model']} because comparable backtest metrics were not available."
    return selected["model"], f"Auto mode selected {selected['model']} because it achieved the lowest rolling backtest MAPE ({mape:.2f}%)."


def _best_available_model(candidates: dict[str, dict[str, Any]]) -> str:
    ranked = [
        item for item in candidates.values()
        if item["status"] in {"available", "fallback"} and item["forecast_points"]
    ]
    ranked.sort(
        key=lambda item: (
            math.inf if item["backtest"]["mape"] is None else item["backtest"]["mape"],
            MODEL_PRIORITY.get(item["model"], 99),
        )
    )
    return ranked[0]["model"]


def _fit_baseline_model(series: pd.Series, horizon_months: int, confidence_level: float) -> ModelArtifacts:
    observed = series.dropna().astype(float)
    monthly_buckets: dict[int, list[float]] = {month: [] for month in range(1, 13)}
    for ts, value in observed.items():
        monthly_buckets[ts.month].append(float(value))

    overall_mean = float(observed.mean()) if len(observed) else 0.0
    seasonal_average = {
        month: (float(np.mean(values)) if values else overall_mean)
        for month, values in monthly_buckets.items()
    }

    annual_growth = 1.0
    if len(observed) >= 24:
        recent_total = float(observed.iloc[-12:].sum())
        prior_total = float(observed.iloc[-24:-12].sum())
        if prior_total > 0:
            annual_growth = max(0.75, min(1.25, recent_total / prior_total))

    monthly_growth = annual_growth ** (1 / 12) if annual_growth > 0 else 1.0
    residuals = np.array(
        [
            float(value) - seasonal_average.get(ts.month, overall_mean)
            for ts, value in observed.items()
        ]
    )
    residual_std = float(np.std(residuals)) if len(residuals) else 0.0
    z_value = float(norm.ppf(0.5 + confidence_level / 2))
    latest_date = observed.index.max()
    future_index = pd.date_range(latest_date + pd.offsets.MonthEnd(1), periods=horizon_months, freq="ME")

    points: list[dict[str, Any]] = []
    for step, target in enumerate(future_index, start=1):
        base = seasonal_average.get(target.month, overall_mean)
        projected = max(0.0, base * (monthly_growth ** step))
        margin = z_value * residual_std * math.sqrt(1 + (step / 6))
        points.append(_point_dict(target, projected, max(0.0, projected - margin), projected + margin))

    return ModelArtifacts(
        forecast_points=points,
        parameters={
            "annual_growth_factor": round(float(annual_growth), 4),
            "monthly_growth_factor": round(float(monthly_growth), 6),
            "residual_std": round(float(residual_std), 4),
        },
        uses_indicators=False,
        indicator_effects=[],
    )


def _fit_sarima_model(
    series: pd.Series,
    horizon_months: int,
    confidence_level: float,
    *,
    historical_exog: Optional[pd.DataFrame] = None,
    future_exog: Optional[pd.DataFrame] = None,
) -> ModelArtifacts:
    y = series.astype(float)
    x = historical_exog if historical_exog is not None and not historical_exog.empty else None
    future_x = future_exog if future_exog is not None and x is not None else None

    candidate_orders = [
        ((1, 1, 1), (0, 1, 1, 12)),
        ((0, 1, 1), (0, 1, 1, 12)),
        ((1, 0, 1), (1, 1, 0, 12)),
    ]
    best_fit: Any = None
    best_order: tuple[tuple[int, int, int], tuple[int, int, int, int]] | None = None
    best_aic = math.inf

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        warnings.simplefilter("ignore", category=RuntimeWarning)
        warnings.simplefilter("ignore", category=ConvergenceWarning)
        for order, seasonal_order in candidate_orders:
            try:
                model = SARIMAX(
                    y,
                    exog=x,
                    order=order,
                    seasonal_order=seasonal_order,
                    trend="c",
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                )
                fitted = model.fit(disp=False)
            except Exception:
                continue

            aic = float(getattr(fitted, "aic", math.inf))
            if math.isfinite(aic) and aic < best_aic:
                best_fit = fitted
                best_order = (order, seasonal_order)
                best_aic = aic

    if best_fit is None or best_order is None:
        raise ValueError("SARIMA could not fit the current series.")

    forecast = best_fit.get_forecast(steps=horizon_months, exog=future_x)
    mean = forecast.predicted_mean
    interval = forecast.conf_int(alpha=1 - confidence_level)
    lower = interval.iloc[:, 0]
    upper = interval.iloc[:, 1]

    points = [
        _point_dict(idx, float(pred), float(lo), float(hi))
        for idx, pred, lo, hi in zip(mean.index, mean.tolist(), lower.tolist(), upper.tolist())
    ]
    indicator_effects = _extract_indicator_effects(best_fit, x.columns.tolist() if x is not None else [])

    return ModelArtifacts(
        forecast_points=points,
        parameters={
            "order": list(best_order[0]),
            "seasonal_order": list(best_order[1]),
            "aic": round(best_aic, 4),
        },
        uses_indicators=x is not None,
        indicator_effects=indicator_effects,
    )


def _fit_prophet_model(
    series: pd.Series,
    horizon_months: int,
    confidence_level: float,
    *,
    historical_exog: Optional[pd.DataFrame] = None,
    future_exog: Optional[pd.DataFrame] = None,
) -> ModelArtifacts:
    if Prophet is None:
        raise ValueError("Prophet is not installed.")

    history = pd.DataFrame({"ds": series.index, "y": series.astype(float).values})
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        interval_width=confidence_level,
        holidays=_oklahoma_holidays(int(series.index.min().year), int(series.index.max().year + 2)),
    )

    uses_indicators = historical_exog is not None and not historical_exog.empty
    if uses_indicators and historical_exog is not None:
        for column in historical_exog.columns:
            model.add_regressor(column)
            history[column] = historical_exog[column].values

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=FutureWarning)
        fitted = model.fit(history)

    future = model.make_future_dataframe(periods=horizon_months, freq="ME")
    if uses_indicators and historical_exog is not None and future_exog is not None:
        combined = pd.concat([historical_exog, future_exog]).reset_index(drop=True)
        for column in historical_exog.columns:
            future[column] = combined[column].values[: len(future)]

    forecast = fitted.predict(future).tail(horizon_months)
    points = [
        _point_dict(row.ds, float(row.yhat), float(row.yhat_lower), float(row.yhat_upper))
        for row in forecast.itertuples()
    ]

    indicator_effects: list[dict[str, Any]] = []
    if uses_indicators and historical_exog is not None:
        for column in historical_exog.columns:
            regressor = model.extra_regressors.get(column, {})
            indicator_effects.append(
                {
                    "name": column,
                    "direction": "tracked",
                    "coefficient": None,
                    "prior_scale": regressor.get("prior_scale"),
                }
            )

    return ModelArtifacts(
        forecast_points=points,
        parameters={"holidays": "oklahoma_retail_public_calendar"},
        uses_indicators=uses_indicators,
        indicator_effects=indicator_effects,
    )


def _backtest_model(
    model_name: str,
    series: pd.Series,
    confidence_level: float,
    *,
    fit_callable: Callable[[pd.Series, int, float, Optional[pd.DataFrame], Optional[pd.DataFrame]], ModelArtifacts],
    historical_exog: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    minimum_train = 18
    if len(series) < minimum_train + 3:
        return _empty_backtest("Insufficient history for rolling backtest.")

    folds = min(4, len(series) - minimum_train)
    points: list[dict[str, Any]] = []

    for offset in range(folds, 0, -1):
        train = series.iloc[:-offset]
        actual_index = series.index[-offset]
        actual_value = float(series.iloc[-offset])
        train_exog = historical_exog.iloc[:-offset] if historical_exog is not None else None
        next_exog = historical_exog.iloc[[-offset]] if historical_exog is not None else None

        try:
            artifacts = fit_callable(train, 1, confidence_level, train_exog, next_exog)
        except Exception:
            continue

        if not artifacts.forecast_points:
            continue

        point = dict(artifacts.forecast_points[0])
        point["target_date"] = actual_index.date()
        point["actual_value"] = round(actual_value, 2)
        points.append(point)

    if not points:
        return _empty_backtest(f"{model_name} backtest failed to produce evaluation points.")

    return _metrics_from_points(points, f"Rolling 1-step backtest over {len(points)} fold(s).")


def _metrics_from_points(points: list[dict[str, Any]], holdout_description: str) -> dict[str, Any]:
    actual = np.array([float(point["actual_value"]) for point in points], dtype=float)
    predicted = np.array([float(point["projected_value"]) for point in points], dtype=float)
    lower = np.array([float(point["lower_bound"]) for point in points], dtype=float)
    upper = np.array([float(point["upper_bound"]) for point in points], dtype=float)

    absolute_error = np.abs(actual - predicted)
    non_zero_mask = actual != 0
    mape = (
        float(np.mean((absolute_error[non_zero_mask] / np.abs(actual[non_zero_mask])) * 100))
        if np.any(non_zero_mask)
        else None
    )
    denom = np.abs(actual) + np.abs(predicted)
    smape_mask = denom != 0
    smape = (
        float(np.mean((200 * absolute_error[smape_mask]) / denom[smape_mask]))
        if np.any(smape_mask)
        else None
    )
    mae = float(np.mean(absolute_error))
    rmse = float(np.sqrt(np.mean((actual - predicted) ** 2)))
    coverage = float(np.mean((actual >= lower) & (actual <= upper))) * 100

    return {
        "mape": round(mape, 2) if mape is not None else None,
        "smape": round(smape, 2) if smape is not None else None,
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "coverage": round(coverage, 2),
        "fold_count": len(points),
        "holdout_description": holdout_description,
        "_points": points,
    }


def _empty_backtest(reason: str) -> dict[str, Any]:
    return {
        "mape": None,
        "smape": None,
        "mae": None,
        "rmse": None,
        "coverage": None,
        "fold_count": 0,
        "holdout_description": reason,
        "_points": [],
    }


def _inverse_mape_weights(results: list[dict[str, Any]]) -> dict[str, float]:
    weights: dict[str, float] = {}
    denom = 0.0
    for item in results:
        score = item["backtest"]["mape"]
        inverse = 1.0 / max(float(score or 50.0), 0.01)
        weights[item["model"]] = inverse
        denom += inverse

    return {model: value / denom for model, value in weights.items()}


def _blend_forecast_points(results: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    blended: list[dict[str, Any]] = []
    base_points = results[0]["forecast_points"]
    for idx in range(len(base_points)):
        target_date = base_points[idx]["target_date"]
        projected = sum(weights[item["model"]] * item["forecast_points"][idx]["projected_value"] for item in results)
        lower = sum(weights[item["model"]] * item["forecast_points"][idx]["lower_bound"] for item in results)
        upper = sum(weights[item["model"]] * item["forecast_points"][idx]["upper_bound"] for item in results)
        blended.append(_point_dict(target_date, projected, lower, upper))
    return blended


def _blend_backtest_points(results: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for result in results:
        for point in result.get("backtest_points", []):
            key = str(point["target_date"])
            if key not in grouped:
                grouped[key] = {
                    "target_date": point["target_date"],
                    "actual_value": point["actual_value"],
                    "projected_value": 0.0,
                    "lower_bound": 0.0,
                    "upper_bound": 0.0,
                }
            grouped[key]["projected_value"] += weights[result["model"]] * point["projected_value"]
            grouped[key]["lower_bound"] += weights[result["model"]] * point["lower_bound"]
            grouped[key]["upper_bound"] += weights[result["model"]] * point["upper_bound"]

    points = list(grouped.values())
    points.sort(key=lambda item: item["target_date"])
    return _metrics_from_points(points, f"Weighted inverse-MAPE blend over {len(points)} backtest fold(s).")


def _extract_indicator_effects(fitted: Any, columns: list[str]) -> list[dict[str, Any]]:
    if not columns:
        return []
    params = getattr(fitted, "params", {})
    effects: list[dict[str, Any]] = []
    for column in columns:
        coefficient = float(params.get(column, 0.0))
        direction = "positive" if coefficient > 0 else "negative" if coefficient < 0 else "neutral"
        effects.append(
            {
                "name": column,
                "direction": direction,
                "coefficient": round(coefficient, 4),
            }
        )
    return effects

def _build_explainability(
    *,
    selected_result: dict[str, Any],
    candidate_results: dict[str, dict[str, Any]],
    quality: dict[str, Any],
    trend_summary: str,
    seasonality_summary: str,
    selection_reason: str,
    indicator_bundle: dict[str, Any],
    top_industries: list[dict[str, Any]],
    requested_model: str,
    selected_model: str,
    series_meta: dict[str, Any],
    tax_type: str,
    scope: str,
    activity_code: Optional[str],
) -> dict[str, Any]:
    candidate_metrics = []
    for item in candidate_results.values():
        if item["status"] not in {"available", "fallback"}:
            continue
        mape = item["backtest"]["mape"]
        metric_text = "no MAPE available" if mape is None else f"MAPE {mape:.2f}%"
        candidate_metrics.append(f"{item['model']} ({metric_text})")

    top_industry_share = sum(driver["share_pct"] or 0 for driver in top_industries[:3]) if top_industries else 0
    if scope == "naics":
        industry_mix_summary = (
            f"NAICS scope is focused on activity code {activity_code}. Advanced model eligibility also checks whether the industry is materially represented in the trailing 12-month tax base."
        )
    elif top_industries:
        lead = top_industries[0]
        industry_mix_summary = (
            f"Top municipal industry drivers remain concentrated in a few segments. The top three industries account for {top_industry_share:.2f}% of the trailing 12-month NAICS base, led by {lead['activity_code']} ({lead['activity_description'] or 'Unknown industry'})."
        )
    else:
        industry_mix_summary = "Industry-mix explainability is unavailable for this scope or tax type."

    holiday_summary = (
        "Oklahoma retail/public holiday effects were included via Prophet."
        if selected_model == "prophet"
        else "Holiday effects were not applied in the selected model."
    )
    if Prophet is None:
        holiday_summary = "Holiday effects are available only when Prophet is installed. This run compared baseline/SARIMA paths without Prophet holiday adjustments."

    indicator_summary = indicator_bundle["summary"]
    if selected_result["uses_indicators"] and selected_result["indicator_effects"]:
        strongest = sorted(
            selected_result["indicator_effects"],
            key=lambda item: abs(float(item.get("coefficient", 0) or 0)),
            reverse=True,
        )
        if strongest:
            top_effect = strongest[0]
            indicator_summary += f" Strongest modeled effect: {top_effect['name']} ({top_effect['direction']})."

    caveats = list(quality["warnings"])
    if requested_model != "auto" and requested_model != selected_model:
        caveats.append(f"Requested model '{requested_model}' was not served; the response used '{selected_model}' instead.")

    return {
        "selected_model_reason": selection_reason,
        "model_comparison_summary": " | ".join(candidate_metrics),
        "trend_summary": trend_summary,
        "seasonality_summary": seasonality_summary,
        "holiday_summary": holiday_summary,
        "indicator_summary": indicator_summary,
        "industry_mix_summary": industry_mix_summary,
        "indicator_drivers": indicator_bundle.get("drivers", []),
        "top_industry_drivers": top_industries,
        "activity_description": series_meta.get("activity_description"),
        "data_quality_flags": quality["warnings"],
        "caveats": caveats,
        "confidence_summary": (
            f"Confidence intervals are reported at {int(round(selected_result['backtest'].get('coverage') or 0))}% empirical coverage in backtest and use the requested interval level in the forward model."
        ),
    }


def _summarize_seasonality(series: pd.Series) -> str:
    observed = series.dropna()
    month_means = observed.groupby(observed.index.month).mean()
    if month_means.empty:
        return "No seasonal pattern could be derived from the available history."
    peak_month = int(month_means.idxmax())
    trough_month = int(month_means.idxmin())
    return (
        f"Seasonality peaks in month {peak_month} and softens most in month {trough_month}, based on calendar-month averages across the training window."
    )


def _summarize_trend(series: pd.Series) -> str:
    observed = series.dropna().astype(float)
    if len(observed) < 12:
        return "Less than 12 months of history are available, so long-run trend detection is limited."
    trailing = float(observed.iloc[-12:].sum())
    prior = float(observed.iloc[-24:-12].sum()) if len(observed) >= 24 else None
    if prior and prior != 0:
        pct = ((trailing - prior) / abs(prior)) * 100
        direction = "up" if pct >= 0 else "down"
        return f"Trailing 12-month revenue is {direction} {abs(pct):.2f}% versus the prior 12-month window."
    slope = np.polyfit(np.arange(len(observed)), observed.values, 1)[0]
    direction = "upward" if slope >= 0 else "downward"
    return f"Training history shows a modest {direction} slope of {slope:.2f} revenue units per month."


def _persist_run(cur: Any, payload: dict[str, Any], *, series_signature: Optional[str]) -> int:
    explainability = payload.get("explainability", {})
    comparison = payload.get("model_comparison", [])
    feature_set = {
        "indicator_profile": payload.get("indicator_profile"),
        "series_scope": payload.get("series_scope"),
        "activity_code": payload.get("activity_code"),
        "cache_version": FORECAST_CACHE_VERSION,
    }
    model_parameters = {
        item["model"]: item.get("parameters", {})
        for item in comparison
    }
    data_quality = payload.get("data_quality", {})
    forecast_points = payload.get("forecast_points", payload.get("forecasts", []))

    cur.execute(
        """
        INSERT INTO forecast_runs (
            copo,
            tax_type,
            activity_code,
            series_scope,
            requested_model,
            selected_model,
            horizon_months,
            lookback_months,
            confidence_level,
            indicator_profile,
            training_start,
            training_end,
            feature_set,
            model_parameters,
            explanation,
            data_quality,
            series_signature,
            cache_version
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (
            payload.get("copo"),
            payload.get("tax_type"),
            payload.get("activity_code"),
            payload.get("series_scope"),
            payload.get("requested_model", payload.get("model")),
            payload.get("selected_model", payload.get("model")),
            payload.get("horizon_months", len(forecast_points)),
            payload.get("lookback_months"),
            payload.get("confidence_level", 0.95),
            payload.get("indicator_profile", "off"),
            data_quality.get("series_start"),
            data_quality.get("series_end"),
            _json_value(feature_set),
            _json_value(model_parameters),
            _json_value(explainability),
            _json_value(data_quality),
            series_signature,
            FORECAST_CACHE_VERSION,
        ),
    )
    run_id = int(cur.fetchone()["id"])

    for item in comparison:
        for point in item.get("forecast_points", []):
            cur.execute(
                """
                INSERT INTO forecast_predictions (
                    run_id, model_type, target_date, projected_value, lower_bound, upper_bound
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    run_id,
                    item["model"],
                    point["target_date"],
                    point["projected_value"],
                    point["lower_bound"],
                    point["upper_bound"],
                ),
            )

        backtest = item.get("backtest", {})
        cur.execute(
            """
            INSERT INTO forecast_backtests (
                run_id, model_type, mape, smape, mae, rmse, coverage, fold_count, holdout_description
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                item["model"],
                backtest.get("mape"),
                backtest.get("smape"),
                backtest.get("mae"),
                backtest.get("rmse"),
                backtest.get("coverage"),
                backtest.get("fold_count", 0),
                backtest.get("holdout_description"),
            ),
        )

    persisted_payload = dict(payload)
    persisted_payload["run_id"] = run_id
    cur.execute(
        "UPDATE forecast_runs SET response_payload = %s WHERE id = %s",
        (_json_value(persisted_payload), run_id),
    )

    return run_id


def _point_dict(target_date: Any, projected: float, lower: float, upper: float) -> dict[str, Any]:
    timestamp = pd.Timestamp(target_date)
    projected = max(0.0, float(projected))
    lower = max(0.0, min(projected, float(lower)))
    upper = max(projected, float(upper))
    return {
        "target_date": timestamp.date(),
        "projected_value": round(projected, 2),
        "lower_bound": round(lower, 2),
        "upper_bound": round(upper, 2),
    }


def _empty_forecast_response(
    *,
    copo: str,
    tax_type: str,
    requested_model: str,
    indicator_profile: str,
    series_scope: str,
    activity_code: Optional[str],
) -> dict[str, Any]:
    data_quality = {
        "observation_count": 0,
        "expected_months": 0,
        "minimum_history_required": ADVANCED_HISTORY_REQUIREMENTS.get(tax_type, 36),
        "latest_observation": None,
        "stale_months": None,
        "missing_month_count": 0,
        "missing_months": [],
        "has_unresolved_gaps": False,
        "is_sparse_history": True,
        "advanced_models_allowed": False,
        "warnings": ["No forecast could be generated because the requested series has no observations."],
        "series_scope": series_scope,
        "activity_code": activity_code,
    }
    explainability = {
        "selected_model_reason": "No model could run because the requested series has no observations.",
        "model_comparison_summary": "",
        "trend_summary": "No history available.",
        "seasonality_summary": "No history available.",
        "holiday_summary": "No history available.",
        "indicator_summary": "No history available.",
        "industry_mix_summary": "No history available.",
        "indicator_drivers": [],
        "top_industry_drivers": [],
        "data_quality_flags": data_quality["warnings"],
        "caveats": data_quality["warnings"],
        "confidence_summary": "No forecast intervals were generated.",
    }
    comparison = [_unavailable_payload("baseline", "No observations are available for this series.")]
    return {
        "copo": copo,
        "tax_type": tax_type,
        "model": "baseline",
        "forecasts": [],
        "selected_model": "baseline",
        "requested_model": requested_model,
        "eligible_models": [],
        "forecast_points": [],
        "backtest_summary": _empty_backtest("No observations are available."),
        "model_comparison": comparison,
        "explainability": explainability,
        "data_quality": data_quality,
        "series_scope": series_scope,
        "activity_code": activity_code,
        "activity_description": None,
        "historical_points": [],
        "horizon_months": 0,
        "lookback_months": None,
        "confidence_level": 0.95,
        "indicator_profile": indicator_profile,
    }


def _oklahoma_holidays(start_year: int, end_year: int) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for year in range(start_year, end_year + 1):
        thanksgiving = pd.Timestamp(year=year, month=11, day=1) + pd.offsets.WeekOfMonth(week=3, weekday=3)
        memorial = pd.Timestamp(year=year, month=5, day=31) - pd.offsets.Week(weekday=0)
        labor = pd.Timestamp(year=year, month=9, day=1) + pd.offsets.Week(weekday=0)
        for holiday_name, holiday_date in (
            ("new_years_day", pd.Timestamp(year=year, month=1, day=1)),
            ("memorial_day", memorial),
            ("independence_day", pd.Timestamp(year=year, month=7, day=4)),
            ("labor_day", labor),
            ("thanksgiving", thanksgiving),
            ("christmas_day", pd.Timestamp(year=year, month=12, day=25)),
        ):
            records.append({"holiday": holiday_name, "ds": holiday_date})
    return pd.DataFrame(records)
