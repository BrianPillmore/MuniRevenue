/* ══════════════════════════════════════════════
   Forecast view -- configurable municipal forecasts
   ══════════════════════════════════════════════ */

import {
  getCityDetail,
  getCityForecast,
  getCityLedger,
  getCityNaicsTop,
  getIndustryTimeSeries,
} from "../api";
import { renderCitySearch } from "../components/city-search";
import { showLoading } from "../components/loading";
import { renderTaxToggle } from "../components/tax-toggle";
import { navigateTo } from "../router";
import Highcharts from "../theme";
import type {
  CityDetailResponse,
  CityForecastPoint,
  CityListItem,
  ForecastModelComparison,
  ForecastQueryOptions,
  ForecastResponse,
  TopNaicsRecord,
  View,
} from "../types";
import {
  escapeHtml,
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
  wrapTable,
} from "../utils";

interface HistoricalPoint {
  date: string;
  value: number;
}

interface ForecastControlsState {
  model: string;
  horizonMonths: number;
  lookbackMonths: number | "all";
  confidenceLevel: number;
  indicatorProfile: string;
  scope: "municipal" | "naics";
  activityCode: string | null;
}

interface ForecastViewState {
  copo: string | null;
  detail: CityDetailResponse | null;
  activeTaxType: string;
  chart: any;
  searchCleanup: (() => void) | null;
  showTrendline: boolean;
  yAxisFromZero: boolean;
  lastForecast: ForecastResponse | null;
  lastHistorical: HistoricalPoint[];
  topIndustries: TopNaicsRecord[];
  controls: ForecastControlsState;
}

const state: ForecastViewState = {
  copo: null,
  detail: null,
  activeTaxType: "sales",
  chart: null,
  searchCleanup: null,
  showTrendline: false,
  yAxisFromZero: true,
  lastForecast: null,
  lastHistorical: [],
  topIndustries: [],
  controls: {
    model: "auto",
    horizonMonths: 12,
    lookbackMonths: 36,
    confidenceLevel: 0.95,
    indicatorProfile: "balanced",
    scope: "municipal",
    activityCode: null,
  },
};

const SHORT_MONTHS = [
  "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const MODEL_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "baseline", label: "Baseline" },
  { value: "sarima", label: "SARIMA" },
  { value: "prophet", label: "Prophet" },
  { value: "ensemble", label: "Ensemble" },
];

const HORIZON_OPTIONS = [6, 12, 24];
const LOOKBACK_OPTIONS: Array<number | "all"> = [24, 36, 48, "all"];
const CONFIDENCE_OPTIONS = [0.8, 0.9, 0.95];
const DRIVER_PROFILE_OPTIONS = [
  { value: "off", label: "Off" },
  { value: "labor", label: "Labor" },
  { value: "retail_housing", label: "Retail + Housing" },
  { value: "balanced", label: "Balanced" },
];

function toMmmYy(dateStr: string): string {
  const d = new Date(dateStr);
  return `${SHORT_MONTHS[d.getMonth() + 1]} ${String(d.getFullYear()).slice(2)}`;
}

function lastDayOfMonth(year: number, month: number): string {
  const date = new Date(year, month, 0);
  return date.toISOString().slice(0, 10);
}

function destroyCharts(): void {
  if (state.chart) {
    state.chart.destroy();
    state.chart = null;
  }
}

function buildForecastOptions(): ForecastQueryOptions {
  return {
    model: state.controls.model,
    horizonMonths: state.controls.horizonMonths,
    lookbackMonths: state.controls.lookbackMonths,
    confidenceLevel: state.controls.confidenceLevel,
    indicatorProfile: state.controls.indicatorProfile,
    activityCode: state.controls.scope === "naics" ? state.controls.activityCode : null,
  };
}

