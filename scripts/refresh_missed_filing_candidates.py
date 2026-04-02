#!/usr/bin/env python3
"""Build the missed_filing_candidates cache table.

This refresh materializes an exhaustive, statewide 6-digit NAICS cache for the
rolling 24-month product window. Each cached row stores the baseline inputs the
API needs so request-time filtering remains cheap while the cache itself stays
directional and explainable.

The refresh is safe by construction:
- build into a physical stage table
- create secondary indexes only after the stage load finishes
- atomically swap the stage table into place once it is ready
"""

from __future__ import annotations

import logging
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence

_backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import psycopg2
import psycopg2.extras
from psycopg2 import sql

from app.api.analytics import (
    _MISSED_FILING_DEFAULT_MIN_BASELINE_SHARE_PCT,
    _MISSED_FILING_DEFAULT_MIN_EXPECTED_VALUE,
    _MISSED_FILING_DEFAULT_MIN_MISSING_AMOUNT,
    _MISSED_FILING_DEFAULT_MIN_MISSING_PCT,
    _MISSED_FILING_CANDIDATES_DDL,
    _MISSED_FILING_REFRESH_META_DDL,
    _VALID_MISSED_FILING_RUN_RATE_METHODS,
    _missed_filing_default_severity_rank_expression,
    _missed_filing_method_expressions,
    _shift_months,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("missed_filing_refresh")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://munirev:changeme@localhost:5432/munirev",
)

WINDOW_MONTHS = 24
HISTORY_MONTHS = 12
TARGET_TAX_TYPES = ("sales", "use")
LIVE_TABLE = "missed_filing_candidates"
META_TABLE = "missed_filing_candidates_refresh_meta"
LOOKUP_INDEX_NAME = "idx_missed_filing_candidates_lookup"
@dataclass(frozen=True)
class NaicsRow:
    report_date: date
    activity_code: str
    activity_description: str
    sector_total: float


def month_start(value: date) -> date:
    return date(value.year, value.month, 1)


def iter_month_starts(start: date, end: date) -> list[date]:
    current = month_start(start)
    stop = month_start(end)
    output: list[date] = []
    while current <= stop:
        output.append(current)
        current = _shift_months(current, 1)
    return output


def create_table(conn: psycopg2.extensions.connection) -> None:
    with conn.cursor() as cur:
        cur.execute(_MISSED_FILING_CANDIDATES_DDL)
        cur.execute(_MISSED_FILING_REFRESH_META_DDL)
    conn.commit()
    logger.info("Ensured %s and %s exist.", LIVE_TABLE, META_TABLE)


def create_candidate_table(
    conn: psycopg2.extensions.connection,
    table_name: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE {} (
                    id BIGSERIAL PRIMARY KEY,
                    copo VARCHAR(10) NOT NULL,
                    city_name TEXT NOT NULL,
                    tax_type VARCHAR(10) NOT NULL,
                    anomaly_date DATE NOT NULL,
                    activity_code VARCHAR(6) NOT NULL,
                    activity_description TEXT NOT NULL,
                    city_total NUMERIC(14,2) NOT NULL,
                    city_prior_year_total NUMERIC(14,2),
                    city_trailing_mean_3 NUMERIC(14,2),
                    city_trailing_count_3 INTEGER,
                    city_trailing_mean_6 NUMERIC(14,2),
                    city_trailing_count_6 INTEGER,
                    city_trailing_mean_12 NUMERIC(14,2),
                    city_trailing_count_12 INTEGER,
                    city_trailing_median_12 NUMERIC(14,2),
                    city_exp_weighted_avg_12 NUMERIC(14,2),
                    prior_year_value NUMERIC(14,2),
                    trailing_mean_3 NUMERIC(14,2),
                    trailing_count_3 INTEGER,
                    trailing_mean_6 NUMERIC(14,2),
                    trailing_count_6 INTEGER,
                    trailing_mean_12 NUMERIC(14,2),
                    trailing_count_12 INTEGER,
                    trailing_median_12 NUMERIC(14,2),
                    exp_weighted_avg_12 NUMERIC(14,2),
                    hybrid_expected_value NUMERIC(14,2),
                    hybrid_city_expected_total NUMERIC(14,2),
                    hybrid_missing_amount NUMERIC(14,2),
                    hybrid_missing_pct NUMERIC(14,2),
                    hybrid_baseline_share_pct NUMERIC(14,2),
                    hybrid_baseline_months_used INTEGER,
                    actual_value NUMERIC(14,2) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            ).format(sql.Identifier(table_name))
        )
    conn.commit()


