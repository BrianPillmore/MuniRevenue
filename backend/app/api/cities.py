"""City / jurisdiction query endpoints for the MuniRev database.

This router must be registered in ``app.main``:

    from app.api.cities import router as cities_router
    app.include_router(cities_router)

All queries use psycopg2 with parameterized statements to prevent
SQL injection.  No ORM -- just plain SQL for full control over the
analytics queries.
"""

from __future__ import annotations

import calendar
import csv
import io
import logging
import os
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Iterator, Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.security import require_scopes
from app.services.forecasting import (
    SUPPORTED_DRIVER_PROFILES,
    SUPPORTED_FORECAST_MODELS,
    build_forecast_package,
)

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://munirev:changeme@localhost:5432/munirev",
)

router = APIRouter(
    prefix="/api",
    tags=["cities"],
    dependencies=[Depends(require_scopes("api:read"))],
)


# ---------------------------------------------------------------------------
# Database helper
# ---------------------------------------------------------------------------

def get_conn() -> psycopg2.extensions.connection:
    """Return a new psycopg2 connection.

    Caller is responsible for closing the connection when finished.
    """
    return psycopg2.connect(DATABASE_URL)


@contextmanager
def get_cursor(
    *, dict_cursor: bool = True
) -> Iterator[psycopg2.extensions.cursor]:
    """Context manager that yields a cursor and handles commit/rollback.

    Uses ``RealDictCursor`` by default so rows come back as dicts.
    """
    conn = get_conn()
    try:
        cursor_factory = (
            psycopg2.extras.RealDictCursor if dict_cursor else None
        )
        cur = conn.cursor(cursor_factory=cursor_factory)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class JurisdictionListItem(BaseModel):
    copo: str
    name: str
    jurisdiction_type: str
    county_name: Optional[str] = None
    population: Optional[int] = None
    has_ledger_data: bool
    latest_voucher_date: Optional[date] = None
    total_sales_returned: Optional[float] = None


class JurisdictionListResponse(BaseModel):
    items: list[JurisdictionListItem]
    total: int
    limit: int
    offset: int


class TaxTypeSummary(BaseModel):
    tax_type: str
    record_count: int
    earliest_date: Optional[date] = None
    latest_date: Optional[date] = None
    total_returned: Optional[float] = None


class JurisdictionDetail(BaseModel):
    copo: str
    name: str
    jurisdiction_type: str
    county_name: Optional[str] = None
    population: Optional[int] = None
    tax_type_summaries: list[TaxTypeSummary] = Field(default_factory=list)
    naics_record_count: int = 0
    naics_earliest_year_month: Optional[int] = None
    naics_latest_year_month: Optional[int] = None


class LedgerRecord(BaseModel):
    voucher_date: date
    tax_type: str
    tax_rate: float
    current_month_collection: float
    refunded: float
    suspended_monies: float
    apportioned: float
    revolving_fund: float
    interest_returned: float
    returned: float
    mom_pct: Optional[float] = None
    yoy_pct: Optional[float] = None


class LedgerResponse(BaseModel):
    copo: str
    tax_type: str
    records: list[LedgerRecord]
    count: int


class NaicsRecord(BaseModel):
    activity_code: str
    activity_description: Optional[str] = None
    sector: str
    tax_rate: float
    sector_total: float
    year_to_date: float
    pct_of_total: Optional[float] = None


class NaicsResponse(BaseModel):
    copo: str
    tax_type: str
    year: int
    month: int
    records: list[NaicsRecord]
    count: int
    total_revenue: Optional[float] = None


class TopNaicsRecord(BaseModel):
    activity_code: str
    activity_description: Optional[str] = None
    sector: str
    avg_sector_total: float
    months_present: int
    total_across_months: float


class TopNaicsResponse(BaseModel):
    copo: str
    tax_type: str
    records: list[TopNaicsRecord]
    count: int


class TopCityByRevenue(BaseModel):
    copo: str
    name: str
    total_sales_returned: float


class OverviewResponse(BaseModel):
    jurisdictions_with_data: int
    total_ledger_records: int
    total_naics_records: int
    earliest_ledger_date: Optional[date] = None
    latest_ledger_date: Optional[date] = None
    earliest_naics_year_month: Optional[int] = None
    latest_naics_year_month: Optional[int] = None
    top_cities_by_sales: list[TopCityByRevenue]


# -- New response models for seasonality, forecast, and county endpoints ----

class SeasonalityMonth(BaseModel):
    month: int
    month_name: str
    observations: int
    mean_returned: Optional[float] = None
    median_returned: Optional[float] = None
    min_returned: Optional[float] = None
    max_returned: Optional[float] = None
    std_dev: Optional[float] = None


class SeasonalityResponse(BaseModel):
    copo: str
    tax_type: str
    months: list[SeasonalityMonth]


class ForecastPoint(BaseModel):
    target_date: date
    projected_value: float
    lower_bound: float
    upper_bound: float


class ForecastBacktestSummary(BaseModel):
    mape: Optional[float] = None
    smape: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None
    coverage: Optional[float] = None
    fold_count: int = 0
    holdout_description: Optional[str] = None


class ForecastModelComparison(BaseModel):
    model: str
    status: str
    selected: bool = False
    reason: str
    uses_indicators: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)
    forecast_points: list[ForecastPoint] = Field(default_factory=list)
    backtest: ForecastBacktestSummary = Field(default_factory=ForecastBacktestSummary)
    indicator_effects: list[dict[str, Any]] = Field(default_factory=list)


class ForecastExplainability(BaseModel):
    selected_model_reason: str
    model_comparison_summary: str
    trend_summary: str
    seasonality_summary: str
    holiday_summary: str
    indicator_summary: str
    industry_mix_summary: str
    indicator_drivers: list[dict[str, Any]] = Field(default_factory=list)
    top_industry_drivers: list[dict[str, Any]] = Field(default_factory=list)
    activity_description: Optional[str] = None
    data_quality_flags: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    confidence_summary: str


class ForecastDataQuality(BaseModel):
    observation_count: int = 0
    expected_months: int = 0
    minimum_history_required: int = 0
    latest_observation: Optional[date] = None
    stale_months: Optional[int] = None
    missing_month_count: int = 0
    missing_months: list[str] = Field(default_factory=list)
    has_unresolved_gaps: bool = False
    is_sparse_history: bool = False
    advanced_models_allowed: bool = False
    warnings: list[str] = Field(default_factory=list)
    series_scope: Optional[str] = None
    series_start: Optional[date] = None
    series_end: Optional[date] = None
    activity_code: Optional[str] = None
    activity_description: Optional[str] = None
    recent_revenue_share_pct: Optional[float] = None


