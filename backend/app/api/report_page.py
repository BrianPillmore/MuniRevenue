"""Monthly report page API — single jurisdiction, single month.

Endpoint: GET /api/report/{copo}/{year}/{month}

Returns all data needed to render the /report/:copo/:year/:month page in one
round-trip: city metadata, revenue by tax type, forecast, missed filings,
anomalies, NAICS top-10 industries, and a 12-month trend series.

Authentication: requires a valid session (same as /forecast, /anomalies, etc.).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel

from app.db.psycopg import get_cursor
from app.user_auth import require_feature_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["report"])

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TaxTypeRevenue(BaseModel):
    tax_type: str
    actual: Optional[float]
    forecast: Optional[float]
    prior_year_actual: Optional[float]


class MissedFilingRow(BaseModel):
    activity_code: str
    activity_description: Optional[str]
    anomaly_date: str
    estimated_monthly_value: float
    expected_value: float
    actual_value: float
    missing_amount: float
    missing_pct: float
    severity: str


class AnomalyRow(BaseModel):
    tax_type: str
    anomaly_type: str
    expected_value: Optional[float]
    actual_value: Optional[float]
    deviation_pct: float
    severity: str
    description: str


class NaicsIndustryRow(BaseModel):
    activity_code: str
    activity_description: Optional[str]
    current_month: float
    prior_year_month: Optional[float]
    yoy_pct: Optional[float]


class TrendPoint(BaseModel):
    year: int
    month: int
    actual: float
    forecast: Optional[float]


class YoyRow(BaseModel):
    tax_type: str
    current_year: Optional[float]
    prior_year: Optional[float]
    yoy_pct: Optional[float]


class MonthlyReportResponse(BaseModel):
    copo: str
    city_name: str
    jurisdiction_type: str
    county_name: Optional[str]
    population: Optional[int]
    year: int
    month: int
    period_label: str
    tax_types: list[str]
    revenue_by_tax_type: list[TaxTypeRevenue]
    missed_filings: list[MissedFilingRow]
    missed_filing_count: int
    anomalies: list[AnomalyRow]
    anomaly_count: int
    naics_top_industries: list[NaicsIndustryRow]
    trend_12mo: list[TrendPoint]
    yoy_by_tax_type: list[YoyRow]
    latest_data_date: Optional[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _period_label(year: int, month: int) -> str:
    return f"{_MONTH_NAMES[month - 1]} {year}"


def _fetch_city_info(cur, copo: str) -> dict | None:
    cur.execute(
        """
        SELECT
            copo,
            name,
            jurisdiction_type,
            county_name,
            population
        FROM jurisdictions
        WHERE copo = %s
        LIMIT 1
        """,
        [copo],
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _fetch_tax_types(cur, copo: str) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT tax_type
        FROM ledger_records
        WHERE copo = %s
        ORDER BY tax_type
        """,
        [copo],
    )
    return [row["tax_type"] for row in cur.fetchall()]


def _fetch_actual_by_tax_type(cur, copo: str, year: int, month: int) -> dict[str, float]:
    cur.execute(
        """
        SELECT tax_type, SUM(returned)::float8 AS total
        FROM ledger_records
        WHERE copo = %s
          AND EXTRACT(YEAR  FROM voucher_date) = %s
          AND EXTRACT(MONTH FROM voucher_date) = %s
        GROUP BY tax_type
        """,
        [copo, year, month],
    )
    return {row["tax_type"]: float(row["total"]) for row in cur.fetchall() if row["total"] is not None}


def _fetch_forecast_by_tax_type(cur, copo: str, year: int, month: int) -> dict[str, float]:
    """Get the most recent selected forecast for each tax type for the given period."""
    period_date = date(year, month, 1)
    cur.execute(
        """
        SELECT DISTINCT ON (fr.tax_type)
            fr.tax_type,
            fp.projected_value::float8
        FROM forecast_predictions fp
        JOIN forecast_runs fr ON fr.id = fp.run_id
        WHERE fr.copo = %s
          AND fr.selected = TRUE
          AND fp.target_date = %s
        ORDER BY fr.tax_type, fr.created_at DESC
        """,
        [copo, period_date],
    )
    return {
        row["tax_type"]: float(row["projected_value"])
        for row in cur.fetchall()
        if row["projected_value"] is not None
    }


def _fetch_prior_year_by_tax_type(cur, copo: str, year: int, month: int) -> dict[str, float]:
    cur.execute(
        """
        SELECT tax_type, SUM(returned)::float8 AS total
        FROM ledger_records
        WHERE copo = %s
          AND EXTRACT(YEAR  FROM voucher_date) = %s
          AND EXTRACT(MONTH FROM voucher_date) = %s
        GROUP BY tax_type
        """,
        [copo, year - 1, month],
    )
    return {row["tax_type"]: float(row["total"]) for row in cur.fetchall() if row["total"] is not None}