def create_refresh_meta_table(
    conn: psycopg2.extensions.connection,
    table_name: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE {} (
                    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                    last_refresh_at TIMESTAMPTZ NOT NULL,
                    data_min_month DATE,
                    data_max_month DATE,
                    snapshot_row_count INTEGER NOT NULL,
                    refresh_duration_seconds NUMERIC(12,2)
                )
                """
            ).format(sql.Identifier(table_name))
        )
    conn.commit()


def create_build_table(
    conn: psycopg2.extensions.connection,
    table_name: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(sql.Identifier(table_name)))
    conn.commit()
    create_candidate_table(conn, table_name)
    logger.info("Prepared stage table %s.", table_name)


def unique_index_name_for(table_name: str) -> str:
    return f"ux_{table_name}_lookup"


def lookup_index_name_for(table_name: str) -> str:
    return f"idx_{table_name}_lookup"


def create_stage_indexes(
    conn: psycopg2.extensions.connection,
    table_name: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE UNIQUE INDEX {} ON {} (copo, tax_type, anomaly_date, activity_code)").format(
                sql.Identifier(unique_index_name_for(table_name)),
                sql.Identifier(table_name),
            )
        )
        cur.execute(
            sql.SQL("CREATE INDEX {} ON {} (anomaly_date DESC, tax_type, copo, activity_code)").format(
                sql.Identifier(lookup_index_name_for(table_name)),
                sql.Identifier(table_name),
            )
        )
        for method in _VALID_MISSED_FILING_RUN_RATE_METHODS:
            method_sql = _missed_filing_method_expressions(method, alias="")
            severity_rank_sql = _missed_filing_default_severity_rank_expression(method, alias="")
            cur.execute(
                sql.SQL(
                    """
                    CREATE INDEX {index_name} ON {table_name} (
                        ({severity_rank}),
                        ({missing_amount}) DESC,
                        anomaly_date DESC,
                        city_name
                    )
                    INCLUDE (id, tax_type)
                    WHERE ({expected}) >= %s
                      AND ({city_expected}) IS NOT NULL
                      AND ({city_expected}) > 0
                      AND ({baseline_months}) > 0
                      AND ({missing_amount}) >= %s
                      AND ({missing_pct}) >= %s
                      AND ({baseline_share}) >= %s
                    """
                ).format(
                    index_name=sql.Identifier(f"idx_{table_name}_{method}_default"),
                    table_name=sql.Identifier(table_name),
                    severity_rank=sql.SQL(severity_rank_sql),
                    expected=sql.SQL(method_sql["expected_raw"]),
                    city_expected=sql.SQL(method_sql["city_expected_raw"]),
                    baseline_months=sql.SQL(method_sql["baseline_months_raw"]),
                    missing_amount=sql.SQL(method_sql["missing_amount_raw"]),
                    missing_pct=sql.SQL(method_sql["missing_pct_raw"]),
                    baseline_share=sql.SQL(method_sql["baseline_share_raw"]),
                ),
                (
                    _MISSED_FILING_DEFAULT_MIN_EXPECTED_VALUE,
                    _MISSED_FILING_DEFAULT_MIN_MISSING_AMOUNT,
                    _MISSED_FILING_DEFAULT_MIN_MISSING_PCT,
                    _MISSED_FILING_DEFAULT_MIN_BASELINE_SHARE_PCT,
                ),
            )
    conn.commit()
    logger.info("Created indexes for stage table %s.", table_name)


def load_ledger_months(
    conn: psycopg2.extensions.connection,
    start_date: date,
    end_date: date,
) -> dict[tuple[str, str], dict[date, tuple[str, float]]]:
    sql_query = """
        SELECT
            lr.copo,
            j.name AS city_name,
            lr.tax_type,
            lr.voucher_date,
            COALESCE(lr.returned, 0)::float8 AS city_total
        FROM ledger_records lr
        JOIN jurisdictions j ON j.copo = lr.copo
        WHERE lr.tax_type = ANY(%s)
          AND lr.voucher_date >= %s
          AND lr.voucher_date <= %s
        ORDER BY lr.copo, lr.tax_type, lr.voucher_date
    """
    data: dict[tuple[str, str], dict[date, tuple[str, float]]] = defaultdict(dict)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql_query, (list(TARGET_TAX_TYPES), start_date, end_date))
        for row in cur.fetchall():
            data[(row["copo"], row["tax_type"])][month_start(row["voucher_date"])] = (
                row["city_name"],
                float(row["city_total"] or 0.0),
            )
    logger.info("Loaded %d city/tax monthly ledger series.", len(data))
    return data


def load_naics_rows(
    conn: psycopg2.extensions.connection,
    copo: str,
    tax_type: str,
    start_year: int,
    end_year: int,
) -> list[NaicsRow]:
    sql_query = """
        SELECT
            make_date(year, month, 1) AS report_date,
            activity_code,
            COALESCE(activity_code_description, activity_code) AS activity_description,
            COALESCE(sector_total, 0)::float8 AS sector_total
        FROM naics_records
        WHERE copo = %s
          AND tax_type = %s
          AND year BETWEEN %s AND %s
          AND activity_code ~ '^[0-9]{6}$'
        ORDER BY year, month, sector_total DESC, activity_code
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql_query, (copo, tax_type, start_year, end_year))
        return [
            NaicsRow(
                report_date=month_start(row["report_date"]),
                activity_code=row["activity_code"],
                activity_description=row["activity_description"],
                sector_total=float(row["sector_total"] or 0.0),
            )
            for row in cur.fetchall()
        ]