class ForecastResponse(BaseModel):
    copo: str
    tax_type: str
    model: str
    forecasts: list[ForecastPoint] = Field(default_factory=list)
    selected_model: str
    requested_model: str
    eligible_models: list[str] = Field(default_factory=list)
    forecast_points: list[ForecastPoint] = Field(default_factory=list)
    backtest_summary: ForecastBacktestSummary = Field(default_factory=ForecastBacktestSummary)
    model_comparison: list[ForecastModelComparison] = Field(default_factory=list)
    explainability: ForecastExplainability
    data_quality: ForecastDataQuality
    series_scope: str
    activity_code: Optional[str] = None
    activity_description: Optional[str] = None
    horizon_months: int
    lookback_months: Optional[int] = None
    confidence_level: float
    indicator_profile: str
    run_id: Optional[int] = None


class ForecastComparisonResponse(BaseModel):
    copo: str
    tax_type: str
    selected_model: str
    requested_model: str
    eligible_models: list[str] = Field(default_factory=list)
    model_comparison: list[ForecastModelComparison] = Field(default_factory=list)
    data_quality: ForecastDataQuality
    series_scope: str
    activity_code: Optional[str] = None
    activity_description: Optional[str] = None


class ForecastDriversResponse(BaseModel):
    copo: str
    tax_type: str
    selected_model: str
    requested_model: str
    explainability: ForecastExplainability
    data_quality: ForecastDataQuality
    backtest_summary: ForecastBacktestSummary = Field(default_factory=ForecastBacktestSummary)
    series_scope: str
    activity_code: Optional[str] = None
    activity_description: Optional[str] = None


class CountyCitySummary(BaseModel):
    copo: str
    name: str
    total_returned: Optional[float] = None
    latest_returned: Optional[float] = None


class CountyMonthlyTotal(BaseModel):
    voucher_date: date
    total_returned: float
    city_count: int


class CountySummaryResponse(BaseModel):
    county_name: str
    city_count: int
    cities: list[CountyCitySummary]
    monthly_totals: list[CountyMonthlyTotal]


# -- Response models for city-level anomaly endpoint -------------------------

class CityAnomalyItem(BaseModel):
    id: int
    copo: str
    tax_type: str
    anomaly_date: date
    anomaly_type: str
    severity: str
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    deviation_pct: float
    description: Optional[str] = None
    created_at: Optional[str] = None


class CityAnomaliesResponse(BaseModel):
    copo: str
    items: list[CityAnomalyItem] = Field(default_factory=list)
    count: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_jurisdiction_exists(copo: str) -> None:
    """Raise 404 if the copo code is not in the jurisdictions table."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT 1 FROM jurisdictions WHERE copo = %s",
            (copo,),
        )
        if cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Jurisdiction with copo '{copo}' not found.",
            )


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Normalise a RealDictRow to a plain dict."""
    if row is None:
        return {}
    return dict(row)


_VALID_TAX_TYPES = ("sales", "use", "lodging")


def _validate_tax_type(
    tax_type: str,
    *,
    allowed: tuple[str, ...] = _VALID_TAX_TYPES,
) -> str:
    """Normalise and validate the tax_type parameter."""
    normalized = tax_type.strip().lower()
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tax_type '{tax_type}'. Must be one of: {', '.join(allowed)}.",
        )
    return normalized


def _validate_forecast_model(model: str) -> str:
    normalized = model.strip().lower()
    if normalized not in SUPPORTED_FORECAST_MODELS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid model '{model}'. Must be one of: {', '.join(SUPPORTED_FORECAST_MODELS)}.",
        )
    return normalized


def _validate_indicator_profile(indicator_profile: str) -> str:
    normalized = indicator_profile.strip().lower()
    if normalized not in SUPPORTED_DRIVER_PROFILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid indicator_profile '{indicator_profile}'. Must be one of: {', '.join(SUPPORTED_DRIVER_PROFILES)}.",
        )
    return normalized


def _parse_lookback_months(lookback_months: Optional[str]) -> Optional[int]:
    if lookback_months is None:
        return 36
    normalized = lookback_months.strip().lower()
    if normalized == "all":
        return None
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lookback_months must be one of 24, 36, 48, or 'all'.",
        ) from exc
    if parsed not in (24, 36, 48):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lookback_months must be one of 24, 36, 48, or 'all'.",
        )
    return parsed


# ---------------------------------------------------------------------------
# 1. GET /api/cities  --  List jurisdictions
# ---------------------------------------------------------------------------

