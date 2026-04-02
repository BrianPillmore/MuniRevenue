// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const getCityDetail = vi.fn();
const getCityForecast = vi.fn();
const getForecastPreferences = vi.fn();
const getCityLedger = vi.fn();
const getCityNaicsTop = vi.fn();
const getIndustryTimeSeries = vi.fn();
const updateForecastPreferences = vi.fn();
const renderCitySearch = vi.fn(() => () => undefined);
const renderTaxToggle = vi.fn();
const showLoading = vi.fn();
const navigateTo = vi.fn();
const setPageMetadata = vi.fn();
const chartDestroy = vi.fn();
const chart = vi.fn(() => ({ destroy: chartDestroy }));

vi.mock("../api", () => ({
  getCityDetail,
  getCityForecast,
  getForecastPreferences,
  getCityLedger,
  getCityNaicsTop,
  getIndustryTimeSeries,
  updateForecastPreferences,
}));

vi.mock("../components/city-search", () => ({
  renderCitySearch,
}));

vi.mock("../components/loading", () => ({
  showLoading,
}));

vi.mock("../components/tax-toggle", () => ({
  renderTaxToggle,
}));

vi.mock("../router", () => ({
  navigateTo,
}));

vi.mock("../seo", () => ({
  setPageMetadata,
}));

vi.mock("../theme", () => ({
  default: {
    chart,
  },
}));

function flushPromises(): Promise<void> {
  return Promise.resolve().then(() => Promise.resolve()).then(() => Promise.resolve());
}

function makeForecastResponse() {
  return {
    copo: "0955",
    tax_type: "sales",
    model: "ensemble",
    forecasts: [
      {
        target_date: "2026-04-30",
        projected_value: 1234,
        lower_bound: 1111,
        upper_bound: 1350,
      },
    ],
    selected_model: "ensemble",
    requested_model: "ensemble",
    eligible_models: ["ensemble"],
    forecast_points: [
      {
        target_date: "2026-04-30",
        projected_value: 1234,
        lower_bound: 1111,
        upper_bound: 1350,
      },
    ],
    backtest_summary: {
      mape: 3.2,
      smape: 2.1,
      mae: 100,
    },
    model_comparison: [
      {
        model: "ensemble",
        selected: true,
        status: "ready",
        backtest: {
          mape: 3.2,
          smape: 2.1,
          mae: 100,
        },
        uses_indicators: true,
        reason: "Best fit for this series",
      },
    ],
    explainability: {
      selected_model_reason: "The ensemble is the strongest configured option.",
      trend_summary: "Revenue has been growing steadily.",
      seasonality_summary: "Seasonality is moderate and stable.",
      confidence_summary: "Confidence is solid.",
      holiday_summary: "No major holiday effect detected.",
      indicator_summary: "Balanced indicator profile is in use.",
      industry_mix_summary: "Industrial mix is broad and stable.",
      caveats: [],
      indicator_drivers: [
        {
          family: "economic",
          geography_scope: "state",
          source_name: "BLS",
        },
      ],
      top_industry_drivers: [
        {
          activity_code: "0114",
          activity_description: "Broilers and chickens",
          share_pct: 12.3,
          trailing_12_total: 10000,
        },
      ],
    },
    data_quality: {
      observation_count: 12,
      expected_months: 12,
      missing_month_count: 0,
      latest_observation: "2026-03-31",
      advanced_models_allowed: true,
      warnings: [],
    },
    series_scope: "naics",
    activity_code: "0114",
    activity_description: "Broilers and chickens",
    horizon_months: 24,
    lookback_months: 48,
    confidence_level: 0.9,
    indicator_profile: "balanced",
  };
}

describe("forecastView", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/forecast/0955");

    getForecastPreferences.mockResolvedValue({
      default_city_copo: "0955",
      default_tax_type: "sales",
      forecast_model: "ensemble",
      forecast_horizon_months: 24,
      forecast_lookback_months: 48,
      forecast_confidence_level: 0.9,
      forecast_indicator_profile: "balanced",
      forecast_scope: "naics",
      forecast_activity_code: "0114",
    });
    getCityDetail.mockResolvedValue({
      copo: "0955",
      name: "Norman",
      jurisdiction_type: "City",
      county_name: "Cleveland",
      population: 128026,
      tax_type_summaries: [{ tax_type: "sales" }],
      naics_record_count: 1,
      naics_earliest_year_month: 202401,
      naics_latest_year_month: 202503,
    });
    getCityNaicsTop.mockResolvedValue({
      copo: "0955",
      tax_type: "sales",
      records: [
        {
          activity_code: "0114",
          activity_description: "Broilers and chickens",
          sector: "Agriculture",
          tax_rate: 1,
          sector_total: 1000,
          year_to_date: 1000,
        },
      ],
      count: 1,
    });
    getIndustryTimeSeries.mockResolvedValue({
      copo: "0955",
      activity_code: "0114",
      activity_description: "Broilers and chickens",
      tax_type: "sales",
      records: [
        {
          year: 2025,
          month: 12,
          sector_total: 1000,
        },
      ],
      count: 1,
    });
    getCityLedger.mockResolvedValue({
      copo: "0955",
      tax_type: "sales",
      records: [],
      count: 0,
    });
    getCityForecast.mockResolvedValue(makeForecastResponse());
    updateForecastPreferences.mockResolvedValue({
      default_city_copo: "0955",
      default_tax_type: "sales",
      forecast_model: "ensemble",
      forecast_horizon_months: 24,
      forecast_lookback_months: 48,
      forecast_confidence_level: 0.9,
      forecast_indicator_profile: "balanced",
      forecast_scope: "naics",
      forecast_activity_code: "0114",
    });
  });

  it("loads saved defaults and persists the current forecast settings as the user's defaults", async () => {
    const { forecastView } = await import("./forecast");

    const container = document.createElement("div");
    document.body.appendChild(container);
    forecastView.render(container, { copo: "0955" });

    await flushPromises();
    await flushPromises();

    expect(getForecastPreferences).toHaveBeenCalledTimes(1);
    expect(getCityForecast).toHaveBeenCalledWith(
      "0955",
      "sales",
      expect.objectContaining({
        model: "ensemble",
        horizonMonths: 24,
        lookbackMonths: 48,
        confidenceLevel: 0.9,
        indicatorProfile: "balanced",
        activityCode: "0114",
      }),
    );

    const saveButton = container.querySelector<HTMLButtonElement>("#forecast-save-defaults");
    const note = container.querySelector<HTMLElement>("#forecast-default-save-note");
    if (!saveButton || !note) {
      throw new Error("Expected forecast controls to render.");
    }

    saveButton.click();
    await flushPromises();

    expect(updateForecastPreferences).toHaveBeenCalledWith({
      default_city_copo: "0955",
      default_tax_type: "sales",
      forecast_model: "ensemble",
      forecast_horizon_months: 24,
      forecast_lookback_months: 48,
      forecast_confidence_level: 0.9,
      forecast_indicator_profile: "balanced",
      forecast_scope: "naics",
      forecast_activity_code: "0114",
    });
    expect(note.textContent).toContain("Saved as your default forecast settings.");
  });
});