def compute_weighted_average(history_values: Sequence[float | None]) -> float | None:
    weighted_sum = 0.0
    weight_total = 0.0
    last_index = len(history_values) - 1
    for idx, amount in enumerate(history_values):
        if amount is None:
            continue
        age = last_index - idx
        weight = 0.75 ** age
        weighted_sum += amount * weight
        weight_total += weight
    if weight_total == 0:
        return None
    return weighted_sum / weight_total


def summarize_history_values(history_values: Sequence[float | None]) -> dict[str, float | int | None]:
    history_3 = [amount for amount in history_values[-3:] if amount is not None]
    history_6 = [amount for amount in history_values[-6:] if amount is not None]
    history_12 = [amount for amount in history_values if amount is not None]

    return {
        "trailing_mean_3": round(sum(history_3) / len(history_3), 2) if history_3 else None,
        "trailing_count_3": len(history_3) or None,
        "trailing_mean_6": round(sum(history_6) / len(history_6), 2) if history_6 else None,
        "trailing_count_6": len(history_6) or None,
        "trailing_mean_12": round(sum(history_12) / len(history_12), 2) if history_12 else None,
        "trailing_count_12": len(history_12) or None,
        "trailing_median_12": round(float(median(history_12)), 2) if history_12 else None,
        "exp_weighted_avg_12": round(compute_weighted_average(history_values), 2) if history_12 else None,
    }


def has_actionable_baseline(
    prior_year_value: float | None,
    stats: dict[str, float | int | None],
) -> bool:
    return (
        prior_year_value is not None
        or (stats["trailing_count_12"] or 0) >= 6
        or (stats["trailing_count_6"] or 0) >= 3
        or (stats["trailing_count_3"] or 0) >= 2
    )


def compute_hybrid_expected(
    *,
    prior_year_value: float | None,
    trailing_mean_3: float | None,
    trailing_count_3: int | None,
    trailing_mean_6: float | None,
    trailing_count_6: int | None,
    trailing_median_12: float | None,
    trailing_count_12: int | None,
) -> tuple[float | None, int]:
    if prior_year_value is not None and (trailing_count_12 or 0) >= 6 and trailing_median_12 is not None:
        return round((prior_year_value * 0.60) + (trailing_median_12 * 0.40), 2), int((trailing_count_12 or 0) + 1)
    if prior_year_value is not None:
        return round(prior_year_value, 2), 1
    if (trailing_count_12 or 0) >= 6 and trailing_median_12 is not None:
        return round(trailing_median_12, 2), int(trailing_count_12 or 0)
    if (trailing_count_6 or 0) >= 3 and trailing_mean_6 is not None:
        return round(trailing_mean_6, 2), int(trailing_count_6 or 0)
    if (trailing_count_3 or 0) >= 2 and trailing_mean_3 is not None:
        return round(trailing_mean_3, 2), int(trailing_count_3 or 0)
    return None, 0