function modelLabel(value: string): string {
  return MODEL_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function scopeLabel(forecast: ForecastResponse): string {
  if (forecast.series_scope === "naics") {
    const code = forecast.activity_code ?? state.controls.activityCode ?? "NAICS";
    return `Industry ${code}`;
  }
  return "Municipal total";
}

function normalizeHistoricalSeries(records: HistoricalPoint[]): HistoricalPoint[] {
  return [...records].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
}

async function loadHistoricalSeries(copo: string): Promise<HistoricalPoint[]> {
  if (state.controls.scope === "naics" && state.controls.activityCode) {
    const response = await getIndustryTimeSeries(copo, state.controls.activityCode, state.activeTaxType);
    return response.records.map((record) => ({
      date: lastDayOfMonth(record.year, record.month),
      value: record.sector_total,
    }));
  }

  const response = await getCityLedger(copo, state.activeTaxType);
  return response.records.map((record) => ({
    date: record.voucher_date,
    value: record.returned,
  }));
}

function renderForecastChart(
  historicalPoints: HistoricalPoint[],
  forecast: ForecastResponse,
): void {
  const chartEl = document.querySelector<HTMLElement>("#forecast-chart-inner");
  if (!chartEl) return;

  destroyCharts();
  const sortedRecords = normalizeHistoricalSeries(historicalPoints).slice(-36);
  if (!sortedRecords.length) {
    chartEl.innerHTML = '<p class="body-copy" style="padding:24px;text-align:center;">No historical data available for this configuration.</p>';
    return;
  }

  const forecastPoints = forecast.forecast_points.length
    ? forecast.forecast_points
    : forecast.forecasts;

  const historicalCategories = sortedRecords.map((record) => toMmmYy(record.date));
  const historicalValues = sortedRecords.map((record) => record.value);
  const forecastCategories = forecastPoints.map((point) => toMmmYy(point.target_date));
  const forecastValues = forecastPoints.map((point) => point.projected_value);
  const upperValues = forecastPoints.map((point) => point.upper_bound);
  const lowerValues = forecastPoints.map((point) => point.lower_bound);

  const allCategories = [...historicalCategories, ...forecastCategories];
  const historicalData: (number | null)[] = [
    ...historicalValues,
    ...forecastValues.map(() => null),
  ];
  const forecastData: (number | null)[] = [
    ...historicalValues.slice(0, -1).map(() => null),
    historicalValues[historicalValues.length - 1],
    ...forecastValues,
  ];
  const upperData: (number | null)[] = [
    ...historicalValues.slice(0, -1).map(() => null),
    historicalValues[historicalValues.length - 1],
    ...upperValues,
  ];
  const lowerData: (number | null)[] = [
    ...historicalValues.slice(0, -1).map(() => null),
    historicalValues[historicalValues.length - 1],
    ...lowerValues,
  ];

  const cityName = state.detail?.name ?? `COPO ${forecast.copo}`;
  const taxLabel = forecast.tax_type.charAt(0).toUpperCase() + forecast.tax_type.slice(1);
  const subtitleBits = [
    `${scopeLabel(forecast)}`,
    `${modelLabel(forecast.selected_model)} selected`,
  ];
  if (forecast.backtest_summary.mape !== null) {
    subtitleBits.push(`MAPE ${forecast.backtest_summary.mape.toFixed(2)}%`);
  }

  const series: any[] = [
    {
      name: "Historical",
      data: historicalData,
      color: "#1b3a5c",
      lineWidth: 2.6,
      marker: { enabled: sortedRecords.length <= 36, radius: 3 },
      zIndex: 3,
    },
    {
      name: "Forecast",
      data: forecastData,
      color: "#c8922a",
      dashStyle: "ShortDash",
      lineWidth: 2.4,
      marker: { enabled: true, radius: 3, symbol: "circle" },
      zIndex: 4,
    },
    {
      name: "Upper bound",
      data: upperData,
      type: "area",
      color: "rgba(43, 122, 158, 0.08)",
      lineWidth: 0,
      marker: { enabled: false },
      enableMouseTracking: false,
      zIndex: 1,
      fillOpacity: 1,
    },
    {
      name: "Lower bound",
      data: lowerData,
      type: "area",
      color: "rgba(27, 58, 92, 0.02)",
      lineWidth: 0,
      marker: { enabled: false },
      enableMouseTracking: false,
      zIndex: 2,
      fillOpacity: 1,
    },
  ];

  if (state.showTrendline && historicalValues.length >= 2) {
    const n = historicalValues.length;
    let sumX = 0;
    let sumY = 0;
    let sumXY = 0;
    let sumX2 = 0;
    for (let i = 0; i < n; i++) {
      sumX += i;
      sumY += historicalValues[i];
      sumXY += i * historicalValues[i];
      sumX2 += i * i;
    }
    const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
    const intercept = (sumY - slope * sumX) / n;
    const trendData: (number | null)[] = [];
    for (let i = 0; i < n; i++) {
      trendData.push(Math.round(intercept + slope * i));
    }
    for (let i = 0; i < forecastValues.length; i++) {
      trendData.push(null);
    }
    series.push({
      name: "Trendline",
      data: trendData,
      color: "#2b7a9e",
      lineWidth: 1.4,
      dashStyle: "Dot",
      marker: { enabled: false },
      enableMouseTracking: false,
      zIndex: 2,
    });
  }

  state.chart = Highcharts.chart(chartEl, {
    chart: {
      type: "line",
      height: 460,
      zooming: { type: "x" },
    },
    title: { text: `${cityName} -- ${taxLabel} forecast` },
    subtitle: { text: subtitleBits.join(" · ") },
    xAxis: {
      categories: allCategories,
      tickInterval: Math.max(1, Math.floor(allCategories.length / 12)),
      labels: { rotation: -45, style: { fontSize: "0.72rem" } },
      plotLines: [{
        color: "rgba(26,31,43,0.2)",
        dashStyle: "Dash",
        value: historicalCategories.length - 0.5,
        width: 1,
        label: {
          text: "Forecast start",
          style: { color: "#5c6578", fontSize: "0.72rem" },
        },
      }],
    },
    yAxis: {
      min: state.yAxisFromZero ? 0 : undefined,
      title: { text: "Returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return formatCompactCurrency(this.value as number);
        },
      },
    },
    tooltip: {
      formatter: function (this: any): string {
        return `<b>${this.point.category as string}</b><br/>${this.series.name}: ${formatCurrency(this.point.y as number)}`;
      },
    },
    plotOptions: {
      line: { connectNulls: false },
      area: { connectNulls: false },
    },
    legend: {
      enabled: true,
      itemStyle: { fontWeight: "normal" },
    },
    series,
  });
}