def _fetch_missed_filings(cur, copo: str, year: int, month: int) -> list[dict]:
    period_date = date(year, month, 1)
    try:
        cur.execute(
            """
            SELECT
                activity_code,
                activity_description,
                anomaly_date::text,
                COALESCE(hybrid_expected_value, trailing_median_12, trailing_mean_12, prior_year_value)
                    AS estimated_monthly_value,
                COALESCE(hybrid_expected_value, trailing_median_12, trailing_mean_12, prior_year_value)
                    AS expected_value,
                actual_value,
                COALESCE(hybrid_missing_amount,
                    COALESCE(hybrid_expected_value, trailing_median_12, trailing_mean_12, prior_year_value)
                    - actual_value
                )                     AS missing_amount,
                COALESCE(hybrid_missing_pct, 0)  AS missing_pct,
                CASE
                    WHEN COALESCE(hybrid_missing_amount, 0) >= 25000 THEN 'critical'
                    WHEN COALESCE(hybrid_missing_amount, 0) >= 10000 THEN 'high'
                    ELSE 'medium'
                END                   AS severity
            FROM missed_filing_candidates
            WHERE copo = %s
              AND anomaly_date = %s
              AND COALESCE(hybrid_missing_amount, 0) > 0
            ORDER BY
                CASE
                    WHEN COALESCE(hybrid_missing_amount, 0) >= 25000 THEN 1
                    WHEN COALESCE(hybrid_missing_amount, 0) >= 10000 THEN 2
                    ELSE 3
                END,
                COALESCE(hybrid_missing_amount, 0) DESC
            LIMIT 20
            """,
            [copo, period_date],
        )
        return [dict(row) for row in cur.fetchall()]
    except Exception:
        cur.connection.rollback()
        return []


def _fetch_anomalies(cur, copo: str, year: int, month: int) -> list[dict]:
    period_date = date(year, month, 1)
    try:
        cur.execute(
            """
            SELECT
                tax_type,
                anomaly_type,
                expected_value::float8,
                actual_value::float8,
                deviation_pct::float8,
                severity,
                description
            FROM anomalies
            WHERE copo = %s
              AND anomaly_date = %s
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    ELSE 3
                END,
                ABS(deviation_pct) DESC
            LIMIT 10
            """,
            [copo, period_date],
        )
        return [dict(row) for row in cur.fetchall()]
    except Exception:
        cur.connection.rollback()
        return []


def _fetch_naics_top(cur, copo: str, year: int, month: int) -> list[dict]:
    """Top 10 NAICS industries for the month with prior-year comparison."""
    cur.execute(
        """
        WITH cur_month AS (
            SELECT
                n.activity_code,
                nc.description      AS activity_description,
                SUM(n.sector_total)::float8 AS total
            FROM naics_records n
            JOIN naics_codes nc ON nc.activity_code = n.activity_code
            WHERE n.copo = %s
              AND n.tax_type = 'sales'
              AND n.year = %s
              AND n.month = %s
            GROUP BY n.activity_code, nc.description
        ),
        prior_year AS (
            SELECT
                n.activity_code,
                SUM(n.sector_total)::float8 AS total
            FROM naics_records n
            WHERE n.copo = %s
              AND n.tax_type = 'sales'
              AND n.year = %s
              AND n.month = %s
            GROUP BY n.activity_code
        )
        SELECT
            c.activity_code,
            c.activity_description,
            c.total                AS current_month,
            p.total                AS prior_year_month,
            CASE WHEN p.total > 0
                 THEN ROUND(((c.total - p.total) / p.total * 100)::numeric, 1)::float8
            END                    AS yoy_pct
        FROM cur_month c
        LEFT JOIN prior_year p ON p.activity_code = c.activity_code
        ORDER BY c.total DESC
        LIMIT 10
        """,
        [copo, year, month, copo, year - 1, month],
    )
    return [dict(row) for row in cur.fetchall()]


