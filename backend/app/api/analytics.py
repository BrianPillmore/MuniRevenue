"""Statewide analytics endpoints for the MuniRev database.

This router must be registered in ``app.main``:

    from app.api.analytics import router as analytics_router
    app.include_router(analytics_router)

All queries use psycopg2 with parameterized statements to prevent
SQL injection.  No ORM -- just plain SQL for full control over the
analytics queries.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.cities import get_cursor
from app.security import require_scopes

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/stats",
    tags=["analytics"],
    dependencies=[Depends(require_scopes("api:read"))],
)


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class StatewideTrendRecord(BaseModel):
    voucher_date: date
    total_returned: float
    jurisdiction_count: int
    mom_pct: Optional[float] = None
    yoy_pct: Optional[float] = None


class StatewideTrendResponse(BaseModel):
    tax_type: str
    records: list[StatewideTrendRecord]
    count: int


class RankingItem(BaseModel):
    rank: int
    copo: str
    name: str
    county_name: Optional[str] = None
    jurisdiction_type: str
    population: Optional[int] = None
    metric_value: Optional[float] = None


class RankingsResponse(BaseModel):
    tax_type: str
    metric: str
    items: list[RankingItem]
    total: int
    limit: int
    offset: int


class SectorMonthlyData(BaseModel):
    year: int
    month: int
    total: float


class NaicsSectorItem(BaseModel):
    sector: str
    sector_name: Optional[str] = None
    monthly_data: list[SectorMonthlyData] = Field(default_factory=list)


class NaicsSectorsResponse(BaseModel):
    tax_type: str
    sectors: list[NaicsSectorItem]
    count: int


class AnomalyItem(BaseModel):
    copo: str
    city_name: str
    tax_type: str
    anomaly_date: date
    anomaly_type: str
    severity: str
    expected_value: Optional[float] = None
    actual_value: Optional[float] = None
    deviation_pct: float
    description: str


class AnomaliesResponse(BaseModel):
    items: list[AnomalyItem] = Field(default_factory=list)
    count: int = 0


class MissedFilingItem(BaseModel):
    copo: str
    city_name: str
    tax_type: str
    anomaly_date: date
    activity_code: str
    activity_description: str
    baseline_method: str
    baseline_months_used: int
    prior_year_value: Optional[float] = None
    trailing_mean_3: Optional[float] = None
    trailing_mean_6: Optional[float] = None
    trailing_mean_12: Optional[float] = None
    trailing_median_12: Optional[float] = None
    exp_weighted_avg_12: Optional[float] = None
    expected_value: float
    actual_value: float
    missing_amount: float
    missing_pct: float
    baseline_share_pct: float
    severity: str
    recommendation: str


class MissedFilingsRefreshInfo(BaseModel):
    last_refresh_at: Optional[datetime] = None
    data_min_month: Optional[date] = None
    data_max_month: Optional[date] = None
    snapshot_row_count: int = 0
    refresh_duration_seconds: Optional[float] = None


class MissedFilingsResponse(BaseModel):
    items: list[MissedFilingItem] = Field(default_factory=list)
    count: int = 0
    total: int = 0
    limit: Optional[int] = None
    offset: int = 0
    has_more: bool = False
    refresh_info: MissedFilingsRefreshInfo = Field(default_factory=MissedFilingsRefreshInfo)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TAX_TYPES = ("sales", "use", "lodging")
_VALID_MISSED_FILING_RUN_RATE_METHODS = (
    "hybrid",
    "yoy",
    "trailing_mean_3",
    "trailing_mean_6",
    "trailing_mean_12",
    "trailing_median_12",
    "exp_weighted_12",
)
_VALID_MISSED_FILING_SORT_OPTIONS = (
    "severity",
    "amount",
    "pct",
    "share",
    "date",
    "city",
)
_MISSED_FILING_METHOD_LABELS = {
    "hybrid": "Hybrid (YoY + 12m median)",
    "yoy": "Same month prior year",
    "trailing_mean_3": "Trailing 3-month average",
    "trailing_mean_6": "Trailing 6-month average",
    "trailing_mean_12": "Trailing 12-month average",
    "trailing_median_12": "Trailing 12-month median",
    "exp_weighted_12": "Exponentially weighted 12-month average",
}

_MISSED_FILING_CANDIDATES_DDL = """
CREATE TABLE IF NOT EXISTS missed_filing_candidates (
    id BIGSERIAL PRIMARY KEY,
    copo VARCHAR(10) NOT NULL,
    city_name TEXT NOT NULL,
    tax_type VARCHAR(10) NOT NULL,
    anomaly_date DATE NOT NULL,
    activity_code VARCHAR(6) NOT NULL,
    activity_description TEXT NOT NULL,
    city_total NUMERIC(14,2) NOT NULL,
    prior_year_value NUMERIC(14,2),
    trailing_mean_3 NUMERIC(14,2),
    trailing_count_3 INTEGER,
    trailing_mean_6 NUMERIC(14,2),
    trailing_count_6 INTEGER,
    trailing_mean_12 NUMERIC(14,2),
    trailing_count_12 INTEGER,
    trailing_median_12 NUMERIC(14,2),
    exp_weighted_avg_12 NUMERIC(14,2),
    actual_value NUMERIC(14,2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (copo, tax_type, anomaly_date, activity_code)
);
ALTER TABLE missed_filing_candidates
    ADD COLUMN IF NOT EXISTS city_prior_year_total NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS city_trailing_mean_3 NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS city_trailing_count_3 INTEGER,
    ADD COLUMN IF NOT EXISTS city_trailing_mean_6 NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS city_trailing_count_6 INTEGER,
    ADD COLUMN IF NOT EXISTS city_trailing_mean_12 NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS city_trailing_count_12 INTEGER,
    ADD COLUMN IF NOT EXISTS city_trailing_median_12 NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS city_exp_weighted_avg_12 NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS hybrid_expected_value NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS hybrid_city_expected_total NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS hybrid_missing_amount NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS hybrid_missing_pct NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS hybrid_baseline_share_pct NUMERIC(14,2),
    ADD COLUMN IF NOT EXISTS hybrid_baseline_months_used INTEGER;
CREATE INDEX IF NOT EXISTS idx_missed_filing_candidates_lookup
    ON missed_filing_candidates (anomaly_date DESC, tax_type, copo, activity_code);
"""
_MISSED_FILING_REFRESH_META_DDL = """
CREATE TABLE IF NOT EXISTS missed_filing_candidates_refresh_meta (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    last_refresh_at TIMESTAMPTZ NOT NULL,
    data_min_month DATE,
    data_max_month DATE,
    snapshot_row_count INTEGER NOT NULL,
    refresh_duration_seconds NUMERIC(12,2)
);
"""


def _validate_tax_type(tax_type: str) -> str:
    """Normalise and validate the tax_type parameter."""
    normalized = tax_type.strip().lower()
    if normalized not in _VALID_TAX_TYPES:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tax_type '{tax_type}'. Must be one of: {', '.join(_VALID_TAX_TYPES)}.",
        )
    return normalized


def _validate_missed_filing_run_rate_method(method: str) -> str:
    """Normalise and validate missed-filings run-rate methods."""
    normalized = method.strip().lower()
    if normalized not in _VALID_MISSED_FILING_RUN_RATE_METHODS:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid run_rate_method '{method}'. Must be one of: "
                f"{', '.join(_VALID_MISSED_FILING_RUN_RATE_METHODS)}."
            ),
        )
    return normalized


def _shift_months(value: date, months: int) -> date:
    """Shift a date by whole calendar months, preserving day=1 semantics."""
    zero_based_month = (value.year * 12 + (value.month - 1)) + months
    year = zero_based_month // 12
    month = (zero_based_month % 12) + 1
    return date(year, month, 1)


def _recent_window_bounds(
    start: Optional[date],
    end: Optional[date],
    *,
    months: int = 24,
) -> tuple[date, date]:
    """Clamp query windows to the rolling recent-month window.

    The product requirement is to keep anomaly-style feeds scoped to the
    prior 24 months. When callers omit dates, the current rolling window is
    used; when they provide a broader range, it is clamped.
    """
    from fastapi import HTTPException, status as http_status

    today = date.today()
    window_start = _shift_months(today.replace(day=1), -(months - 1))
    effective_start = max(start or window_start, window_start)
    effective_end = min(end or today, today)

    if effective_end < effective_start:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="end_date must be on or after start_date within the 24-month window.",
        )

    return effective_start, effective_end


def _ensure_missed_filing_candidates_table() -> None:
    """Ensure the missed-filing candidate cache table exists."""
    with get_cursor() as cur:
        cur.execute(_MISSED_FILING_CANDIDATES_DDL)
        cur.execute(_MISSED_FILING_REFRESH_META_DDL)


def ensure_analytics_support_tables() -> None:
    """Initialize analytics-side support tables that are safe to pre-create."""
    _ensure_missed_filing_candidates_table()


def _get_missed_filing_refresh_info() -> MissedFilingsRefreshInfo:
    """Return snapshot metadata for the missed-filings cache."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                last_refresh_at,
                data_min_month,
                data_max_month,
                snapshot_row_count,
                refresh_duration_seconds
            FROM missed_filing_candidates_refresh_meta
            WHERE singleton = TRUE
            """
        )
        row = cur.fetchone()
        if row is not None:
            return MissedFilingsRefreshInfo(
                last_refresh_at=row["last_refresh_at"],
                data_min_month=row["data_min_month"],
                data_max_month=row["data_max_month"],
                snapshot_row_count=int(row["snapshot_row_count"] or 0),
                refresh_duration_seconds=float(row["refresh_duration_seconds"])
                if row["refresh_duration_seconds"] is not None
                else None,
            )

        cur.execute(
            """
            SELECT
                MAX(created_at) AS last_refresh_at,
                MIN(anomaly_date) AS data_min_month,
                MAX(anomaly_date) AS data_max_month,
                COUNT(*) AS snapshot_row_count
            FROM missed_filing_candidates
            """
        )
        fallback = cur.fetchone()

    return MissedFilingsRefreshInfo(
        last_refresh_at=fallback["last_refresh_at"],
        data_min_month=fallback["data_min_month"],
        data_max_month=fallback["data_max_month"],
        snapshot_row_count=int(fallback["snapshot_row_count"] or 0),
    )


# ---------------------------------------------------------------------------
# 1. GET /api/stats/statewide-trend  --  Statewide aggregate time series
# ---------------------------------------------------------------------------

@router.get("/statewide-trend", response_model=StatewideTrendResponse)
def get_statewide_trend(
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    start: Optional[date] = Query(None, description="Start date (inclusive)."),
    end: Optional[date] = Query(None, description="End date (inclusive)."),
) -> StatewideTrendResponse:
    """Return statewide aggregate revenue as a time series.

    Each row is a voucher_date with the total returned across all
    jurisdictions and the count of contributing jurisdictions.
    Month-over-month and year-over-year percentage changes are
    computed via window functions.
    """
    normalized_tax = _validate_tax_type(tax_type)

    where_parts = ["tax_type = %s"]
    params: list[Any] = [normalized_tax]

    if start is not None:
        where_parts.append("voucher_date >= %s")
        params.append(start)
    if end is not None:
        where_parts.append("voucher_date <= %s")
        params.append(end)

    where_sql = " AND ".join(where_parts)

    sql = f"""
        WITH agg AS (
            SELECT
                voucher_date,
                SUM(returned)          AS total_returned,
                COUNT(DISTINCT copo)   AS jurisdiction_count
            FROM ledger_records
            WHERE {where_sql}
            GROUP BY voucher_date
            ORDER BY voucher_date
        )
        SELECT
            voucher_date,
            total_returned,
            jurisdiction_count,
            -- Month-over-month change
            CASE
                WHEN LAG(total_returned) OVER w IS NOT NULL
                     AND LAG(total_returned) OVER w != 0
                THEN ROUND(
                    ((total_returned - LAG(total_returned) OVER w)
                     / ABS(LAG(total_returned) OVER w)) * 100,
                    2
                )
                ELSE NULL
            END AS mom_pct,
            -- Year-over-year change (lag 12 periods)
            CASE
                WHEN LAG(total_returned, 12) OVER w IS NOT NULL
                     AND LAG(total_returned, 12) OVER w != 0
                THEN ROUND(
                    ((total_returned - LAG(total_returned, 12) OVER w)
                     / ABS(LAG(total_returned, 12) OVER w)) * 100,
                    2
                )
                ELSE NULL
            END AS yoy_pct
        FROM agg
        WINDOW w AS (ORDER BY voucher_date ASC)
        ORDER BY voucher_date ASC
    """

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    records = [
        StatewideTrendRecord(
            voucher_date=r["voucher_date"],
            total_returned=float(r["total_returned"]),
            jurisdiction_count=int(r["jurisdiction_count"]),
            mom_pct=float(r["mom_pct"]) if r["mom_pct"] is not None else None,
            yoy_pct=float(r["yoy_pct"]) if r["yoy_pct"] is not None else None,
        )
        for r in rows
    ]

    return StatewideTrendResponse(
        tax_type=normalized_tax,
        records=records,
        count=len(records),
    )


# ---------------------------------------------------------------------------
# 2. GET /api/stats/rankings  --  Rank jurisdictions by metric
# ---------------------------------------------------------------------------

@router.get("/rankings", response_model=RankingsResponse)
def get_rankings(
    tax_type: str = Query("sales", description="Tax type: sales, use, or lodging."),
    metric: str = Query("total_returned", description="Ranking metric: total_returned or yoy_change."),
    limit: int = Query(50, ge=1, le=600, description="Max results to return."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
) -> RankingsResponse:
    """Rank jurisdictions by a chosen metric.

    Supported metrics:
    - ``total_returned`` -- sum of all returned amounts, highest first.
    - ``yoy_change`` -- latest year-over-year percentage change in
      returned, highest first.
    """
    from fastapi import HTTPException, status as http_status

    normalized_tax = _validate_tax_type(tax_type)
    normalized_metric = metric.strip().lower()

    if normalized_metric not in ("total_returned", "yoy_change"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid metric '{metric}'. Must be total_returned or yoy_change.",
        )

    if normalized_metric == "total_returned":
        # Total returned across all time for each jurisdiction
        count_sql = """
            SELECT COUNT(DISTINCT lr.copo) AS total
            FROM ledger_records lr
            WHERE lr.tax_type = %s
        """

        data_sql = """
            SELECT
                ROW_NUMBER() OVER (ORDER BY SUM(lr.returned) DESC) AS rank,
                lr.copo,
                j.name,
                j.county_name,
                j.jurisdiction_type,
                j.population,
                SUM(lr.returned) AS metric_value
            FROM ledger_records lr
            JOIN jurisdictions j ON j.copo = lr.copo
            WHERE lr.tax_type = %s
            GROUP BY lr.copo, j.name, j.county_name, j.jurisdiction_type, j.population
            ORDER BY metric_value DESC
            LIMIT %s OFFSET %s
        """

        with get_cursor() as cur:
            cur.execute(count_sql, (normalized_tax,))
            total = cur.fetchone()["total"]

            cur.execute(data_sql, (normalized_tax, limit, offset))
            rows = cur.fetchall()

    else:
        # yoy_change -- compute latest YoY change per jurisdiction
        # Find each jurisdiction's latest voucher_date that has a value
        # 12 months prior, then compute the change
        count_sql = """
            WITH latest_yoy AS (
                SELECT
                    lr.copo,
                    lr.voucher_date,
                    lr.returned AS current_val,
                    LAG(lr.returned, 12) OVER (
                        PARTITION BY lr.copo ORDER BY lr.voucher_date
                    ) AS prior_val
                FROM ledger_records lr
                WHERE lr.tax_type = %s
            ),
            ranked AS (
                SELECT
                    copo,
                    current_val,
                    prior_val,
                    ROW_NUMBER() OVER (PARTITION BY copo ORDER BY voucher_date DESC) AS rn
                FROM latest_yoy
                WHERE prior_val IS NOT NULL AND prior_val != 0
            )
            SELECT COUNT(*) AS total
            FROM ranked
            WHERE rn = 1
        """

        data_sql = """
            WITH latest_yoy AS (
                SELECT
                    lr.copo,
                    lr.voucher_date,
                    lr.returned AS current_val,
                    LAG(lr.returned, 12) OVER (
                        PARTITION BY lr.copo ORDER BY lr.voucher_date
                    ) AS prior_val
                FROM ledger_records lr
                WHERE lr.tax_type = %s
            ),
            ranked AS (
                SELECT
                    copo,
                    current_val,
                    prior_val,
                    ROW_NUMBER() OVER (PARTITION BY copo ORDER BY voucher_date DESC) AS rn
                FROM latest_yoy
                WHERE prior_val IS NOT NULL AND prior_val != 0
            ),
            yoy_calc AS (
                SELECT
                    copo,
                    ROUND(((current_val - prior_val) / ABS(prior_val)) * 100, 2) AS metric_value
                FROM ranked
                WHERE rn = 1
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY yc.metric_value DESC) AS rank,
                yc.copo,
                j.name,
                j.county_name,
                j.jurisdiction_type,
                j.population,
                yc.metric_value
            FROM yoy_calc yc
            JOIN jurisdictions j ON j.copo = yc.copo
            ORDER BY yc.metric_value DESC
            LIMIT %s OFFSET %s
        """

        with get_cursor() as cur:
            cur.execute(count_sql, (normalized_tax,))
            total = cur.fetchone()["total"]

            cur.execute(data_sql, (normalized_tax, limit, offset))
            rows = cur.fetchall()

    items = [
        RankingItem(
            rank=int(r["rank"]) + offset if normalized_metric == "total_returned" and offset > 0 else int(r["rank"]),
            copo=r["copo"],
            name=r["name"],
            county_name=r["county_name"],
            jurisdiction_type=r["jurisdiction_type"],
            population=int(r["population"]) if r["population"] is not None else None,
            metric_value=float(r["metric_value"]) if r["metric_value"] is not None else None,
        )
        for r in rows
    ]

    # Fix ranks when using offset -- ROW_NUMBER starts from 1 in SQL,
    # but we need to account for pagination offset
    if offset > 0:
        for i, item in enumerate(items):
            item.rank = offset + i + 1

    return RankingsResponse(
        tax_type=normalized_tax,
        metric=normalized_metric,
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# 3. GET /api/stats/naics-sectors  --  Statewide NAICS sector trends
# ---------------------------------------------------------------------------

@router.get("/naics-sectors", response_model=NaicsSectorsResponse)
def get_naics_sectors(
    tax_type: str = Query("sales", description="Tax type: sales or use."),
    limit: int = Query(10, ge=1, le=50, description="Number of top sectors to return."),
) -> NaicsSectorsResponse:
    """Return statewide NAICS sector trends grouped by month.

    Sectors are ranked by their total revenue across all months.
    Each sector includes its monthly breakdown sorted chronologically.
    """
    from fastapi import HTTPException, status as http_status

    normalized_tax = tax_type.strip().lower()
    if normalized_tax not in ("sales", "use"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tax_type '{tax_type}' for NAICS. Must be sales or use.",
        )

    sql = """
        SELECT
            nr.sector,
            ns.sector_name,
            nr.year,
            nr.month,
            SUM(nr.sector_total) AS total
        FROM naics_records nr
        LEFT JOIN naics_sectors ns ON nr.sector = ns.sector
        WHERE nr.tax_type = %s
        GROUP BY nr.sector, ns.sector_name, nr.year, nr.month
        ORDER BY nr.year, nr.month, total DESC
    """

    with get_cursor() as cur:
        cur.execute(sql, (normalized_tax,))
        rows = cur.fetchall()

    # Aggregate into per-sector structures
    sector_data: dict[str, dict[str, Any]] = {}
    sector_grand_total: dict[str, float] = defaultdict(float)

    for r in rows:
        sector_key = r["sector"]
        if sector_key not in sector_data:
            sector_data[sector_key] = {
                "sector": r["sector"],
                "sector_name": r["sector_name"],
                "monthly_data": [],
            }
        total_val = float(r["total"])
        sector_data[sector_key]["monthly_data"].append(
            SectorMonthlyData(
                year=int(r["year"]),
                month=int(r["month"]),
                total=total_val,
            )
        )
        sector_grand_total[sector_key] += total_val

    # Rank sectors by grand total and take the top N
    ranked_sectors = sorted(
        sector_data.keys(),
        key=lambda s: sector_grand_total[s],
        reverse=True,
    )[:limit]

    sectors = [
        NaicsSectorItem(
            sector=sector_data[s]["sector"],
            sector_name=sector_data[s]["sector_name"],
            monthly_data=sector_data[s]["monthly_data"],
        )
        for s in ranked_sectors
    ]

    return NaicsSectorsResponse(
        tax_type=normalized_tax,
        sectors=sectors,
        count=len(sectors),
    )


# ---------------------------------------------------------------------------
# 4. GET /api/stats/anomalies  --  Statewide anomaly feed
# ---------------------------------------------------------------------------

@router.get("/anomalies", response_model=AnomaliesResponse)
def get_anomalies(
    severity: Optional[str] = Query(None, description="Filter by severity: low, medium, high, critical."),
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly type: yoy_spike, yoy_drop, mom_outlier, missing_data, naics_shift."),
    tax_type: Optional[str] = Query(None, description="Filter by tax type: sales, use, lodging."),
    start_date: Optional[date] = Query(None, description="Start date for anomaly_date filter (inclusive)."),
    end_date: Optional[date] = Query(None, description="End date for anomaly_date filter (inclusive)."),
    limit: Optional[int] = Query(None, ge=1, le=100000, description="Optional max results to return."),
) -> AnomaliesResponse:
    """Return detected statewide anomalies from the anomalies table.

    Results are ordered by severity (critical first) then by date
    (most recent first).  Supports filtering by severity, anomaly type,
    tax type, and date range.
    """
    effective_start, effective_end = _recent_window_bounds(start_date, end_date)

    where_parts: list[str] = [
        "a.anomaly_date >= %s",
        "a.anomaly_date <= %s",
    ]
    params: list[Any] = [effective_start, effective_end]

    if severity is not None:
        normalized_sev = severity.strip().lower()
        if normalized_sev not in ("low", "medium", "high", "critical"):
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity '{severity}'. Must be low, medium, high, or critical.",
            )
        where_parts.append("a.severity = %s")
        params.append(normalized_sev)

    if anomaly_type is not None:
        normalized_at = anomaly_type.strip().lower()
        valid_types = ("yoy_spike", "yoy_drop", "mom_outlier", "missing_data", "naics_shift")
        if normalized_at not in valid_types:
            from fastapi import HTTPException, status
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid anomaly_type '{anomaly_type}'. Must be one of: {', '.join(valid_types)}.",
            )
        where_parts.append("a.anomaly_type = %s")
        params.append(normalized_at)

    if tax_type is not None:
        normalized_tax = _validate_tax_type(tax_type)
        where_parts.append("a.tax_type = %s")
        params.append(normalized_tax)

    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    limit_sql = " LIMIT %s" if limit is not None else ""

    sql = f"""
        SELECT
            a.copo,
            j.name AS city_name,
            a.tax_type,
            a.anomaly_date,
            a.anomaly_type,
            a.severity,
            a.expected_value,
            a.actual_value,
            a.deviation_pct,
            a.description
        FROM anomalies a
        JOIN jurisdictions j ON a.copo = j.copo
        {where_sql}
        ORDER BY
            CASE a.severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                WHEN 'low'      THEN 4
                ELSE 5
            END,
            a.anomaly_date DESC
        {limit_sql}
    """
    if limit is not None:
        params.append(limit)

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    items = [
        AnomalyItem(
            copo=r["copo"],
            city_name=r["city_name"],
            tax_type=r["tax_type"],
            anomaly_date=r["anomaly_date"],
            anomaly_type=r["anomaly_type"],
            severity=r["severity"],
            expected_value=float(r["expected_value"]) if r["expected_value"] is not None else None,
            actual_value=float(r["actual_value"]) if r["actual_value"] is not None else None,
            deviation_pct=float(r["deviation_pct"]),
            description=r["description"],
        )
        for r in rows
    ]

    return AnomaliesResponse(items=items, count=len(items))


@router.get("/missed-filings", response_model=MissedFilingsResponse)
def get_missed_filings(
    severity: Optional[str] = Query(None, description="Filter by severity: medium, high, critical."),
    tax_type: Optional[str] = Query(None, description="Filter by tax type: sales or use."),
    city_query: Optional[str] = Query(None, description="Optional case-insensitive city-name search."),
    naics_query: Optional[str] = Query(None, description="Optional NAICS code or description search."),
    run_rate_method: str = Query(
        "hybrid",
        description=(
            "Run-rate baseline method: hybrid, yoy, trailing_mean_3, "
            "trailing_mean_6, trailing_mean_12, trailing_median_12, exp_weighted_12."
        ),
    ),
    sort_by: str = Query(
        "severity",
        description="Sort order: severity, amount, pct, share, date, or city.",
    ),
    start_date: Optional[date] = Query(None, description="Start date for anomaly_date filter (inclusive)."),
    end_date: Optional[date] = Query(None, description="End date for anomaly_date filter (inclusive)."),
    min_expected_value: float = Query(5000, ge=0, description="Minimum expected NAICS revenue to consider."),
    min_missing_amount: float = Query(2500, ge=0, description="Minimum missing dollar amount to flag."),
    min_missing_pct: float = Query(40, ge=0, le=100, description="Minimum missing percent to flag."),
    min_baseline_share_pct: float = Query(2, ge=0, description="Minimum expected share of the city's tax base."),
    high_missing_amount: float = Query(10000, ge=0, description="High-severity dollar threshold."),
    high_missing_pct: float = Query(60, ge=0, le=100, description="High-severity percent threshold."),
    critical_missing_amount: float = Query(25000, ge=0, description="Critical-severity dollar threshold."),
    critical_missing_pct: float = Query(85, ge=0, le=100, description="Critical-severity percent threshold."),
    limit: int = Query(100, ge=1, le=1000, description="Page size for missed-filing candidates."),
    offset: int = Query(0, ge=0, description="Pagination offset for missed-filing candidates."),
) -> MissedFilingsResponse:
    """Return statewide NAICS-level missed filing candidates.

    This feed is a directional tool for finance staff. It identifies
    six-digit NAICS categories whose current month revenue is far below
    an expected run rate, suggesting a likely missing filer rather than
    a broad-based slowdown. The cache covers the rolling 24-month window
    exhaustively for analyzable city/month/code combinations, then
    applies the selected run-rate method and severity thresholds at
    request time.
    """
    from fastapi import HTTPException, status as http_status

    effective_start, effective_end = _recent_window_bounds(start_date, end_date)

    normalized_tax: Optional[str] = None
    if tax_type is not None:
        normalized_tax = _validate_tax_type(tax_type)
        if normalized_tax not in ("sales", "use"):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Missed filings are only available for sales and use tax because lodging has no NAICS industry feed.",
            )

    normalized_severity: Optional[str] = None
    if severity is not None:
        normalized_severity = severity.strip().lower()
        if normalized_severity not in ("medium", "high", "critical"):
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Invalid severity. Must be medium, high, or critical.",
            )

    normalized_method = _validate_missed_filing_run_rate_method(run_rate_method)
    normalized_sort = sort_by.strip().lower()
    if normalized_sort not in _VALID_MISSED_FILING_SORT_OPTIONS:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid sort_by '{sort_by}'. Must be one of: "
                f"{', '.join(_VALID_MISSED_FILING_SORT_OPTIONS)}."
            ),
        )

    if not (min_missing_amount <= high_missing_amount <= critical_missing_amount):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing-amount thresholds must satisfy min <= high <= critical.",
        )

    if not (min_missing_pct <= high_missing_pct <= critical_missing_pct):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Missing-percent thresholds must satisfy min <= high <= critical.",
        )

    where_parts = [
        "c.tax_type IN ('sales', 'use')",
        "c.anomaly_date >= %s",
        "c.anomaly_date <= %s",
    ]
    params: list[Any] = [effective_start, effective_end]

    if normalized_tax is not None:
        where_parts.append("c.tax_type = %s")
        params.append(normalized_tax)

    where_sql = " AND ".join(where_parts)
    search_where_parts: list[str] = []
    search_params: list[Any] = []
    if normalized_severity is not None:
        search_where_parts.append("severity = %s")
        search_params.append(normalized_severity)
    if city_query is not None and city_query.strip():
        search_where_parts.append("city_name ILIKE %s")
        search_params.append(f"%{city_query.strip()}%")
    if naics_query is not None and naics_query.strip():
        search_where_parts.append("(activity_code ILIKE %s OR activity_description ILIKE %s)")
        search_term = f"%{naics_query.strip()}%"
        search_params.extend([search_term, search_term])
    search_where_sql = ("WHERE " + " AND ".join(search_where_parts)) if search_where_parts else ""
    order_by_sql_map = {
        "severity": """
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            missing_amount DESC,
            anomaly_date DESC,
            city_name ASC
        """,
        "amount": "missing_amount DESC, anomaly_date DESC, city_name ASC",
        "pct": "missing_pct DESC, missing_amount DESC, anomaly_date DESC",
        "share": "baseline_share_pct DESC, missing_amount DESC, anomaly_date DESC",
        "date": "anomaly_date DESC, missing_amount DESC, city_name ASC",
        "city": "city_name ASC, anomaly_date DESC, missing_amount DESC",
    }
    order_by_sql = order_by_sql_map[normalized_sort]

    run_rate_expression_map = {
        "hybrid": "c.hybrid_expected_value",
        "yoy": "c.prior_year_value",
        "trailing_mean_3": "CASE WHEN c.trailing_count_3 >= 2 THEN c.trailing_mean_3 ELSE NULL END",
        "trailing_mean_6": "CASE WHEN c.trailing_count_6 >= 3 THEN c.trailing_mean_6 ELSE NULL END",
        "trailing_mean_12": "CASE WHEN c.trailing_count_12 >= 6 THEN c.trailing_mean_12 ELSE NULL END",
        "trailing_median_12": "CASE WHEN c.trailing_count_12 >= 6 THEN c.trailing_median_12 ELSE NULL END",
        "exp_weighted_12": "CASE WHEN c.trailing_count_12 >= 6 THEN c.exp_weighted_avg_12 ELSE NULL END",
    }
    baseline_months_used_map = {
        "hybrid": "COALESCE(c.hybrid_baseline_months_used, 0)",
        "yoy": "CASE WHEN c.prior_year_value IS NOT NULL THEN 1 ELSE 0 END",
        "trailing_mean_3": "COALESCE(c.trailing_count_3, 0)",
        "trailing_mean_6": "COALESCE(c.trailing_count_6, 0)",
        "trailing_mean_12": "COALESCE(c.trailing_count_12, 0)",
        "trailing_median_12": "COALESCE(c.trailing_count_12, 0)",
        "exp_weighted_12": "COALESCE(c.trailing_count_12, 0)",
    }

    run_rate_expression = run_rate_expression_map[normalized_method]
    baseline_months_expression = baseline_months_used_map[normalized_method]
    city_run_rate_expression_map = {
        "hybrid": "c.hybrid_city_expected_total",
        "yoy": "c.city_prior_year_total",
        "trailing_mean_3": "CASE WHEN c.city_trailing_count_3 >= 2 THEN c.city_trailing_mean_3 ELSE NULL END",
        "trailing_mean_6": "CASE WHEN c.city_trailing_count_6 >= 3 THEN c.city_trailing_mean_6 ELSE NULL END",
        "trailing_mean_12": "CASE WHEN c.city_trailing_count_12 >= 6 THEN c.city_trailing_mean_12 ELSE NULL END",
        "trailing_median_12": "CASE WHEN c.city_trailing_count_12 >= 6 THEN c.city_trailing_median_12 ELSE NULL END",
        "exp_weighted_12": "CASE WHEN c.city_trailing_count_12 >= 6 THEN c.city_exp_weighted_avg_12 ELSE NULL END",
    }
    city_run_rate_expression = city_run_rate_expression_map[normalized_method]

    if normalized_method == "hybrid":
        missing_amount_expression = "s.hybrid_missing_amount"
        missing_pct_expression = "s.hybrid_missing_pct"
        baseline_share_expression = "s.hybrid_baseline_share_pct"
    else:
        missing_amount_expression = "ROUND(s.expected_value - s.actual_value, 2)"
        missing_pct_expression = """
            ROUND(
                ((s.expected_value - s.actual_value) / NULLIF(ABS(s.expected_value), 0)) * 100,
                2
            )
        """
        baseline_share_expression = """
            LEAST(
                100.00,
                ROUND((s.expected_value / NULLIF(s.city_expected_total, 0)) * 100, 2)
            )
        """

    is_hybrid_default_floor = (
        normalized_method == "hybrid"
        and min_expected_value == 5000
        and min_missing_amount == 2500
        and min_missing_pct == 40
        and min_baseline_share_pct == 2
    )

    if is_hybrid_default_floor:
        fast_where_parts = [
            "c.tax_type IN ('sales', 'use')",
            "c.anomaly_date >= %s",
            "c.anomaly_date <= %s",
            "c.hybrid_expected_value IS NOT NULL",
            "c.hybrid_city_expected_total IS NOT NULL",
            "c.hybrid_city_expected_total > 0",
            "COALESCE(c.hybrid_baseline_months_used, 0) > 0",
            "c.hybrid_expected_value >= 5000",
            "c.hybrid_missing_amount >= 2500",
            "c.hybrid_missing_pct >= 40",
            "c.hybrid_baseline_share_pct >= 2",
        ]
        fast_params: list[Any] = [effective_start, effective_end]
        if normalized_tax is not None:
            fast_where_parts.append("c.tax_type = %s")
            fast_params.append(normalized_tax)
        if city_query is not None and city_query.strip():
            fast_where_parts.append("c.city_name ILIKE %s")
            fast_params.append(f"%{city_query.strip()}%")
        if naics_query is not None and naics_query.strip():
            fast_where_parts.append("(c.activity_code ILIKE %s OR c.activity_description ILIKE %s)")
            search_term = f"%{naics_query.strip()}%"
            fast_params.extend([search_term, search_term])

        severity_sql = ""
        if normalized_severity is not None:
            severity_sql = "WHERE severity = %s"
            fast_params.append(normalized_severity)

        fast_sql = f"""
            WITH filtered AS (
                SELECT
                    c.copo,
                    c.city_name,
                    c.tax_type,
                    c.anomaly_date,
                    c.activity_code,
                    c.activity_description,
                    'hybrid' AS baseline_method,
                    COALESCE(c.hybrid_baseline_months_used, 0) AS baseline_months_used,
                    ROUND(c.prior_year_value, 2) AS prior_year_value,
                    ROUND(c.trailing_mean_3, 2) AS trailing_mean_3,
                    ROUND(c.trailing_mean_6, 2) AS trailing_mean_6,
                    ROUND(c.trailing_mean_12, 2) AS trailing_mean_12,
                    ROUND(c.trailing_median_12, 2) AS trailing_median_12,
                    ROUND(c.exp_weighted_avg_12, 2) AS exp_weighted_avg_12,
                    ROUND(c.hybrid_expected_value, 2) AS expected_value,
                    ROUND(c.actual_value, 2) AS actual_value,
                    ROUND(c.hybrid_missing_amount, 2) AS missing_amount,
                    ROUND(c.hybrid_missing_pct, 2) AS missing_pct,
                    ROUND(c.hybrid_baseline_share_pct, 2) AS baseline_share_pct,
                    CASE
                        WHEN c.hybrid_missing_amount >= %s
                          OR c.hybrid_missing_pct >= %s
                            THEN 'critical'
                        WHEN c.hybrid_missing_amount >= %s
                          OR c.hybrid_missing_pct >= %s
                            THEN 'high'
                        ELSE 'medium'
                    END AS severity
                FROM missed_filing_candidates c
                WHERE {" AND ".join(fast_where_parts)}
            )
            SELECT
                copo,
                city_name,
                tax_type,
                anomaly_date,
                activity_code,
                activity_description,
                baseline_method,
                baseline_months_used,
                prior_year_value,
                trailing_mean_3,
                trailing_mean_6,
                trailing_mean_12,
                trailing_median_12,
                exp_weighted_avg_12,
                expected_value,
                actual_value,
                missing_amount,
                missing_pct,
                baseline_share_pct,
                severity
            FROM filtered
            {severity_sql}
            ORDER BY {order_by_sql}
            LIMIT %s
            OFFSET %s
        """

        with get_cursor() as cur:
            cur.execute(
                fast_sql,
                [
                    critical_missing_amount,
                    critical_missing_pct,
                    high_missing_amount,
                    high_missing_pct,
                    *fast_params,
                    limit + 1,
                    offset,
                ],
            )
            rows = cur.fetchall()
    else:
        sql = f"""
            WITH scored AS (
                SELECT
                    c.copo,
                    c.city_name,
                    c.tax_type,
                    c.anomaly_date,
                    c.activity_code,
                    c.activity_description,
                    c.city_total,
                    c.prior_year_value,
                    c.trailing_mean_3,
                    c.trailing_count_3,
                    c.trailing_mean_6,
                    c.trailing_count_6,
                    c.trailing_mean_12,
                    c.trailing_count_12,
                    c.trailing_median_12,
                    c.exp_weighted_avg_12,
                    c.actual_value,
                    c.city_prior_year_total,
                    c.city_trailing_mean_3,
                    c.city_trailing_count_3,
                    c.city_trailing_mean_6,
                    c.city_trailing_count_6,
                    c.city_trailing_mean_12,
                    c.city_trailing_count_12,
                    c.city_trailing_median_12,
                    c.city_exp_weighted_avg_12,
                    c.hybrid_missing_amount,
                    c.hybrid_missing_pct,
                    c.hybrid_baseline_share_pct,
                    '{normalized_method}' AS baseline_method,
                    ({run_rate_expression})::numeric AS expected_value,
                    ({city_run_rate_expression})::numeric AS city_expected_total,
                    ({baseline_months_expression})::int AS baseline_months_used
                FROM missed_filing_candidates c
                WHERE {where_sql}
            ),
            filtered AS (
                SELECT
                    s.copo,
                    s.city_name,
                    s.tax_type,
                    s.anomaly_date,
                    s.activity_code,
                    s.activity_description,
                    s.baseline_method,
                    s.baseline_months_used,
                    ROUND(s.prior_year_value, 2) AS prior_year_value,
                    ROUND(s.trailing_mean_3, 2) AS trailing_mean_3,
                    ROUND(s.trailing_mean_6, 2) AS trailing_mean_6,
                    ROUND(s.trailing_mean_12, 2) AS trailing_mean_12,
                    ROUND(s.trailing_median_12, 2) AS trailing_median_12,
                    ROUND(s.exp_weighted_avg_12, 2) AS exp_weighted_avg_12,
                    ROUND(s.expected_value, 2) AS expected_value,
                    ROUND(s.actual_value, 2) AS actual_value,
                    {missing_amount_expression} AS missing_amount,
                    {missing_pct_expression} AS missing_pct,
                    {baseline_share_expression} AS baseline_share_pct,
                    CASE
                        WHEN ({missing_amount_expression}) >= %s
                          OR ({missing_pct_expression}) >= %s
                            THEN 'critical'
                        WHEN ({missing_amount_expression}) >= %s
                          OR ({missing_pct_expression}) >= %s
                            THEN 'high'
                        ELSE 'medium'
                    END AS severity
                FROM scored s
                WHERE s.expected_value IS NOT NULL
                  AND s.city_expected_total IS NOT NULL
                  AND s.city_expected_total > 0
                  AND s.baseline_months_used > 0
                  AND s.expected_value >= %s
                  AND ({missing_amount_expression}) >= %s
                  AND ({missing_pct_expression}) >= %s
                  AND ({baseline_share_expression}) >= %s
            ),
            searched AS (
                SELECT *
                FROM filtered
                {search_where_sql}
            )
            SELECT
                copo,
                city_name,
                tax_type,
                anomaly_date,
                activity_code,
                activity_description,
                baseline_method,
                baseline_months_used,
                prior_year_value,
                trailing_mean_3,
                trailing_mean_6,
                trailing_mean_12,
                trailing_median_12,
                exp_weighted_avg_12,
                expected_value,
                actual_value,
                missing_amount,
                missing_pct,
                baseline_share_pct,
                severity
            FROM searched
            ORDER BY {order_by_sql}
            LIMIT %s
            OFFSET %s
        """

        params.extend(
            [
                critical_missing_amount,
                critical_missing_pct,
                high_missing_amount,
                high_missing_pct,
                min_expected_value,
                min_missing_amount,
                min_missing_pct,
                min_baseline_share_pct,
            ]
        )
        params.extend(search_params)
        params.extend([limit + 1, offset])

        with get_cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    method_label = _MISSED_FILING_METHOD_LABELS[normalized_method]
    refresh_info = _get_missed_filing_refresh_info()

    def _format_money(value: float) -> str:
        return f"${value:,.0f}"

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    items = [
        MissedFilingItem(
            copo=row["copo"],
            city_name=row["city_name"],
            tax_type=row["tax_type"],
            anomaly_date=row["anomaly_date"],
            activity_code=row["activity_code"],
            activity_description=row["activity_description"],
            baseline_method=row["baseline_method"],
            baseline_months_used=row["baseline_months_used"],
            prior_year_value=float(row["prior_year_value"]) if row["prior_year_value"] is not None else None,
            trailing_mean_3=float(row["trailing_mean_3"]) if row["trailing_mean_3"] is not None else None,
            trailing_mean_6=float(row["trailing_mean_6"]) if row["trailing_mean_6"] is not None else None,
            trailing_mean_12=float(row["trailing_mean_12"]) if row["trailing_mean_12"] is not None else None,
            trailing_median_12=float(row["trailing_median_12"]) if row["trailing_median_12"] is not None else None,
            exp_weighted_avg_12=float(row["exp_weighted_avg_12"]) if row["exp_weighted_avg_12"] is not None else None,
            expected_value=float(row["expected_value"]),
            actual_value=float(row["actual_value"]),
            missing_amount=float(row["missing_amount"]),
            missing_pct=float(row["missing_pct"]),
            baseline_share_pct=float(row["baseline_share_pct"]),
            severity=row["severity"],
            recommendation=(
                f"Investigate NAICS {row['activity_code']} ({row['activity_description']}) "
                f"for {row['tax_type']} tax in {row['anomaly_date']:%b %Y}. "
                f"{method_label} expects about {_format_money(float(row['expected_value']))}; "
                f"observed {_format_money(float(row['actual_value']))}, leaving an estimated "
                f"{_format_money(float(row['missing_amount']))} gap ({float(row['missing_pct']):.1f}% missing)."
            ),
        )
        for row in page_rows
    ]

    return MissedFilingsResponse(
        items=items,
        count=len(items),
        total=offset + len(items) + (1 if has_more else 0),
        limit=limit,
        offset=offset,
        has_more=has_more,
        refresh_info=refresh_info,
    )