def compute_hybrid_gap_metrics(
    *,
    expected_value: float | None,
    city_expected_total: float | None,
    actual_value: float,
) -> tuple[float | None, float | None, float | None]:
    if expected_value is None:
        return None, None, None

    missing_amount = round(expected_value - actual_value, 2)
    missing_pct = (
        round(((expected_value - actual_value) / abs(expected_value)) * 100, 2)
        if expected_value != 0
        else None
    )
    baseline_share_pct = (
        round(min(100.0, (expected_value / city_expected_total) * 100), 2)
        if city_expected_total not in (None, 0)
        else None
    )
    return missing_amount, missing_pct, baseline_share_pct


def build_candidate_rows(
    ledger_months: dict[date, tuple[str, float]],
    naics_rows: list[NaicsRow],
    target_start: date,
    target_end: date,
) -> list[dict[str, object]]:
    history_start = _shift_months(month_start(target_start), -HISTORY_MONTHS)
    analysis_months = iter_month_starts(history_start, month_start(target_end))
    month_to_index = {report_date: idx for idx, report_date in enumerate(analysis_months)}

    city_series: list[float | None] = [None] * len(analysis_months)
    city_name = ""
    for report_date, (name, city_total) in ledger_months.items():
        idx = month_to_index.get(month_start(report_date))
        if idx is None:
            continue
        city_series[idx] = float(city_total)
        city_name = name

    target_months = [
        report_date
        for report_date in analysis_months
        if target_start <= report_date <= target_end
        and city_series[month_to_index[report_date]] is not None
    ]
    if not target_months:
        return []

    city_stats_by_month: dict[date, dict[str, float | int | None]] = {}
    eligible_target_months: list[date] = []
    for report_date in target_months:
        idx = month_to_index[report_date]
        history_window = city_series[max(0, idx - HISTORY_MONTHS):idx]
        stats = summarize_history_values(history_window)
        city_prior_year_total = city_series[idx - 12] if idx >= 12 else None
        stats["city_prior_year_total"] = round(float(city_prior_year_total), 2) if city_prior_year_total is not None else None
        city_stats_by_month[report_date] = stats
        if has_actionable_baseline(
            float(city_prior_year_total) if city_prior_year_total is not None else None,
            stats,
        ):
            eligible_target_months.append(report_date)

    if not eligible_target_months or not naics_rows:
        return []

    code_series: dict[str, list[float | None]] = {}
    code_description_map: dict[str, str] = {}
    for row in naics_rows:
        report_date = month_start(row.report_date)
        idx = month_to_index.get(report_date)
        if idx is None:
            continue
        series = code_series.setdefault(row.activity_code, [None] * len(analysis_months))
        series[idx] = float(row.sector_total)
        code_description_map[row.activity_code] = row.activity_description or row.activity_code

    output: list[dict[str, object]] = []
    for activity_code, series in code_series.items():
        activity_description = code_description_map.get(activity_code, activity_code)
        for report_date in eligible_target_months:
            idx = month_to_index[report_date]
            prior_year_value = series[idx - 12] if idx >= 12 else None
            history_window = series[max(0, idx - HISTORY_MONTHS):idx]
            stats = summarize_history_values(history_window)

            if not has_actionable_baseline(
                float(prior_year_value) if prior_year_value is not None else None,
                stats,
            ):
                continue

            city_stats = city_stats_by_month[report_date]
            actual_value = float(series[idx]) if series[idx] is not None else 0.0
            city_total = float(city_series[idx] or 0.0)
            hybrid_expected_value, hybrid_baseline_months_used = compute_hybrid_expected(
                prior_year_value=float(prior_year_value) if prior_year_value is not None else None,
                trailing_mean_3=stats["trailing_mean_3"],
                trailing_count_3=stats["trailing_count_3"],
                trailing_mean_6=stats["trailing_mean_6"],
                trailing_count_6=stats["trailing_count_6"],
                trailing_median_12=stats["trailing_median_12"],
                trailing_count_12=stats["trailing_count_12"],
            )
            hybrid_city_expected_total, _ = compute_hybrid_expected(
                prior_year_value=float(city_stats["city_prior_year_total"]) if city_stats["city_prior_year_total"] is not None else None,
                trailing_mean_3=city_stats["trailing_mean_3"],
                trailing_count_3=city_stats["trailing_count_3"],
                trailing_mean_6=city_stats["trailing_mean_6"],
                trailing_count_6=city_stats["trailing_count_6"],
                trailing_median_12=city_stats["trailing_median_12"],
                trailing_count_12=city_stats["trailing_count_12"],
            )
            hybrid_missing_amount, hybrid_missing_pct, hybrid_baseline_share_pct = compute_hybrid_gap_metrics(
                expected_value=hybrid_expected_value,
                city_expected_total=hybrid_city_expected_total,
                actual_value=actual_value,
            )
            output.append(
                {
                    "city_name": city_name,
                    "anomaly_date": report_date,
                    "activity_code": activity_code,
                    "activity_description": activity_description,
                    "city_total": round(city_total, 2),
                    "city_prior_year_total": city_stats["city_prior_year_total"],
                    "city_trailing_mean_3": city_stats["trailing_mean_3"],
                    "city_trailing_count_3": city_stats["trailing_count_3"],
                    "city_trailing_mean_6": city_stats["trailing_mean_6"],
                    "city_trailing_count_6": city_stats["trailing_count_6"],
                    "city_trailing_mean_12": city_stats["trailing_mean_12"],
                    "city_trailing_count_12": city_stats["trailing_count_12"],
                    "city_trailing_median_12": city_stats["trailing_median_12"],
                    "city_exp_weighted_avg_12": city_stats["exp_weighted_avg_12"],
                    "prior_year_value": round(float(prior_year_value), 2) if prior_year_value is not None else None,
                    "trailing_mean_3": stats["trailing_mean_3"],
                    "trailing_count_3": stats["trailing_count_3"],
                    "trailing_mean_6": stats["trailing_mean_6"],
                    "trailing_count_6": stats["trailing_count_6"],
                    "trailing_mean_12": stats["trailing_mean_12"],
                    "trailing_count_12": stats["trailing_count_12"],
                    "trailing_median_12": stats["trailing_median_12"],
                    "exp_weighted_avg_12": stats["exp_weighted_avg_12"],
                    "hybrid_expected_value": hybrid_expected_value,
                    "hybrid_city_expected_total": hybrid_city_expected_total,
                    "hybrid_missing_amount": hybrid_missing_amount,
                    "hybrid_missing_pct": hybrid_missing_pct,
                    "hybrid_baseline_share_pct": hybrid_baseline_share_pct,
                    "hybrid_baseline_months_used": hybrid_baseline_months_used,
                    "actual_value": round(actual_value, 2),
                }
            )

    return output


