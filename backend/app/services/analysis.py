from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Optional

import numpy as np
import pandas as pd

from app.schemas import AnalysisResponse, AnovaResult, ChangeRow, ForecastPoint, SeasonalRow, SummaryMetrics

try:
    from scipy.stats import f as scipy_f_distribution
except Exception:  # pragma: no cover - optional dependency fallback
    scipy_f_distribution = None


DISPLAY_START_YEAR = 2022
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


class InputDataError(ValueError):
    """Raised when the uploaded spreadsheet cannot be interpreted."""


@dataclass(frozen=True)
class CanonicalColumns:
    voucher_date: str
    returned: str


def analyze_excel_bytes(file_bytes: bytes) -> AnalysisResponse:
    frame = pd.read_excel(BytesIO(file_bytes))
    tax_data = canonicalize_tax_data(frame)
    return build_analysis(tax_data)


def canonicalize_tax_data(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        raise InputDataError("The uploaded spreadsheet is empty.")

    columns = detect_columns(frame)
    data = frame.rename(
        columns={
            columns.voucher_date: "voucher_date",
            columns.returned: "returned",
        }
    )[["voucher_date", "returned"]].copy()

    data["voucher_date"] = pd.to_datetime(data["voucher_date"], errors="coerce")
    data["returned"] = pd.to_numeric(data["returned"], errors="coerce")
    data = data.dropna(subset=["voucher_date", "returned"]).sort_values("voucher_date").reset_index(drop=True)

    if data.empty:
        raise InputDataError(
            "No valid date and numeric records were found. Expected one date column and one revenue column."
        )

    return data


def detect_columns(frame: pd.DataFrame) -> CanonicalColumns:
    lowered = {str(column).strip().lower(): column for column in frame.columns}

    named_date = next((lowered[key] for key in lowered if "date" in key), None)
    named_amount = next(
        (lowered[key] for key in lowered if any(token in key for token in ("returned", "amount", "revenue", "sales"))),
        None,
    )

    voucher_date = named_date or first_date_like_column(frame)
    returned = named_amount or first_numeric_like_column(frame)

    if voucher_date is None or returned is None:
        raise InputDataError("Unable to detect the spreadsheet's date and revenue columns.")

    return CanonicalColumns(voucher_date=voucher_date, returned=returned)


def first_date_like_column(frame: pd.DataFrame) -> Optional[str]:
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            return str(column)
        parsed = pd.to_datetime(series, errors="coerce")
        if parsed.notna().mean() >= 0.8:
            return str(column)
    return None


def first_numeric_like_column(frame: pd.DataFrame) -> Optional[str]:
    for column in frame.columns:
        series = frame[column]
        if pd.api.types.is_numeric_dtype(series):
            return str(column)
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().mean() >= 0.8:
            return str(column)
    return None


def build_analysis(data: pd.DataFrame) -> AnalysisResponse:
    change_rows = build_monthly_changes(data)
    display_data = data[data["voucher_date"].dt.year >= DISPLAY_START_YEAR].copy()
    display_source = display_data if not display_data.empty else data

    summary = build_summary(change_rows, data)
    seasonality = build_seasonality(display_source)
    anova = build_anova(display_source)
    forecast = build_forecast(display_source)
    highlights = build_highlights(change_rows, seasonality, forecast, anova)

    return AnalysisResponse(
        summary=summary,
        monthly_changes=change_rows,
        seasonality=seasonality,
        anova=anova,
        forecast=forecast,
        highlights=highlights,
    )


def build_summary(change_rows: list[ChangeRow], data: pd.DataFrame) -> SummaryMetrics:
    latest = change_rows[-1]
    return SummaryMetrics(
        records=int(len(data)),
        first_date=data["voucher_date"].min().date().isoformat(),
        last_date=data["voucher_date"].max().date().isoformat(),
        average_returned=round(float(data["returned"].mean()), 2),
        latest_returned=round(float(data["returned"].iloc[-1]), 2),
        latest_mom_pct=round_nullable(latest.mom_pct),
        latest_yoy_pct=round_nullable(latest.yoy_pct),
    )


def build_monthly_changes(data: pd.DataFrame) -> list[ChangeRow]:
    change_frame = data.copy()
    change_frame["mom_pct"] = change_frame["returned"].pct_change() * 100
    change_frame["yoy_pct"] = change_frame["returned"].pct_change(12) * 100

    display_frame = change_frame[change_frame["voucher_date"].dt.year >= DISPLAY_START_YEAR].copy()
    if display_frame.empty:
        display_frame = change_frame

    rows: list[ChangeRow] = []
    for row in display_frame.itertuples(index=False):
        rows.append(
            ChangeRow(
                voucher_date=row.voucher_date.date().isoformat(),
                returned=round(float(row.returned), 2),
                mom_pct=round_nullable(row.mom_pct),
                yoy_pct=round_nullable(row.yoy_pct),
            )
        )
    return rows


def build_seasonality(data: pd.DataFrame) -> list[SeasonalRow]:
    seasonal = data.copy()
    seasonal["month_number"] = seasonal["voucher_date"].dt.month
    rows: list[SeasonalRow] = []

    for month_number, month_name in enumerate(MONTH_NAMES, start=1):
        slice_frame = seasonal[seasonal["month_number"] == month_number]
        if slice_frame.empty:
            continue

        rows.append(
            SeasonalRow(
                month=month_name,
                observations=int(len(slice_frame)),
                mean_returned=round(float(slice_frame["returned"].mean()), 2),
                median_returned=round(float(slice_frame["returned"].median()), 2),
                min_returned=round(float(slice_frame["returned"].min()), 2),
                max_returned=round(float(slice_frame["returned"].max()), 2),
            )
        )

    return rows


def build_anova(data: pd.DataFrame) -> AnovaResult:
    groups = [group["returned"].to_numpy(dtype=float) for _, group in data.groupby(data["voucher_date"].dt.month)]
    groups = [group for group in groups if len(group) > 0]

    if len(groups) < 2:
        return AnovaResult(
            interpretation="Not enough month groups were available to run ANOVA.",
            note="Upload at least two months of observations to compare seasonal differences.",
        )

    counts = [len(group) for group in groups]
    grand_total = sum(group.sum() for group in groups)
    grand_count = sum(counts)
    grand_mean = grand_total / grand_count

    ss_between = sum(len(group) * float((group.mean() - grand_mean) ** 2) for group in groups)
    ss_within = sum(float(((group - group.mean()) ** 2).sum()) for group in groups)

    df_between = len(groups) - 1
    df_within = grand_count - len(groups)

    if df_within <= 0 or ss_within == 0:
        return AnovaResult(
            interpretation="Monthly values did not vary enough to produce a stable ANOVA result.",
            note="The within-group variance was effectively zero.",
        )

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within
    f_statistic = ms_between / ms_within if ms_within else None
    p_value = None

    if scipy_f_distribution is not None and f_statistic is not None:
        p_value = float(scipy_f_distribution.sf(f_statistic, df_between, df_within))

    significant = None if p_value is None else p_value < 0.05
    interpretation = (
        "Monthly average returns differ enough to suggest seasonality."
        if significant
        else "Monthly averages do not show strong evidence of seasonality at the 5% level."
    )
    if p_value is None:
        interpretation = (
            "ANOVA was computed, but SciPy is not installed so the exact p-value could not be calculated locally."
        )

    return AnovaResult(
        f_statistic=round_nullable(f_statistic),
        p_value=round_nullable(p_value, digits=4),
        significant=significant,
        interpretation=interpretation,
        note="Install SciPy to enable the exact ANOVA significance test." if p_value is None else None,
    )


def build_forecast(data: pd.DataFrame) -> list[ForecastPoint]:
    if len(data) < 6:
        return []

    working = data.copy()
    working["business_month"] = (working["voucher_date"] - pd.DateOffset(months=2)).dt.to_period("M").dt.to_timestamp()
    working["business_days"] = working["business_month"].dt.days_in_month
    working["normalized"] = working["returned"] / working["business_days"] * 30
    working["month_number"] = working["business_month"].dt.month

    overall_norm = float(working["normalized"].mean())
    seasonal_baseline = working.groupby("month_number")["normalized"].mean() / overall_norm
    seasonal_factors = seasonal_baseline.replace(0, 1).reindex(range(1, 13)).fillna(1.0)

    working["seasonal_factor"] = working["month_number"].map(seasonal_factors)
    working["deseasonalized"] = working["normalized"] / working["seasonal_factor"]

    timeline = np.arange(len(working), dtype=float)
    if len(working) == 1:
        intercept = float(working["deseasonalized"].iloc[0])
        slope = 0.0
    else:
        slope, intercept = np.polyfit(timeline, working["deseasonalized"].to_numpy(dtype=float), 1)

    fitted = intercept + slope * timeline
    residuals = working["deseasonalized"].to_numpy(dtype=float) - fitted
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0

    future_business_months = pd.date_range(
        start=working["business_month"].max() + pd.offsets.MonthBegin(1),
        periods=12,
        freq="MS",
    )
    future_index = np.arange(len(working), len(working) + len(future_business_months), dtype=float)
    trend_forecast = intercept + slope * future_index

    forecast_rows: list[ForecastPoint] = []
    for idx, business_month in enumerate(future_business_months):
        month_number = int(business_month.month)
        seasonal_factor = float(seasonal_factors.loc[month_number])
        basis_month = MONTH_NAMES[month_number - 1]
        normalized_projection = max(float(trend_forecast[idx]) * seasonal_factor, 0.0)
        lower_normalized = max(normalized_projection - 1.96 * residual_std, 0.0)
        upper_normalized = max(normalized_projection + 1.96 * residual_std, 0.0)

        business_days = int(business_month.days_in_month)
        receipt_month = business_month + pd.DateOffset(months=2)

        forecast_rows.append(
            ForecastPoint(
                date=receipt_month.date().isoformat(),
                projected_returned=round(normalized_projection / 30 * business_days, 2),
                lower_bound=round(lower_normalized / 30 * business_days, 2),
                upper_bound=round(upper_normalized / 30 * business_days, 2),
                basis_month=basis_month,
            )
        )

    return forecast_rows


def build_highlights(
    change_rows: list[ChangeRow],
    seasonality: list[SeasonalRow],
    forecast: list[ForecastPoint],
    anova: AnovaResult,
) -> list[str]:
    highlights: list[str] = []

    mom_candidates = [row for row in change_rows if row.mom_pct is not None]
    yoy_candidates = [row for row in change_rows if row.yoy_pct is not None]

    if mom_candidates:
        strongest_mom = max(mom_candidates, key=lambda row: abs(row.mom_pct or 0))
        direction = "increase" if (strongest_mom.mom_pct or 0) >= 0 else "decrease"
        highlights.append(
            f"The sharpest month-over-month {direction} was {strongest_mom.mom_pct:.2f}% in {strongest_mom.voucher_date}."
        )

    if yoy_candidates:
        latest_yoy = yoy_candidates[-1]
        highlights.append(f"The most recent year-over-year change is {latest_yoy.yoy_pct:.2f}% for {latest_yoy.voucher_date}.")

    if seasonality:
        strongest_month = max(seasonality, key=lambda row: row.mean_returned)
        highlights.append(
            f"{strongest_month.month} has the highest average returned value at ${strongest_month.mean_returned:,.0f}."
        )

    if forecast:
        first_forecast = forecast[0]
        highlights.append(
            "The next projected filing month is "
            f"{first_forecast.date} with an expected return of ${first_forecast.projected_returned:,.0f}."
        )

    highlights.append(anova.interpretation)
    highlights.append(
        "Forecasts are produced from a seasonally adjusted trend model that normalizes each business month to 30 days."
    )
    return highlights


def round_nullable(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)