@router.get("/cities", response_model=JurisdictionListResponse)
def list_cities(
    search: Optional[str] = Query(None, description="Case-insensitive name search."),
    type: Optional[str] = Query(None, alias="type", description="Filter by jurisdiction_type: city or county."),
    limit: int = Query(50, ge=1, le=500, description="Max results to return."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
) -> JurisdictionListResponse:
    """List jurisdictions with computed summary fields.

    Includes ``has_ledger_data``, ``latest_voucher_date``, and
    ``total_sales_returned`` (sum of all sales-tax returned amounts).
    Results are sorted alphabetically by jurisdiction name.
    """
    where_clauses: list[str] = []
    params: list[Any] = []

    if search:
        where_clauses.append("j.name ILIKE %s")
        params.append(f"%{search}%")

    if type:
        normalized_type = type.strip().lower()
        if normalized_type not in ("city", "county"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid type '{type}'. Must be 'city' or 'county'.",
            )
        where_clauses.append("j.jurisdiction_type = %s")
        params.append(normalized_type)

    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Count query
    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM jurisdictions j
        {where_sql}
    """

    # Data query -- LEFT JOIN to ledger_records to compute summary fields
    data_sql = f"""
        SELECT
            j.copo,
            j.name,
            j.jurisdiction_type       AS jurisdiction_type,
            j.county_name,
            j.population,
            COALESCE(l_agg.has_data, FALSE)         AS has_ledger_data,
            l_agg.latest_voucher_date,
            l_agg.total_sales_returned
        FROM jurisdictions j
        LEFT JOIN LATERAL (
            SELECT
                TRUE                                                     AS has_data,
                MAX(lr.voucher_date)                                     AS latest_voucher_date,
                SUM(lr.returned) FILTER (WHERE lr.tax_type = 'sales')    AS total_sales_returned
            FROM ledger_records lr
            WHERE lr.copo = j.copo
        ) l_agg ON TRUE
        {where_sql}
        ORDER BY j.name ASC
        LIMIT %s OFFSET %s
    """

    # The LIMIT/OFFSET params go after the WHERE params
    data_params = params + [limit, offset]

    with get_cursor() as cur:
        cur.execute(count_sql, params or None)
        total = cur.fetchone()["total"]  # type: ignore[index]

        cur.execute(data_sql, data_params)
        rows = cur.fetchall()

    items = [
        JurisdictionListItem(
            copo=r["copo"],
            name=r["name"],
            jurisdiction_type=r["jurisdiction_type"],
            county_name=r["county_name"],
            population=r["population"],
            has_ledger_data=bool(r["has_ledger_data"]),
            latest_voucher_date=r["latest_voucher_date"],
            total_sales_returned=(
                float(r["total_sales_returned"])
                if r["total_sales_returned"] is not None
                else None
            ),
        )
        for r in rows
    ]

    return JurisdictionListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# 2. GET /api/cities/{copo}  --  Single jurisdiction detail
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}", response_model=JurisdictionDetail)
def get_city(copo: str) -> JurisdictionDetail:
    """Return detailed information for a single jurisdiction.

    Includes jurisdiction metadata, per-tax-type ledger summaries
    (record count, date range, total returned), and NAICS record count
    with date range.
    """
    _ensure_jurisdiction_exists(copo)

    jurisdiction_sql = """
        SELECT
            copo,
            name,
            jurisdiction_type AS jurisdiction_type,
            county_name,
            population
        FROM jurisdictions
        WHERE copo = %s
    """

    tax_summary_sql = """
        SELECT
            tax_type           AS tax_type,
            COUNT(*)           AS record_count,
            MIN(voucher_date)  AS earliest_date,
            MAX(voucher_date)  AS latest_date,
            SUM(returned)      AS total_returned
        FROM ledger_records
        WHERE copo = %s
        GROUP BY tax_type
        ORDER BY tax_type
    """

    naics_summary_sql = """
        SELECT
            COUNT(*)                       AS record_count,
            MIN(year * 100 + month)        AS earliest_year_month,
            MAX(year * 100 + month)        AS latest_year_month
        FROM naics_records
        WHERE copo = %s
    """

    with get_cursor() as cur:
        cur.execute(jurisdiction_sql, (copo,))
        jrow = _row_to_dict(cur.fetchone())

        cur.execute(tax_summary_sql, (copo,))
        tax_rows = cur.fetchall()

        cur.execute(naics_summary_sql, (copo,))
        naics_row = _row_to_dict(cur.fetchone())

    tax_type_summaries = [
        TaxTypeSummary(
            tax_type=r["tax_type"],
            record_count=r["record_count"],
            earliest_date=r["earliest_date"],
            latest_date=r["latest_date"],
            total_returned=float(r["total_returned"]) if r["total_returned"] is not None else None,
        )
        for r in tax_rows
    ]

    return JurisdictionDetail(
        copo=jrow["copo"],
        name=jrow["name"],
        jurisdiction_type=jrow["jurisdiction_type"],
        county_name=jrow["county_name"],
        population=jrow["population"],
        tax_type_summaries=tax_type_summaries,
        naics_record_count=naics_row.get("record_count", 0) or 0,
        naics_earliest_year_month=naics_row.get("earliest_year_month"),
        naics_latest_year_month=naics_row.get("latest_year_month"),
    )


# ---------------------------------------------------------------------------
# 3. GET /api/cities/{copo}/ledger  --  Ledger time series
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/ledger", response_model=LedgerResponse)
def get_city_ledger(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    start: Optional[date] = Query(None, description="Start date (inclusive)."),
    end: Optional[date] = Query(None, description="End date (inclusive)."),
) -> LedgerResponse:
    """Return monthly ledger records for a jurisdiction.

    Records are sorted chronologically. Month-over-month and
    year-over-year percentage changes are computed in SQL using
    window functions.
    """
    _ensure_jurisdiction_exists(copo)

    normalized_tax = _validate_tax_type(tax_type)

    where_parts = [
        "lr.copo = %s",
        "lr.tax_type = %s",
    ]
    params: list[Any] = [copo, normalized_tax]

    if start is not None:
        where_parts.append("lr.voucher_date >= %s")
        params.append(start)
    if end is not None:
        where_parts.append("lr.voucher_date <= %s")
        params.append(end)

    where_sql = " AND ".join(where_parts)

    sql = f"""
        SELECT
            lr.voucher_date,
            lr.tax_type                            AS tax_type,
            lr.tax_rate,
            lr.current_month_collection,
            lr.refunded,
            lr.suspended_monies,
            lr.apportioned,
            lr.revolving_fund,
            lr.interest_returned,
            lr.returned,
            -- Month-over-month change
            CASE
                WHEN LAG(lr.returned) OVER w IS NOT NULL
                     AND LAG(lr.returned) OVER w != 0
                THEN ROUND(
                    ((lr.returned - LAG(lr.returned) OVER w)
                     / ABS(LAG(lr.returned) OVER w)) * 100,
                    2
                )
                ELSE NULL
            END AS mom_pct,
            -- Year-over-year change (same month, prior year)
            CASE
                WHEN LAG(lr.returned, 12) OVER w IS NOT NULL
                     AND LAG(lr.returned, 12) OVER w != 0
                THEN ROUND(
                    ((lr.returned - LAG(lr.returned, 12) OVER w)
                     / ABS(LAG(lr.returned, 12) OVER w)) * 100,
                    2
                )
                ELSE NULL
            END AS yoy_pct
        FROM ledger_records lr
        WHERE {where_sql}
        WINDOW w AS (ORDER BY lr.voucher_date ASC)
        ORDER BY lr.voucher_date ASC
    """

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    records = [
        LedgerRecord(
            voucher_date=r["voucher_date"],
            tax_type=r["tax_type"],
            tax_rate=float(r["tax_rate"]),
            current_month_collection=float(r["current_month_collection"]),
            refunded=float(r["refunded"]),
            suspended_monies=float(r["suspended_monies"]),
            apportioned=float(r["apportioned"]),
            revolving_fund=float(r["revolving_fund"]),
            interest_returned=float(r["interest_returned"]),
            returned=float(r["returned"]),
            mom_pct=float(r["mom_pct"]) if r["mom_pct"] is not None else None,
            yoy_pct=float(r["yoy_pct"]) if r["yoy_pct"] is not None else None,
        )
        for r in rows
    ]

    return LedgerResponse(
        copo=copo,
        tax_type=normalized_tax,
        records=records,
        count=len(records),
    )


# ---------------------------------------------------------------------------
# 4. GET /api/cities/{copo}/naics  --  NAICS industry breakdown
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/naics", response_model=NaicsResponse)
def get_city_naics(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales or use."),
    year: Optional[int] = Query(None, description="Year (defaults to latest available)."),
    month: Optional[int] = Query(None, ge=1, le=12, description="Month 1-12 (defaults to latest available)."),
) -> NaicsResponse:
    """Return NAICS industry breakdown for a jurisdiction.

    If ``year`` and ``month`` are not specified, the latest available
    reporting period is used.  Industries are sorted by sector_total
    descending.  Each record includes ``pct_of_total`` -- the share
    of total revenue for the period.
    """
    _ensure_jurisdiction_exists(copo)

    normalized_tax = tax_type.strip().lower()
    if normalized_tax not in ("sales", "use"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tax_type '{tax_type}' for NAICS. Must be sales or use.",
        )

    # Resolve year/month to the latest available if not provided.
    if year is None or month is None:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT year, month
                FROM naics_records
                WHERE copo = %s AND tax_type = %s
                ORDER BY year DESC, month DESC
                LIMIT 1
                """,
                (copo, normalized_tax),
            )
            latest = cur.fetchone()
            if latest is None:
                return NaicsResponse(
                    copo=copo,
                    tax_type=normalized_tax,
                    year=year or 0,
                    month=month or 0,
                    records=[],
                    count=0,
                    total_revenue=None,
                )
            resolved_year = latest["year"]
            resolved_month = latest["month"]
    else:
        resolved_year = year
        resolved_month = month

    sql = """
        WITH period_data AS (
            SELECT
                n.activity_code,
                n.activity_code_description  AS activity_description,
                n.sector,
                n.tax_rate,
                n.sector_total,
                n.year_to_date
            FROM naics_records n
            WHERE n.copo = %s
              AND n.tax_type = %s
              AND n.year = %s
              AND n.month = %s
        ),
        grand_total AS (
            SELECT COALESCE(SUM(sector_total), 0) AS total
            FROM period_data
        )
        SELECT
            pd.activity_code,
            pd.activity_description,
            pd.sector,
            pd.tax_rate,
            pd.sector_total,
            pd.year_to_date,
            CASE
                WHEN gt.total > 0
                THEN ROUND((pd.sector_total / gt.total) * 100, 2)
                ELSE NULL
            END AS pct_of_total
        FROM period_data pd
        CROSS JOIN grand_total gt
        ORDER BY pd.sector_total DESC
    """

    with get_cursor() as cur:
        cur.execute(sql, (copo, normalized_tax, resolved_year, resolved_month))
        rows = cur.fetchall()

    total_revenue = sum(float(r["sector_total"]) for r in rows) if rows else None

    records = [
        NaicsRecord(
            activity_code=r["activity_code"],
            activity_description=r["activity_description"],
            sector=r["sector"],
            tax_rate=float(r["tax_rate"]),
            sector_total=float(r["sector_total"]),
            year_to_date=float(r["year_to_date"]),
            pct_of_total=float(r["pct_of_total"]) if r["pct_of_total"] is not None else None,
        )
        for r in rows
    ]

    return NaicsResponse(
        copo=copo,
        tax_type=normalized_tax,
        year=resolved_year,
        month=resolved_month,
        records=records,
        count=len(records),
        total_revenue=total_revenue,
    )