def insert_candidates(
    conn: psycopg2.extensions.connection,
    table_name: str,
    copo: str,
    tax_type: str,
    rows: list[dict[str, object]],
    snapshot_created_at: datetime,
) -> int:
    if not rows:
        return 0

    payload = [
        (
            copo,
            row["city_name"],
            tax_type,
            row["anomaly_date"],
            row["activity_code"],
            row["activity_description"],
            row["city_total"],
            row["city_prior_year_total"],
            row["city_trailing_mean_3"],
            row["city_trailing_count_3"],
            row["city_trailing_mean_6"],
            row["city_trailing_count_6"],
            row["city_trailing_mean_12"],
            row["city_trailing_count_12"],
            row["city_trailing_median_12"],
            row["city_exp_weighted_avg_12"],
            row["prior_year_value"],
            row["trailing_mean_3"],
            row["trailing_count_3"],
            row["trailing_mean_6"],
            row["trailing_count_6"],
            row["trailing_mean_12"],
            row["trailing_count_12"],
            row["trailing_median_12"],
            row["exp_weighted_avg_12"],
            row["hybrid_expected_value"],
            row["hybrid_city_expected_total"],
            row["hybrid_missing_amount"],
            row["hybrid_missing_pct"],
            row["hybrid_baseline_share_pct"],
            row["hybrid_baseline_months_used"],
            row["actual_value"],
            snapshot_created_at,
        )
        for row in rows
    ]

    sql_query = sql.SQL(
        """
        INSERT INTO {} (
            copo,
            city_name,
            tax_type,
            anomaly_date,
            activity_code,
            activity_description,
            city_total,
            city_prior_year_total,
            city_trailing_mean_3,
            city_trailing_count_3,
            city_trailing_mean_6,
            city_trailing_count_6,
            city_trailing_mean_12,
            city_trailing_count_12,
            city_trailing_median_12,
            city_exp_weighted_avg_12,
            prior_year_value,
            trailing_mean_3,
            trailing_count_3,
            trailing_mean_6,
            trailing_count_6,
            trailing_mean_12,
            trailing_count_12,
            trailing_median_12,
            exp_weighted_avg_12,
            hybrid_expected_value,
            hybrid_city_expected_total,
            hybrid_missing_amount,
            hybrid_missing_pct,
            hybrid_baseline_share_pct,
            hybrid_baseline_months_used,
            actual_value,
            created_at
        ) VALUES %s
        """
    ).format(sql.Identifier(table_name))
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, sql_query.as_string(conn), payload, page_size=2000)
    conn.commit()
    return len(payload)