def _fetch_trend_12mo(cur, copo: str, year: int, month: int) -> list[dict]:
    """12-month actuals + forecasts ending at (year, month)."""
    # Go back 11 more months
    if month > 11:
        start_year, start_month = year, month - 11
    else:
        start_year = year - 1
        start_month = month + 1  # e.g. month=3 → start 4 of prior year

    # Use first-of-next-month as exclusive upper bound so mid-month voucher
    # dates (e.g. 2026-03-09) are included for the end month.
    if month == 12:
        upper_bound = date(year + 1, 1, 1)
    else:
        upper_bound = date(year, month + 1, 1)

    cur.execute(
        """
        SELECT
            EXTRACT(YEAR  FROM voucher_date)::int AS year,
            EXTRACT(MONTH FROM voucher_date)::int AS month,
            SUM(returned)::float8 AS actual
        FROM ledger_records
        WHERE copo = %s
          AND tax_type = 'sales'
          AND voucher_date >= %s
          AND voucher_date < %s
        GROUP BY year, month
        ORDER BY year, month
        """,
        [copo, date(start_year, start_month, 1), upper_bound],
    )
    actuals = {(row["year"], row["month"]): float(row["actual"]) for row in cur.fetchall()}

    # Grab forecasts for all 12 months if available
    months_dates = []
    y, m = start_year, start_month
    while (y, m) <= (year, month):
        months_dates.append(date(y, m, 1))
        m += 1
        if m > 12:
            m = 1
            y += 1

    forecasts: dict[tuple[int, int], float] = {}
    if months_dates:
        cur.execute(
            """
            SELECT DISTINCT ON (fp.target_date)
                EXTRACT(YEAR  FROM fp.target_date)::int AS year,
                EXTRACT(MONTH FROM fp.target_date)::int AS month,
                fp.projected_value::float8
            FROM forecast_predictions fp
            JOIN forecast_runs fr ON fr.id = fp.run_id
            WHERE fr.copo = %s
              AND fr.tax_type = 'sales'
              AND fr.selected = TRUE
              AND fp.target_date = ANY(%s)
            ORDER BY fp.target_date, fr.created_at DESC
            """,
            [copo, months_dates],
        )
        for row in cur.fetchall():
            k = (int(row["year"]), int(row["month"]))
            if row["projected_value"] is not None:
                forecasts[k] = float(row["projected_value"])

    result = []
    for d in months_dates:
        k = (d.year, d.month)
        actual = actuals.get(k)
        if actual is not None:
            result.append({
                "year": d.year,
                "month": d.month,
                "actual": actual,
                "forecast": forecasts.get(k),
            })

    return result


def _fetch_latest_data_date(cur, copo: str) -> str | None:
    cur.execute(
        """
        SELECT MAX(voucher_date)::text AS latest
        FROM ledger_records
        WHERE copo = %s
        """,
        [copo],
    )
    row = cur.fetchone()
    return row["latest"] if row else None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.get("/report/{copo}/{year}/{month}", response_model=MonthlyReportResponse)
def get_monthly_report(
    copo: str = Path(..., description="Jurisdiction COPO code"),
    year: int = Path(..., ge=2000, le=2100),
    month: int = Path(..., ge=1, le=12),
    _session=Depends(require_feature_access),
) -> MonthlyReportResponse:
    """Return all data needed for the monthly report page for one city and month."""
    with get_cursor() as cur:
        city = _fetch_city_info(cur, copo)

    if not city:
        raise HTTPException(status_code=404, detail=f"Jurisdiction '{copo}' not found.")

    with get_cursor() as cur:
        tax_types = _fetch_tax_types(cur, copo)

    if not tax_types:
        raise HTTPException(
            status_code=404,
            detail=f"No ledger data found for '{copo}'.",
        )

    with get_cursor() as cur:
        actual_by_type = _fetch_actual_by_tax_type(cur, copo, year, month)
        forecast_by_type = _fetch_forecast_by_tax_type(cur, copo, year, month)
        prior_year_by_type = _fetch_prior_year_by_tax_type(cur, copo, year, month)

    revenue_by_tax_type = []
    for tt in tax_types:
        actual = actual_by_type.get(tt)
        revenue_by_tax_type.append(
            TaxTypeRevenue(
                tax_type=tt,
                actual=actual,
                forecast=forecast_by_type.get(tt),
                prior_year_actual=prior_year_by_type.get(tt),
            )
        )

    with get_cursor() as cur:
        missed_rows = _fetch_missed_filings(cur, copo, year, month)
        anomaly_rows = _fetch_anomalies(cur, copo, year, month)
        naics_rows = _fetch_naics_top(cur, copo, year, month)
        trend_rows = _fetch_trend_12mo(cur, copo, year, month)
        latest_date = _fetch_latest_data_date(cur, copo)

    yoy_by_tax_type = []
    for tt in tax_types:
        current = actual_by_type.get(tt)
        prior = prior_year_by_type.get(tt)
        yoy_pct: float | None = None
        if current is not None and prior is not None and prior != 0:
            yoy_pct = round((current - prior) / abs(prior) * 100, 1)
        yoy_by_tax_type.append(
            YoyRow(tax_type=tt, current_year=current, prior_year=prior, yoy_pct=yoy_pct)
        )

    return MonthlyReportResponse(
        copo=copo,
        city_name=city["name"],
        jurisdiction_type=city["jurisdiction_type"],
        county_name=city.get("county_name"),
        population=city.get("population"),
        year=year,
        month=month,
        period_label=_period_label(year, month),
        tax_types=tax_types,
        revenue_by_tax_type=revenue_by_tax_type,
        missed_filings=[MissedFilingRow(**r) for r in missed_rows],
        missed_filing_count=len(missed_rows),
        anomalies=[AnomalyRow(**r) for r in anomaly_rows],
        anomaly_count=len(anomaly_rows),
        naics_top_industries=[NaicsIndustryRow(**r) for r in naics_rows],
        trend_12mo=[TrendPoint(**r) for r in trend_rows],
        yoy_by_tax_type=yoy_by_tax_type,
        latest_data_date=latest_date,
    )