# ---------------------------------------------------------------------------
# 5. GET /api/cities/{copo}/naics/top  --  Top NAICS drivers across time
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/naics/top", response_model=TopNaicsResponse)
def get_city_top_naics(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales or use."),
    limit: int = Query(10, ge=1, le=100, description="Number of top industries to return."),
) -> TopNaicsResponse:
    """Return the top NAICS industry drivers for a jurisdiction across
    all available months, ranked by average ``sector_total``.

    Useful for identifying which industries consistently contribute
    the most revenue over time.
    """
    _ensure_jurisdiction_exists(copo)

    normalized_tax = tax_type.strip().lower()
    if normalized_tax not in ("sales", "use"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tax_type '{tax_type}' for NAICS. Must be sales or use.",
        )

    sql = """
        SELECT
            n.activity_code,
            n.activity_code_description     AS activity_description,
            n.sector,
            ROUND(AVG(n.sector_total), 2)   AS avg_sector_total,
            COUNT(*)::int                   AS months_present,
            SUM(n.sector_total)             AS total_across_months
        FROM naics_records n
        WHERE n.copo = %s
          AND n.tax_type = %s
        GROUP BY n.activity_code, n.activity_code_description, n.sector
        ORDER BY avg_sector_total DESC
        LIMIT %s
    """

    with get_cursor() as cur:
        cur.execute(sql, (copo, normalized_tax, limit))
        rows = cur.fetchall()

    records = [
        TopNaicsRecord(
            activity_code=r["activity_code"],
            activity_description=r["activity_description"],
            sector=r["sector"],
            avg_sector_total=float(r["avg_sector_total"]),
            months_present=r["months_present"],
            total_across_months=float(r["total_across_months"]),
        )
        for r in rows
    ]

    return TopNaicsResponse(
        copo=copo,
        tax_type=normalized_tax,
        records=records,
        count=len(records),
    )


# ---------------------------------------------------------------------------
# 6. GET /api/stats/overview  --  Statewide overview
# ---------------------------------------------------------------------------