def publish_stage_table(
    conn: psycopg2.extensions.connection,
    stage_table: str,
    *,
    snapshot_created_at: datetime,
    duration_seconds: float,
    live_table: str = LIVE_TABLE,
    meta_table: str = META_TABLE,
    lookup_index_name: str = LOOKUP_INDEX_NAME,
) -> None:
    previous_table = f"{live_table}_old_{int(snapshot_created_at.timestamp())}"
    stage_lookup_index = lookup_index_name_for(stage_table)

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                "SELECT MIN(anomaly_date), MAX(anomaly_date), COUNT(*) FROM {}"
            ).format(sql.Identifier(stage_table))
        )
        data_min_month, data_max_month, snapshot_row_count = cur.fetchone()

        cur.execute(
            sql.SQL("LOCK TABLE {} IN ACCESS EXCLUSIVE MODE").format(
                sql.Identifier(live_table)
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                sql.Identifier(live_table),
                sql.Identifier(previous_table),
            )
        )
        cur.execute(
            sql.SQL("ALTER TABLE {} RENAME TO {}").format(
                sql.Identifier(stage_table),
                sql.Identifier(live_table),
            )
        )
        cur.execute(
            sql.SQL("DROP TABLE {}").format(sql.Identifier(previous_table))
        )
        cur.execute(
            sql.SQL("ALTER INDEX {} RENAME TO {}").format(
                sql.Identifier(stage_lookup_index),
                sql.Identifier(lookup_index_name),
            )
        )
        cur.execute(
            sql.SQL(
                """
                INSERT INTO {} (
                    singleton,
                    last_refresh_at,
                    data_min_month,
                    data_max_month,
                    snapshot_row_count,
                    refresh_duration_seconds
                ) VALUES (
                    TRUE,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s
                )
                ON CONFLICT (singleton) DO UPDATE SET
                    last_refresh_at = EXCLUDED.last_refresh_at,
                    data_min_month = EXCLUDED.data_min_month,
                    data_max_month = EXCLUDED.data_max_month,
                    snapshot_row_count = EXCLUDED.snapshot_row_count,
                    refresh_duration_seconds = EXCLUDED.refresh_duration_seconds
                """
            ).format(sql.Identifier(meta_table)),
            (
                snapshot_created_at,
                data_min_month,
                data_max_month,
                int(snapshot_row_count or 0),
                round(duration_seconds, 2),
            ),
        )
    conn.commit()


def main() -> None:
    start = time.time()
    today = date.today()
    target_start = _shift_months(today.replace(day=1), -(WINDOW_MONTHS - 1))
    history_start = _shift_months(target_start, -HISTORY_MONTHS)
    snapshot_created_at = datetime.now(timezone.utc)
    stage_table = f"{LIVE_TABLE}_stage_{int(snapshot_created_at.timestamp())}"

    logger.info("Connecting to %s", DATABASE_URL.split("@")[-1])
    conn = psycopg2.connect(DATABASE_URL)

    try:
        create_table(conn)
        create_build_table(conn, stage_table)

        ledger = load_ledger_months(conn, history_start, today)
        total_inserted = 0
        processed = 0

        for (copo, tax_type), monthly_ledger in sorted(ledger.items()):
            naics_rows = load_naics_rows(conn, copo, tax_type, history_start.year, today.year)
            candidate_rows = build_candidate_rows(monthly_ledger, naics_rows, target_start, today)
            total_inserted += insert_candidates(
                conn,
                stage_table,
                copo,
                tax_type,
                candidate_rows,
                snapshot_created_at,
            )
            processed += 1

            if processed % 50 == 0:
                logger.info(
                    "Processed %d/%d city-tax pairs; staged %d rows so far.",
                    processed,
                    len(ledger),
                    total_inserted,
                )

        create_stage_indexes(conn, stage_table)
        publish_stage_table(
            conn,
            stage_table,
            snapshot_created_at=snapshot_created_at,
            duration_seconds=time.time() - start,
        )
        logger.info("Published %d %s rows.", total_inserted, LIVE_TABLE)
    finally:
        conn.close()

    logger.info("Completed in %.1f seconds.", time.time() - start)


if __name__ == "__main__":
    main()
