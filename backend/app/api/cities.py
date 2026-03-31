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
import math
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any, Iterator, Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DATABASE_URL = "postgresql://munirev:changeme@localhost:5432/munirev"

router = APIRouter(prefix="/api", tags=["cities"])


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


class ForecastResponse(BaseModel):
    copo: str
    tax_type: str
    model: str
    forecasts: list[ForecastPoint]


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
# 8. GET /api/cities/{copo}/forecast  --  12-month on-the-fly forecast
# ---------------------------------------------------------------------------

@router.get("/cities/{copo}/forecast", response_model=ForecastResponse)
def get_city_forecast(
    copo: str,
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
) -> ForecastResponse:
    """Compute a 12-month revenue forecast for a jurisdiction.

    The model uses a seasonal-trend decomposition approach:
    1. Fetch the last 36 months of ledger data.
    2. Compute seasonal averages by calendar month.
    3. Compute a trend factor (last-12 total vs prior-12 total).
    4. Project 12 months forward: seasonal_avg * trend_factor.
    5. Confidence interval: +/- 1.96 * std_dev of residuals.
    """
    _ensure_jurisdiction_exists(copo)
    normalized_tax = _validate_tax_type(tax_type)

    # Fetch last 36 months of ledger data ordered chronologically
    sql = """
        SELECT
            voucher_date,
            returned
        FROM ledger_records
        WHERE copo = %s AND tax_type = %s
        ORDER BY voucher_date DESC
        LIMIT 36
    """

    with get_cursor() as cur:
        cur.execute(sql, (copo, normalized_tax))
        rows = cur.fetchall()

    if not rows:
        return ForecastResponse(
            copo=copo,
            tax_type=normalized_tax,
            model="seasonal_trend",
            forecasts=[],
        )

    # Sort chronologically (query was DESC for LIMIT)
    rows = list(reversed(rows))
    n = len(rows)

    # Build month-indexed data structures
    # seasonal_sums[month] = list of returned values for that calendar month
    seasonal_sums: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for r in rows:
        vd: date = r["voucher_date"]
        val = float(r["returned"])
        seasonal_sums[vd.month].append(val)

    # Seasonal average by calendar month
    seasonal_avg: dict[int, float] = {}
    for m in range(1, 13):
        vals = seasonal_sums[m]
        seasonal_avg[m] = sum(vals) / len(vals) if vals else 0.0

    # Trend factor: ratio of last-12 total to prior-12 total
    trend_factor = 1.0
    if n >= 24:
        recent_12 = sum(float(r["returned"]) for r in rows[-12:])
        prior_12 = sum(float(r["returned"]) for r in rows[-24:-12])
        if prior_12 != 0:
            trend_factor = recent_12 / prior_12

    # Compute residuals to estimate confidence interval width
    residuals: list[float] = []
    for r in rows:
        vd = r["voucher_date"]
        actual = float(r["returned"])
        expected = seasonal_avg.get(vd.month, 0.0)
        if expected != 0:
            residuals.append(actual - expected)

    if residuals:
        mean_residual = sum(residuals) / len(residuals)
        variance = sum((x - mean_residual) ** 2 for x in residuals) / len(residuals)
        std_residual = math.sqrt(variance)
    else:
        std_residual = 0.0

    # Determine the starting point for forecasts: month after latest data
    latest_date: date = rows[-1]["voucher_date"]

    forecasts: list[ForecastPoint] = []
    for i in range(1, 13):
        # Advance by i months from latest_date
        target_month = latest_date.month + i
        target_year = latest_date.year
        while target_month > 12:
            target_month -= 12
            target_year += 1

        # Last day of the target month as the target date
        last_day = calendar.monthrange(target_year, target_month)[1]
        target_date = date(target_year, target_month, last_day)

        base = seasonal_avg.get(target_month, 0.0)
        projected = base * trend_factor
        margin = 1.96 * std_residual

        forecasts.append(
            ForecastPoint(
                target_date=target_date,
                projected_value=round(projected, 2),
                lower_bound=round(projected - margin, 2),
                upper_bound=round(projected + margin, 2),
            )
        )

    return ForecastResponse(
        copo=copo,
        tax_type=normalized_tax,
        model="seasonal_trend",
        forecasts=forecasts,
    )


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
