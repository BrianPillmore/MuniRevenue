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
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.cities import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["analytics"])


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TAX_TYPES = ("sales", "use", "lodging")


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
    anomaly_type: Optional[str] = Query(None, description="Filter by anomaly type: yoy_spike, yoy_drop, mom_outlier, missing_data."),
    tax_type: Optional[str] = Query(None, description="Filter by tax type: sales, use, lodging."),
    limit: int = Query(50, ge=1, le=500, description="Max results to return."),
) -> AnomaliesResponse:
    """Return detected statewide anomalies from the anomalies table.

    Results are ordered by severity (critical first) then by date
    (most recent first).  Supports filtering by severity, anomaly type,
    and tax type.
    """
    where_parts: list[str] = []
    params: list[Any] = []

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
        valid_types = ("yoy_spike", "yoy_drop", "mom_outlier", "missing_data")
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
        LIMIT %s
    """
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