@router.get("/stats/overview", response_model=OverviewResponse)
def get_overview() -> OverviewResponse:
    """Return statewide summary statistics.

    Includes total jurisdictions with data, record counts, date ranges,
    and the top 10 cities ranked by total sales tax returned.
    """
    summary_sql = """
        SELECT
            (SELECT COUNT(DISTINCT copo) FROM ledger_records)          AS jurisdictions_with_data,
            (SELECT COUNT(*) FROM ledger_records)                      AS total_ledger_records,
            (SELECT COUNT(*) FROM naics_records)                       AS total_naics_records,
            (SELECT MIN(voucher_date) FROM ledger_records)             AS earliest_ledger_date,
            (SELECT MAX(voucher_date) FROM ledger_records)             AS latest_ledger_date,
            (SELECT MIN(year * 100 + month) FROM naics_records)        AS earliest_naics_year_month,
            (SELECT MAX(year * 100 + month) FROM naics_records)        AS latest_naics_year_month
    """

    top_cities_sql = """
        SELECT
            lr.copo,
            j.name,
            SUM(lr.returned) AS total_sales_returned
        FROM ledger_records lr
        JOIN jurisdictions j ON j.copo = lr.copo
        WHERE lr.tax_type = 'sales'
        GROUP BY lr.copo, j.name
        ORDER BY total_sales_returned DESC
        LIMIT 10
    """

    with get_cursor() as cur:
        cur.execute(summary_sql)
        summary = _row_to_dict(cur.fetchone())

        cur.execute(top_cities_sql)
        top_rows = cur.fetchall()

    top_cities = [
        TopCityByRevenue(
            copo=r["copo"],
            name=r["name"],
            total_sales_returned=float(r["total_sales_returned"]),
        )
        for r in top_rows
    ]

    return OverviewResponse(
        jurisdictions_with_data=summary.get("jurisdictions_with_data", 0) or 0,
        total_ledger_records=summary.get("total_ledger_records", 0) or 0,
        total_naics_records=summary.get("total_naics_records", 0) or 0,
        earliest_ledger_date=summary.get("earliest_ledger_date"),
        latest_ledger_date=summary.get("latest_ledger_date"),
        earliest_naics_year_month=summary.get("earliest_naics_year_month"),
        latest_naics_year_month=summary.get("latest_naics_year_month"),
        top_cities_by_sales=top_cities,
    )


# ---------------------------------------------------------------------------
# 7. GET /api/cities/{copo}/seasonality  --  Monthly seasonal statistics
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/seasonality", response_model=SeasonalityResponse)
def get_city_seasonality(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
) -> SeasonalityResponse:
    """Return monthly seasonal statistics for a jurisdiction.

    Groups all historical ledger data by calendar month (1-12) to show
    the mean, median, min, max, and standard deviation of returned
    amounts.  Useful for understanding seasonal revenue patterns.
    """
    _ensure_jurisdiction_exists(copo)
    normalized_tax = _validate_tax_type(tax_type)

    sql = """
        SELECT
            EXTRACT(MONTH FROM voucher_date)::int              AS month,
            COUNT(*)                                           AS observations,
            AVG(returned)                                      AS mean_returned,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY returned) AS median_returned,
            MIN(returned)                                      AS min_returned,
            MAX(returned)                                      AS max_returned,
            STDDEV(returned)                                   AS std_dev
        FROM ledger_records
        WHERE copo = %s AND tax_type = %s
        GROUP BY month
        ORDER BY month
    """

    with get_cursor() as cur:
        cur.execute(sql, (copo, normalized_tax))
        rows = cur.fetchall()

    months = [
        SeasonalityMonth(
            month=int(r["month"]),
            month_name=calendar.month_name[int(r["month"])],
            observations=int(r["observations"]),
            mean_returned=round(float(r["mean_returned"]), 2) if r["mean_returned"] is not None else None,
            median_returned=round(float(r["median_returned"]), 2) if r["median_returned"] is not None else None,
            min_returned=float(r["min_returned"]) if r["min_returned"] is not None else None,
            max_returned=float(r["max_returned"]) if r["max_returned"] is not None else None,
            std_dev=round(float(r["std_dev"]), 2) if r["std_dev"] is not None else None,
        )
        for r in rows
    ]

    return SeasonalityResponse(
        copo=copo,
        tax_type=normalized_tax,
        months=months,
    )


# ---------------------------------------------------------------------------
# 8. GET /api/cities/{copo}/forecast  --  configurable forecast framework
# ---------------------------------------------------------------------------


def _build_city_forecast_payload(
    *,
    copo: str,
    tax_type: str,
    model: str,
    horizon_months: int,
    lookback_months: Optional[str],
    confidence_level: float,
    indicator_profile: str,
    activity_code: Optional[str],
    persist: bool,
) -> dict[str, Any]:
    _ensure_jurisdiction_exists(copo)
    normalized_tax = _validate_tax_type(tax_type)
    normalized_model = _validate_forecast_model(model)
    normalized_profile = _validate_indicator_profile(indicator_profile)
    parsed_lookback = _parse_lookback_months(lookback_months)

    if activity_code is not None:
        activity_code = activity_code.strip()
        if normalized_tax not in ("sales", "use"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="activity_code forecasts are only available for sales and use tax series.",
            )
        if not activity_code:
            activity_code = None

    with get_cursor() as cur:
        return build_forecast_package(
            cur,
            copo=copo,
            tax_type=normalized_tax,
            requested_model=normalized_model,
            horizon_months=horizon_months,
            lookback_months=parsed_lookback,
            confidence_level=confidence_level,
            indicator_profile=normalized_profile,
            activity_code=activity_code,
            persist=persist,
        )


@router.get("/cities/{copo}/forecast", response_model=ForecastResponse)
def get_city_forecast(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    model: str = Query("auto", description="Forecast model: auto, baseline, sarima, prophet, or ensemble."),
    horizon_months: int = Query(12, ge=1, le=24, description="Forecast horizon in months."),
    lookback_months: Optional[str] = Query("36", description="Training lookback window: 24, 36, 48, or all."),
    confidence_level: float = Query(0.95, ge=0.80, le=0.99, description="Confidence interval level."),
    indicator_profile: str = Query("balanced", description="Driver profile: off, labor, retail_housing, balanced."),
    activity_code: Optional[str] = Query(None, description="Optional NAICS activity code for industry-level forecasts."),
) -> ForecastResponse:
    """Return a configurable municipal or NAICS-level forecast package."""
    payload = _build_city_forecast_payload(
        copo=copo,
        tax_type=tax_type,
        model=model,
        horizon_months=horizon_months,
        lookback_months=lookback_months,
        confidence_level=confidence_level,
        indicator_profile=indicator_profile,
        activity_code=activity_code,
        persist=True,
    )
    return ForecastResponse(**payload)


