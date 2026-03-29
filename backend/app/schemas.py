from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class SummaryMetrics(BaseModel):
    records: int
    first_date: str
    last_date: str
    average_returned: float
    latest_returned: float
    latest_mom_pct: Optional[float] = None
    latest_yoy_pct: Optional[float] = None


class ChangeRow(BaseModel):
    voucher_date: str
    returned: float
    mom_pct: Optional[float] = None
    yoy_pct: Optional[float] = None


class SeasonalRow(BaseModel):
    month: str
    observations: int
    mean_returned: float
    median_returned: float
    min_returned: float
    max_returned: float


class AnovaResult(BaseModel):
    f_statistic: Optional[float] = None
    p_value: Optional[float] = None
    significant: Optional[bool] = None
    interpretation: str
    note: Optional[str] = None


class ForecastPoint(BaseModel):
    date: str
    projected_returned: float
    lower_bound: float
    upper_bound: float
    basis_month: str = Field(description="Month used for seasonal normalization.")


class AnalysisResponse(BaseModel):
    summary: SummaryMetrics
    monthly_changes: list[ChangeRow]
    seasonality: list[SeasonalRow]
    anova: AnovaResult
    forecast: list[ForecastPoint]
    highlights: list[str]