function renderForecastTable(forecast: ForecastResponse): void {
  const container = document.querySelector<HTMLElement>("#forecast-table-area");
  if (!container) return;

  const rows = (forecast.forecast_points.length ? forecast.forecast_points : forecast.forecasts)
    .map(
      (point) => `
        <tr>
          <td>${toMmmYy(point.target_date)}</td>
          <td style="text-align:right;">${formatCurrency(point.projected_value)}</td>
          <td style="text-align:right;">${formatCurrency(point.lower_bound)}</td>
          <td style="text-align:right;">${formatCurrency(point.upper_bound)}</td>
          <td style="text-align:right;">${escapeHtml(modelLabel(forecast.selected_model))}</td>
        </tr>
      `,
    )
    .join("");

  container.innerHTML = wrapTable(
    ["Target Month", "Projected", "Lower Bound", "Upper Bound", "Served Model"],
    rows,
  );
}

function renderWarnings(forecast: ForecastResponse): void {
  const container = document.querySelector<HTMLElement>("#forecast-warnings-area");
  if (!container) return;

  const warnings = forecast.data_quality.warnings;
  if (!warnings.length) {
    container.innerHTML = `
      <div class="forecast-callout forecast-callout-ok">
        <strong>Forecast quality check</strong>
        <p class="body-copy">This series passed the current data-quality gates for the selected model set.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="forecast-callout forecast-callout-warn">
      <strong>Forecast warnings</strong>
      <ul class="forecast-warning-list">
        ${warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("")}
      </ul>
    </div>
  `;
}

function renderComparisonTable(forecast: ForecastResponse): void {
  const container = document.querySelector<HTMLElement>("#forecast-comparison-area");
  if (!container) return;

  const rows = forecast.model_comparison
    .map((comparison: ForecastModelComparison) => {
      const statusLabel = comparison.selected
        ? `${comparison.status} / selected`
        : comparison.status;
      return `
        <tr>
          <td>${escapeHtml(modelLabel(comparison.model))}</td>
          <td>${escapeHtml(statusLabel)}</td>
          <td style="text-align:right;">${comparison.backtest.mape === null ? "N/A" : formatPercent(comparison.backtest.mape)}</td>
          <td style="text-align:right;">${comparison.backtest.smape === null ? "N/A" : formatPercent(comparison.backtest.smape)}</td>
          <td style="text-align:right;">${comparison.backtest.mae === null ? "N/A" : formatCurrency(comparison.backtest.mae)}</td>
          <td>${comparison.uses_indicators ? "Yes" : "No"}</td>
          <td>${escapeHtml(comparison.reason)}</td>
        </tr>
      `;
    })
    .join("");

  container.innerHTML = wrapTable(
    ["Model", "Status", "MAPE", "SMAPE", "MAE", "Drivers", "Reason"],
    rows,
  );
}

function renderExplainability(forecast: ForecastResponse): void {
  const container = document.querySelector<HTMLElement>("#forecast-explainability-area");
  if (!container) return;

  const explainability = forecast.explainability;
  const indicators = explainability.indicator_drivers
    .map((driver) => {
      const family = typeof driver.family === "string" ? driver.family : "indicator";
      const geography = typeof driver.geography_scope === "string" ? driver.geography_scope : "scope";
      const source = typeof driver.source_name === "string" ? driver.source_name : "Unknown source";
      return `<li>${escapeHtml(family)} · ${escapeHtml(geography)} · ${escapeHtml(source)}</li>`;
    })
    .join("");

  const industries = explainability.top_industry_drivers
    .map((driver) => {
      const code = typeof driver.activity_code === "string" ? driver.activity_code : "NAICS";
      const label = typeof driver.activity_description === "string" ? driver.activity_description : "Unknown industry";
      const share = typeof driver.share_pct === "number" ? `${driver.share_pct.toFixed(2)}%` : "N/A";
      const total = typeof driver.trailing_12_total === "number" ? formatCurrency(driver.trailing_12_total) : "N/A";
      return `<li><strong>${escapeHtml(code)}</strong> ${escapeHtml(label)} · ${share} of trailing-12 base · ${total}</li>`;
    })
    .join("");

  container.innerHTML = `
    <div class="forecast-summary-grid">
      <article class="forecast-summary-card">
        <p class="forecast-summary-label">Why this model</p>
        <p>${escapeHtml(explainability.selected_model_reason)}</p>
      </article>
      <article class="forecast-summary-card">
        <p class="forecast-summary-label">Trend</p>
        <p>${escapeHtml(explainability.trend_summary)}</p>
      </article>
      <article class="forecast-summary-card">
        <p class="forecast-summary-label">Seasonality</p>
        <p>${escapeHtml(explainability.seasonality_summary)}</p>
      </article>
      <article class="forecast-summary-card">
        <p class="forecast-summary-label">Confidence</p>
        <p>${escapeHtml(explainability.confidence_summary)}</p>
      </article>
      <article class="forecast-summary-card">
        <p class="forecast-summary-label">Holiday effects</p>
        <p>${escapeHtml(explainability.holiday_summary)}</p>
      </article>
      <article class="forecast-summary-card">
        <p class="forecast-summary-label">Driver summary</p>
        <p>${escapeHtml(explainability.indicator_summary)}</p>
      </article>
    </div>

    <div class="forecast-detail-grid">
      <article class="forecast-detail-card">
        <h4>Data quality</h4>
        <div class="forecast-meta-list">
          <div><span>Observed months</span><strong>${formatNumber(forecast.data_quality.observation_count)}</strong></div>
          <div><span>Expected months</span><strong>${formatNumber(forecast.data_quality.expected_months)}</strong></div>
          <div><span>Missing months</span><strong>${formatNumber(forecast.data_quality.missing_month_count)}</strong></div>
          <div><span>Latest observation</span><strong>${forecast.data_quality.latest_observation ? escapeHtml(toMmmYy(forecast.data_quality.latest_observation)) : "N/A"}</strong></div>
          <div><span>Series scope</span><strong>${escapeHtml(scopeLabel(forecast))}</strong></div>
          <div><span>Advanced models</span><strong>${forecast.data_quality.advanced_models_allowed ? "Enabled" : "Fallback only"}</strong></div>
        </div>
      </article>
      <article class="forecast-detail-card">
        <h4>Industry mix</h4>
        <p class="body-copy">${escapeHtml(explainability.industry_mix_summary)}</p>
        ${industries ? `<ul class="forecast-inline-list">${industries}</ul>` : '<p class="body-copy">No industry driver detail is available for this series.</p>'}
      </article>
      <article class="forecast-detail-card">
        <h4>Indicator provenance</h4>
        ${indicators ? `<ul class="forecast-inline-list">${indicators}</ul>` : '<p class="body-copy">No external indicators were loaded for this run.</p>'}
      </article>
      <article class="forecast-detail-card">
        <h4>Caveats</h4>
        ${explainability.caveats.length
          ? `<ul class="forecast-inline-list">${explainability.caveats.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
          : '<p class="body-copy">No additional caveats were reported for this run.</p>'}
      </article>
    </div>
  `;
}

function downloadForecastCsv(): void {
  if (!state.lastForecast) return;
  const forecastPoints = state.lastForecast.forecast_points.length
    ? state.lastForecast.forecast_points
    : state.lastForecast.forecasts;
  if (!forecastPoints.length) return;

  const cityName = state.detail?.name ?? state.copo ?? "unknown";
  const lines = [
    "Target Month,Projected,Lower Bound,Upper Bound,Selected Model,Requested Model,Series Scope,MAPE",
  ];
  for (const row of forecastPoints) {
    lines.push([
      row.target_date,
      row.projected_value.toFixed(2),
      row.lower_bound.toFixed(2),
      row.upper_bound.toFixed(2),
      state.lastForecast.selected_model,
      state.lastForecast.requested_model,
      state.lastForecast.series_scope,
      state.lastForecast.backtest_summary.mape ?? "",
    ].join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `MuniRev-Forecast-${cityName}-${state.activeTaxType}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function renderForecastControls(): void {
  const container = document.querySelector<HTMLElement>("#forecast-config-area");
  if (!container) return;

  const industryOptions = state.topIndustries.length
    ? state.topIndustries.map((record) => {
      const selected = state.controls.activityCode === record.activity_code ? "selected" : "";
      const label = `${record.activity_code} · ${record.activity_description ?? record.sector}`;
      return `<option value="${escapeHtml(record.activity_code)}" ${selected}>${escapeHtml(label)}</option>`;
    }).join("")
    : '<option value="">No top industries available</option>';

  container.innerHTML = `
    <div class="forecast-toolbar">
      <label class="forecast-control">
        <span>Model</span>
        <select id="forecast-model">
          ${MODEL_OPTIONS.map((option) => `<option value="${option.value}" ${state.controls.model === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
        </select>
      </label>
      <label class="forecast-control">
        <span>Horizon</span>
        <select id="forecast-horizon">
          ${HORIZON_OPTIONS.map((value) => `<option value="${value}" ${state.controls.horizonMonths === value ? "selected" : ""}>${value} months</option>`).join("")}
        </select>
      </label>
      <label class="forecast-control">
        <span>Lookback</span>
        <select id="forecast-lookback">
          ${LOOKBACK_OPTIONS.map((value) => `<option value="${value}" ${state.controls.lookbackMonths === value ? "selected" : ""}>${value === "all" ? "All history" : `${value} months`}</option>`).join("")}
        </select>
      </label>
      <label class="forecast-control">
        <span>Confidence</span>
        <select id="forecast-confidence">
          ${CONFIDENCE_OPTIONS.map((value) => `<option value="${value}" ${state.controls.confidenceLevel === value ? "selected" : ""}>${Math.round(value * 100)}%</option>`).join("")}
        </select>
      </label>
      <label class="forecast-control">
        <span>Driver profile</span>
        <select id="forecast-drivers">
          ${DRIVER_PROFILE_OPTIONS.map((option) => `<option value="${option.value}" ${state.controls.indicatorProfile === option.value ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}
        </select>
      </label>
      <label class="forecast-control">
        <span>Scope</span>
        <select id="forecast-scope" ${state.activeTaxType === "lodging" ? "disabled" : ""}>
          <option value="municipal" ${state.controls.scope === "municipal" ? "selected" : ""}>Municipal total</option>
          <option value="naics" ${state.controls.scope === "naics" ? "selected" : ""}>NAICS industry</option>
        </select>
      </label>
      ${state.controls.scope === "naics" && state.activeTaxType !== "lodging" ? `
        <label class="forecast-control forecast-control-wide">
          <span>Industry</span>
          <select id="forecast-activity-code">
            ${industryOptions}
          </select>
        </label>
      ` : ""}
    </div>
    <p class="helper-note" style="margin:10px 0 0;">
      Municipal forecasts use the jurisdiction total. NAICS forecasts use the selected industry code and are limited to sales/use tax series.
    </p>
  `;

  document.querySelector<HTMLSelectElement>("#forecast-model")
    ?.addEventListener("change", (event) => {
      state.controls.model = (event.target as HTMLSelectElement).value;
      if (state.copo) loadForecast(state.copo);
    });
  document.querySelector<HTMLSelectElement>("#forecast-horizon")
    ?.addEventListener("change", (event) => {
      state.controls.horizonMonths = Number((event.target as HTMLSelectElement).value);
      if (state.copo) loadForecast(state.copo);
    });
  document.querySelector<HTMLSelectElement>("#forecast-lookback")
    ?.addEventListener("change", (event) => {
      const value = (event.target as HTMLSelectElement).value;
      state.controls.lookbackMonths = value === "all" ? "all" : Number(value);
      if (state.copo) loadForecast(state.copo);
    });
  document.querySelector<HTMLSelectElement>("#forecast-confidence")
    ?.addEventListener("change", (event) => {
      state.controls.confidenceLevel = Number((event.target as HTMLSelectElement).value);
      if (state.copo) loadForecast(state.copo);
    });
  document.querySelector<HTMLSelectElement>("#forecast-drivers")
    ?.addEventListener("change", (event) => {
      state.controls.indicatorProfile = (event.target as HTMLSelectElement).value;
      if (state.copo) loadForecast(state.copo);
    });
  document.querySelector<HTMLSelectElement>("#forecast-scope")
    ?.addEventListener("change", async (event) => {
      state.controls.scope = (event.target as HTMLSelectElement).value as "municipal" | "naics";
      if (state.controls.scope === "municipal") {
        state.controls.activityCode = null;
      }
      if (state.copo) await loadForecast(state.copo);
    });
  document.querySelector<HTMLSelectElement>("#forecast-activity-code")
    ?.addEventListener("change", (event) => {
      state.controls.activityCode = (event.target as HTMLSelectElement).value;
      if (state.copo) loadForecast(state.copo);
    });
}

async function loadForecast(copo: string): Promise<void> {
  state.copo = copo;
  const chartArea = document.querySelector<HTMLElement>("#forecast-chart-area");
  const tableArea = document.querySelector<HTMLElement>("#forecast-table-area");
  const comparisonArea = document.querySelector<HTMLElement>("#forecast-comparison-area");
  const explainabilityArea = document.querySelector<HTMLElement>("#forecast-explainability-area");
  const warningsArea = document.querySelector<HTMLElement>("#forecast-warnings-area");

  if (chartArea) showLoading(chartArea);
  if (tableArea) tableArea.innerHTML = "";
  if (comparisonArea) comparisonArea.innerHTML = "";
  if (explainabilityArea) explainabilityArea.innerHTML = "";
  if (warningsArea) warningsArea.innerHTML = "";

  try {
    const [detail, maybeTopIndustries] = await Promise.all([
      getCityDetail(copo),
      state.activeTaxType !== "lodging"
        ? getCityNaicsTop(copo, state.activeTaxType, 20).catch(() => null)
        : Promise.resolve(null),
    ]);
    state.detail = detail;
    state.topIndustries = maybeTopIndustries?.records ?? [];

    if (state.activeTaxType === "lodging") {
      state.controls.scope = "municipal";
      state.controls.activityCode = null;
    } else if (state.controls.scope === "naics") {
      if (!state.topIndustries.length) {
        state.controls.scope = "municipal";
        state.controls.activityCode = null;
      } else if (!state.controls.activityCode || !state.topIndustries.some((record) => record.activity_code === state.controls.activityCode)) {
        state.controls.activityCode = state.topIndustries[0].activity_code;
      }
    }

    const toggleContainer = document.querySelector<HTMLElement>("#forecast-tax-toggle");
    if (toggleContainer) {
      const types = detail.tax_type_summaries.map((summary) => summary.tax_type);
      renderTaxToggle(toggleContainer, types, state.activeTaxType, onTaxTypeChange);
    }

    const headingEl = document.querySelector<HTMLElement>("#forecast-city-heading");
    if (headingEl) {
      headingEl.innerHTML = `
        <p class="eyebrow">${escapeHtml(detail.jurisdiction_type)}${detail.county_name ? ` / ${escapeHtml(detail.county_name)} County` : ""}</p>
        <h3 style="margin:4px 0 0;font-family:Georgia,serif;font-size:1.2rem;">${escapeHtml(detail.name)}</h3>
      `;
    }

    renderForecastControls();

    const [historicalPoints, forecast] = await Promise.all([
      loadHistoricalSeries(copo),
      getCityForecast(copo, state.activeTaxType, buildForecastOptions()),
    ]);

    state.lastHistorical = historicalPoints;
    state.lastForecast = forecast;

    if (chartArea) {
      chartArea.innerHTML = '<div id="forecast-chart-inner" class="chart-box"></div>';
    }

    renderForecastChart(historicalPoints, forecast);
    renderWarnings(forecast);
    renderForecastTable(forecast);
    renderComparisonTable(forecast);
    renderExplainability(forecast);
  } catch (error) {
    if (chartArea) {
      chartArea.innerHTML = '<p class="body-copy" style="padding:20px;color:var(--danger)">Failed to load forecast data.</p>';
    }
    if (warningsArea) {
      warningsArea.innerHTML = `
        <div class="forecast-callout forecast-callout-warn">
          <strong>Load failed</strong>
          <p class="body-copy">${escapeHtml(error instanceof Error ? error.message : "Unable to load this forecast configuration.")}</p>
        </div>
      `;
    }
  }
}

function onCitySelected(city: CityListItem): void {
  navigateTo(`#/forecast/${city.copo}`);
}

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  if (taxType === "lodging") {
    state.controls.scope = "municipal";
    state.controls.activityCode = null;
  }
  if (state.copo) loadForecast(state.copo);
}

function onToggleTrendline(): void {
  state.showTrendline = !state.showTrendline;
  const btn = document.querySelector<HTMLButtonElement>("#btn-trendline");
  if (btn) btn.classList.toggle("is-active", state.showTrendline);
  if (state.lastForecast) {
    renderForecastChart(state.lastHistorical, state.lastForecast);
  }
}

function onToggleYAxis(): void {
  state.yAxisFromZero = !state.yAxisFromZero;
  const btn = document.querySelector<HTMLButtonElement>("#btn-yaxis");
  if (btn) btn.classList.toggle("is-active", state.yAxisFromZero);
  if (state.lastForecast) {
    renderForecastChart(state.lastHistorical, state.lastForecast);
  }
}

export const forecastView: View = {
  render(container: HTMLElement, params: Record<string, string>): void {
    container.className = "view-forecast";

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Explore</p>
          <h2>Forecasts</h2>
        </div>
        <div id="forecast-search-mount" style="margin-bottom:16px;"></div>
        <div id="forecast-city-heading"></div>
        <div id="forecast-tax-toggle" style="margin: 16px 0;"></div>
      </div>

      <div class="panel" style="padding: 22px 30px; margin-top: 20px;">
        <div class="block-header" style="margin-bottom:12px;">
          <p class="eyebrow">Controls</p>
          <h3>Configure forecast</h3>
        </div>
        <div id="forecast-config-area"></div>
      </div>

      <div class="panel chart-container" style="margin-top: 20px;">
        <div id="forecast-chart-area"></div>
      </div>

      <div
        id="forecast-controls"
        class="toggle-controls"
        style="display:flex;gap:8px;margin:8px 0;padding:0 4px;"
      >
        <button id="btn-trendline" class="control-btn">Show trendline</button>
        <button id="btn-yaxis" class="control-btn is-active">Y-axis from zero</button>
      </div>

      <div class="panel" style="padding: 22px 30px; margin-top: 20px;">
        <div class="block-header" style="margin-bottom:12px;">
          <p class="eyebrow">Signals</p>
          <h3>Data quality and warnings</h3>
        </div>
        <div id="forecast-warnings-area"></div>
      </div>

      <div class="panel" style="padding: 22px 30px; margin-top: 20px;">
        <div class="block-header" style="margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
            <div>
              <p class="eyebrow">Forecast data</p>
              <h3>Projection output</h3>
            </div>
            <button id="btn-download-forecast" class="button button-ghost" style="min-height:36px;padding:0 14px;font-size:0.82rem;">Download CSV</button>
          </div>
        </div>
        <div id="forecast-table-area"></div>
      </div>

      <div class="panel" style="padding: 22px 30px; margin-top: 20px;">
        <div class="block-header" style="margin-bottom:12px;">
          <p class="eyebrow">Compare</p>
          <h3>Model comparison</h3>
        </div>
        <div id="forecast-comparison-area"></div>
      </div>

      <div class="panel" style="padding: 22px 30px; margin-top: 20px;">
        <div class="block-header" style="margin-bottom:12px;">
          <p class="eyebrow">Explainability</p>
          <h3>Why the forecast looks this way</h3>
        </div>
        <div id="forecast-explainability-area"></div>
      </div>
    `;

    const searchMount = container.querySelector<HTMLElement>("#forecast-search-mount")!;
    state.searchCleanup = renderCitySearch(searchMount, {
      onSelect: onCitySelected,
      placeholder: "Search for a city to forecast...",
    });

    document.querySelector<HTMLButtonElement>("#btn-trendline")
      ?.addEventListener("click", onToggleTrendline);
    document.querySelector<HTMLButtonElement>("#btn-yaxis")
      ?.addEventListener("click", onToggleYAxis);
    document.querySelector<HTMLButtonElement>("#btn-download-forecast")
      ?.addEventListener("click", downloadForecastCsv);

    renderForecastControls();

    if (params.copo) {
      loadForecast(params.copo);
    }
  },

  destroy(): void {
    destroyCharts();
    if (state.searchCleanup) {
      state.searchCleanup();
      state.searchCleanup = null;
    }
    state.copo = null;
    state.detail = null;
    state.activeTaxType = "sales";
    state.showTrendline = false;
    state.yAxisFromZero = true;
    state.lastForecast = null;
    state.lastHistorical = [];
    state.topIndustries = [];
    state.controls = {
      model: "auto",
      horizonMonths: 12,
      lookbackMonths: 36,
      confidenceLevel: 0.95,
      indicatorProfile: "balanced",
      scope: "municipal",
      activityCode: null,
    };
  },
};