@router.get("/cities/{copo}/forecast/compare", response_model=ForecastComparisonResponse)
def compare_city_forecast_models(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    model: str = Query("auto", description="Forecast model: auto, baseline, sarima, prophet, or ensemble."),
    horizon_months: int = Query(12, ge=1, le=24, description="Forecast horizon in months."),
    lookback_months: Optional[str] = Query("36", description="Training lookback window: 24, 36, 48, or all."),
    confidence_level: float = Query(0.95, ge=0.80, le=0.99, description="Confidence interval level."),
    indicator_profile: str = Query("balanced", description="Driver profile: off, labor, retail_housing, balanced."),
    activity_code: Optional[str] = Query(None, description="Optional NAICS activity code for industry-level forecasts."),
) -> ForecastComparisonResponse:
    """Return the model comparison table without the primary chart payload."""
    payload = _build_city_forecast_payload(
        copo=copo,
        tax_type=tax_type,
        model=model,
        horizon_months=horizon_months,
        lookback_months=lookback_months,
        confidence_level=confidence_level,
        indicator_profile=indicator_profile,
        activity_code=activity_code,
        persist=False,
    )
    comparison_payload = {
        "copo": payload["copo"],
        "tax_type": payload["tax_type"],
        "selected_model": payload["selected_model"],
        "requested_model": payload["requested_model"],
        "eligible_models": payload["eligible_models"],
        "model_comparison": payload["model_comparison"],
        "data_quality": payload["data_quality"],
        "series_scope": payload["series_scope"],
        "activity_code": payload.get("activity_code"),
        "activity_description": payload.get("activity_description"),
    }
    return ForecastComparisonResponse(**comparison_payload)


@router.get("/cities/{copo}/forecast/drivers", response_model=ForecastDriversResponse)
def get_city_forecast_drivers(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    model: str = Query("auto", description="Forecast model: auto, baseline, sarima, prophet, or ensemble."),
    horizon_months: int = Query(12, ge=1, le=24, description="Forecast horizon in months."),
    lookback_months: Optional[str] = Query("36", description="Training lookback window: 24, 36, 48, or all."),
    confidence_level: float = Query(0.95, ge=0.80, le=0.99, description="Confidence interval level."),
    indicator_profile: str = Query("balanced", description="Driver profile: off, labor, retail_housing, balanced."),
    activity_code: Optional[str] = Query(None, description="Optional NAICS activity code for industry-level forecasts."),
) -> ForecastDriversResponse:
    """Return the explainability payload for the active forecast configuration."""
    payload = _build_city_forecast_payload(
        copo=copo,
        tax_type=tax_type,
        model=model,
        horizon_months=horizon_months,
        lookback_months=lookback_months,
        confidence_level=confidence_level,
        indicator_profile=indicator_profile,
        activity_code=activity_code,
        persist=False,
    )
    drivers_payload = {
        "copo": payload["copo"],
        "tax_type": payload["tax_type"],
        "selected_model": payload["selected_model"],
        "requested_model": payload["requested_model"],
        "explainability": payload["explainability"],
        "data_quality": payload["data_quality"],
        "backtest_summary": payload["backtest_summary"],
        "series_scope": payload["series_scope"],
        "activity_code": payload.get("activity_code"),
        "activity_description": payload.get("activity_description"),
    }
    return ForecastDriversResponse(**drivers_payload)


# ---------------------------------------------------------------------------
# 9. GET /api/cities/{copo}/ledger/export  --  CSV download
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/ledger/export")
def export_city_ledger(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    start: Optional[date] = Query(None, description="Start date (inclusive)."),
    end: Optional[date] = Query(None, description="End date (inclusive)."),
) -> StreamingResponse:
    """Export ledger records as a downloadable CSV file.

    Uses the same query as the JSON ledger endpoint but streams the
    result as ``text/csv`` with a Content-Disposition header for
    browser downloads.
    """
    _ensure_jurisdiction_exists(copo)
    normalized_tax = _validate_tax_type(tax_type)

    where_parts = [
        "lr.copo = %s",
        "lr.tax_type = %s",
    ]
    params: list[Any] = [copo, normalized_tax]

    if start is not None:
        where_parts.append("lr.voucher_date >= %s")
        params.append(start)
    if end is not None:
        where_parts.append("lr.voucher_date <= %s")
        params.append(end)

    where_sql = " AND ".join(where_parts)

    sql = f"""
        SELECT
            lr.voucher_date,
            lr.tax_type,
            lr.tax_rate,
            lr.current_month_collection,
            lr.refunded,
            lr.suspended_monies,
            lr.apportioned,
            lr.revolving_fund,
            lr.interest_returned,
            lr.returned
        FROM ledger_records lr
        WHERE {where_sql}
        ORDER BY lr.voucher_date ASC
    """

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    # Build CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    columns = [
        "voucher_date",
        "tax_type",
        "tax_rate",
        "current_month_collection",
        "refunded",
        "suspended_monies",
        "apportioned",
        "revolving_fund",
        "interest_returned",
        "returned",
    ]
    writer.writerow(columns)

    for r in rows:
        writer.writerow([r[col] for col in columns])

    output.seek(0)
    filename = f"{copo}_{normalized_tax}_ledger.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ---------------------------------------------------------------------------
# 10. GET /api/counties/{county_name}/summary  --  County aggregate
# ---------------------------------------------------------------------------

@router.get("/counties/{county_name}/summary", response_model=CountySummaryResponse)
def get_county_summary(
    county_name: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    limit: int = Query(24, ge=1, le=120, description="Number of recent months to include."),
) -> CountySummaryResponse:
    """Return an aggregate summary for a county.

    Includes a list of cities in the county with their total and latest
    returned amounts, plus monthly aggregate totals across all cities
    in the county.
    """
    normalized_tax = _validate_tax_type(tax_type)

    # Verify that the county exists
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM jurisdictions WHERE county_name ILIKE %s",
            (county_name,),
        )
        row = cur.fetchone()
        if row is None or row["cnt"] == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"County '{county_name}' not found.",
            )

    # Per-city breakdown
    cities_sql = """
        SELECT
            j.copo,
            j.name,
            SUM(lr.returned) AS total_returned,
            (
                SELECT lr2.returned
                FROM ledger_records lr2
                WHERE lr2.copo = j.copo AND lr2.tax_type = %s
                ORDER BY lr2.voucher_date DESC
                LIMIT 1
            ) AS latest_returned
        FROM jurisdictions j
        LEFT JOIN ledger_records lr
            ON lr.copo = j.copo AND lr.tax_type = %s
        WHERE j.county_name ILIKE %s
        GROUP BY j.copo, j.name
        ORDER BY total_returned DESC NULLS LAST
    """

    # Monthly aggregate across all cities in the county
    monthly_sql = """
        SELECT
            lr.voucher_date,
            SUM(lr.returned)       AS total_returned,
            COUNT(DISTINCT lr.copo) AS city_count
        FROM ledger_records lr
        JOIN jurisdictions j ON j.copo = lr.copo
        WHERE j.county_name ILIKE %s
          AND lr.tax_type = %s
        GROUP BY lr.voucher_date
        ORDER BY lr.voucher_date DESC
        LIMIT %s
    """

    with get_cursor() as cur:
        cur.execute(cities_sql, (normalized_tax, normalized_tax, county_name))
        city_rows = cur.fetchall()

        cur.execute(monthly_sql, (county_name, normalized_tax, limit))
        monthly_rows = cur.fetchall()

    cities = [
        CountyCitySummary(
            copo=r["copo"],
            name=r["name"],
            total_returned=round(float(r["total_returned"]), 2) if r["total_returned"] is not None else None,
            latest_returned=round(float(r["latest_returned"]), 2) if r["latest_returned"] is not None else None,
        )
        for r in city_rows
    ]

    # Reverse monthly rows to chronological order
    monthly_rows = list(reversed(monthly_rows))

    monthly_totals = [
        CountyMonthlyTotal(
            voucher_date=r["voucher_date"],
            total_returned=round(float(r["total_returned"]), 2),
            city_count=int(r["city_count"]),
        )
        for r in monthly_rows
    ]

    # Use the canonical county_name from the first jurisdiction found
    canonical_county = county_name
    if city_rows:
        with get_cursor() as cur:
            cur.execute(
                "SELECT county_name FROM jurisdictions WHERE county_name ILIKE %s LIMIT 1",
                (county_name,),
            )
            cn_row = cur.fetchone()
            if cn_row:
                canonical_county = cn_row["county_name"]

    return CountySummaryResponse(
        county_name=canonical_county,
        city_count=len(cities),
        cities=cities,
        monthly_totals=monthly_totals,
    )


# ---------------------------------------------------------------------------
# 11. GET /api/cities/{copo}/anomalies  --  City anomaly feed
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/anomalies", response_model=CityAnomaliesResponse)
def get_city_anomalies(
    copo: str,
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical."),
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly type: yoy_spike, yoy_drop, mom_outlier, missing_data, naics_shift."),
    start_date: Optional[date] = Query(None, description="Start date for anomaly_date filter (inclusive)."),
    end_date: Optional[date] = Query(None, description="End date for anomaly_date filter (inclusive)."),
) -> CityAnomaliesResponse:
    """Return detected anomalies for a specific jurisdiction.

    Results are ordered by anomaly_date descending (most recent first).
    Supports optional filtering by severity, anomaly type, and date range.
    """
    _ensure_jurisdiction_exists(copo)

    where_parts: list[str] = ["copo = %s"]
    params: list[Any] = [copo]

    if severity is not None:
        normalized_sev = severity.strip().lower()
        if normalized_sev not in ("low", "medium", "high", "critical"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity '{severity}'. Must be low, medium, high, or critical.",
            )
        where_parts.append("severity = %s")
        params.append(normalized_sev)

    if anomaly_type is not None:
        normalized_at = anomaly_type.strip().lower()
        valid_types = ("yoy_spike", "yoy_drop", "mom_outlier", "missing_data", "naics_shift")
        if normalized_at not in valid_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid anomaly_type. Must be one of: {', '.join(valid_types)}",
            )
        where_parts.append("anomaly_type = %s")
        params.append(normalized_at)

    if start_date is not None:
        where_parts.append("anomaly_date >= %s")
        params.append(start_date)

    if end_date is not None:
        where_parts.append("anomaly_date <= %s")
        params.append(end_date)

    where_sql = " AND ".join(where_parts)

    sql = f"""
        SELECT
            id, copo, tax_type, anomaly_date, anomaly_type,
            severity, expected_value, actual_value, deviation_pct,
            description, created_at
        FROM anomalies
        WHERE {where_sql}
        ORDER BY anomaly_date DESC
    """

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    items = [
        CityAnomalyItem(
            id=r["id"],
            copo=r["copo"],
            tax_type=r["tax_type"],
            anomaly_date=r["anomaly_date"],
            anomaly_type=r["anomaly_type"],
            severity=r["severity"],
            expected_value=float(r["expected_value"]) if r["expected_value"] is not None else None,
            actual_value=float(r["actual_value"]) if r["actual_value"] is not None else None,
            deviation_pct=float(r["deviation_pct"]),
            description=r["description"],
            created_at=r["created_at"].isoformat() if r["created_at"] is not None else None,
        )
        for r in rows
    ]

    return CityAnomaliesResponse(
        copo=copo,
        items=items,
        count=len(items),
    )


# ── Industry time series ──────────────────────────────────


class IndustryTimeSeriesPoint(BaseModel):
    year: int
    month: int
    sector_total: float


class IndustryTimeSeriesResponse(BaseModel):
    copo: str
    activity_code: str
    activity_description: Optional[str] = None
    tax_type: str
    records: list[IndustryTimeSeriesPoint]
    count: int


@router.get(
    "/cities/{copo}/naics/timeseries/{activity_code}",
    response_model=IndustryTimeSeriesResponse,
    summary="NAICS industry time series for a city",
)
def get_industry_timeseries(
    copo: str,
    activity_code: str,
    tax_type: str = Query("sales", description="Tax type: sales or use."),
) -> IndustryTimeSeriesResponse:
    """Monthly revenue for a specific NAICS industry code within a city."""
    _ensure_jurisdiction_exists(copo)

    sql = """
        SELECT year, month, sector_total, activity_code_description
        FROM naics_records
        WHERE copo = %s AND tax_type = %s AND activity_code = %s
        ORDER BY year, month
    """

    with get_cursor() as cur:
        cur.execute(sql, (copo, tax_type, activity_code))
        rows = cur.fetchall()

    if not rows:
        return IndustryTimeSeriesResponse(
            copo=copo, activity_code=activity_code, tax_type=tax_type,
            records=[], count=0,
        )

    description = rows[0].get("activity_code_description")
    records = [
        IndustryTimeSeriesPoint(
            year=r["year"], month=r["month"],
            sector_total=float(r["sector_total"]) if r["sector_total"] else 0,
        )
        for r in rows
    ]

    return IndustryTimeSeriesResponse(
        copo=copo, activity_code=activity_code,
        activity_description=description, tax_type=tax_type,
        records=records, count=len(records),
    )


# ---------------------------------------------------------------------------
# 13. GET /api/cities/{copo}/anomalies/{anomaly_date}/decompose
#     Industry decomposition for an anomaly period
# ---------------------------------------------------------------------------


class PeriodSummary(BaseModel):
    year: int
    month: int
    total: float


class IndustryChange(BaseModel):
    activity_code: str
    description: Optional[str] = None
    sector: str
    current_value: float
    prior_value: float
    change: float
    change_pct: Optional[float] = None
    contribution_pct: float


class DecompositionResponse(BaseModel):
    copo: str
    tax_type: str
    anomaly_date: str
    comparison_type: str
    current_period: PeriodSummary
    prior_period: PeriodSummary
    total_change: float
    total_change_pct: Optional[float] = None
    industries: list[IndustryChange]
    count: int


@router.get(
    "/cities/{copo}/anomalies/{anomaly_date}/decompose",
    response_model=DecompositionResponse,
    summary="Industry decomposition of an anomaly",
)
def decompose_anomaly(
    copo: str,
    anomaly_date: str,
    tax_type: str = Query(..., description="Tax type: sales or use."),
    comparison: str = Query("yoy", description="Comparison mode: yoy or mom."),
) -> DecompositionResponse:
    """Decompose an anomaly into its industry-level drivers.

    For the month identified by ``anomaly_date``, compares NAICS industry
    revenue against a prior period (year-over-year or month-over-month)
    and ranks industries by absolute change to show which sectors drove
    the anomalous movement.
    """
    _ensure_jurisdiction_exists(copo)

    # -- Validate tax_type (only sales/use for NAICS) ----------------------
    normalized_tax = tax_type.strip().lower()
    if normalized_tax not in ("sales", "use"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tax_type '{tax_type}'. Must be 'sales' or 'use'.",
        )

    # -- Validate comparison parameter -------------------------------------
    normalized_comparison = comparison.strip().lower()
    if normalized_comparison not in ("yoy", "mom"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid comparison '{comparison}'. Must be 'yoy' or 'mom'.",
        )

    # -- Parse anomaly_date to extract year and month ----------------------
    try:
        parsed_date = date.fromisoformat(anomaly_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid anomaly_date '{anomaly_date}'. Expected ISO format YYYY-MM-DD.",
        )

    current_year = parsed_date.year
    current_month = parsed_date.month

    # -- Determine prior period --------------------------------------------
    if normalized_comparison == "yoy":
        prior_year = current_year - 1
        prior_month = current_month
    else:
        # month-over-month: go back one month
        if current_month == 1:
            prior_year = current_year - 1
            prior_month = 12
        else:
            prior_year = current_year
            prior_month = current_month - 1

    # -- Query NAICS data for both periods via FULL OUTER JOIN -------------
    #
    # Uses sub-selects for current and prior periods joined on
    # activity_code so industries appearing in only one period are
    # still captured.
    decompose_sql = """
        SELECT
            COALESCE(cur.activity_code, pri.activity_code) AS activity_code,
            COALESCE(cur.activity_code_description,
                     pri.activity_code_description)        AS description,
            COALESCE(cur.sector, pri.sector)               AS sector,
            COALESCE(cur.sector_total, 0)                  AS current_value,
            COALESCE(pri.sector_total, 0)                  AS prior_value
        FROM (
            SELECT activity_code, activity_code_description, sector, sector_total
            FROM naics_records
            WHERE copo = %s AND tax_type = %s AND year = %s AND month = %s
        ) cur
        FULL OUTER JOIN (
            SELECT activity_code, activity_code_description, sector, sector_total
            FROM naics_records
            WHERE copo = %s AND tax_type = %s AND year = %s AND month = %s
        ) pri ON cur.activity_code = pri.activity_code
        ORDER BY ABS(COALESCE(cur.sector_total, 0) - COALESCE(pri.sector_total, 0)) DESC
    """

    params: list[Any] = [
        copo, normalized_tax, current_year, current_month,
        copo, normalized_tax, prior_year, prior_month,
    ]

    with get_cursor() as cur:
        cur.execute(decompose_sql, params)
        rows = cur.fetchall()

    # -- Compute totals and per-industry metrics ---------------------------
    current_total = 0.0
    prior_total = 0.0
    raw_industries: list[dict[str, Any]] = []

    for r in rows:
        cv = float(r["current_value"])
        pv = float(r["prior_value"])
        change = cv - pv

        current_total += cv
        prior_total += pv

        # Skip tiny changes (less than $100 absolute)
        if abs(change) < 100:
            continue

        # change_pct: guard against zero prior
        if pv != 0:
            change_pct: Optional[float] = round((change / pv) * 100, 2)
        else:
            change_pct = None

        raw_industries.append({
            "activity_code": r["activity_code"],
            "description": r["description"],
            "sector": r["sector"],
            "current_value": round(cv, 2),
            "prior_value": round(pv, 2),
            "change": round(change, 2),
            "change_pct": change_pct,
        })

    total_change = round(current_total - prior_total, 2)

    if prior_total != 0:
        total_change_pct: Optional[float] = round(
            (total_change / prior_total) * 100, 2
        )
    else:
        total_change_pct = None

    # -- Compute contribution_pct and build final list ---------------------
    industries: list[IndustryChange] = []
    for ind in raw_industries:
        if total_change != 0:
            contribution = round((ind["change"] / total_change) * 100, 2)
        else:
            contribution = 0.0

        industries.append(
            IndustryChange(
                activity_code=ind["activity_code"],
                description=ind["description"],
                sector=ind["sector"],
                current_value=ind["current_value"],
                prior_value=ind["prior_value"],
                change=ind["change"],
                change_pct=ind["change_pct"],
                contribution_pct=contribution,
            )
        )

    # Already sorted by ABS(change) DESC from SQL; limit to top 50
    industries = industries[:50]

    return DecompositionResponse(
        copo=copo,
        tax_type=normalized_tax,
        anomaly_date=anomaly_date,
        comparison_type=normalized_comparison,
        current_period=PeriodSummary(
            year=current_year,
            month=current_month,
            total=round(current_total, 2),
        ),
        prior_period=PeriodSummary(
            year=prior_year,
            month=prior_month,
            total=round(prior_total, 2),
        ),
        total_change=total_change,
        total_change_pct=total_change_pct,
        industries=industries,
        count=len(industries),
    )
