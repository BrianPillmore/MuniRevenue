/* ══════════════════════════════════════════════
   Forecast view -- Historical + projected revenue
   ══════════════════════════════════════════════ */

import { getCityDetail, getCityForecast, getCityLedger } from "../api";
import { renderCitySearch } from "../components/city-search";
import { showLoading } from "../components/loading";
import { renderTaxToggle } from "../components/tax-toggle";
import { navigateTo } from "../router";
import Highcharts from "../theme";
import type {
  CityDetailResponse,
  CityForecastPoint,
  CityLedgerResponse,
  CityListItem,
  ForecastResponse,
  LedgerRecord,
  View,
} from "../types";
import {
  escapeHtml,
  formatCompactCurrency,
  formatCurrency,
  wrapTable,
} from "../utils";

/* ── State ── */

interface ForecastViewState {
  copo: string | null;
  detail: CityDetailResponse | null;
  activeTaxType: string;
  chart: any;
  searchCleanup: (() => void) | null;
  showTrendline: boolean;
  yAxisFromZero: boolean;
  lastForecast: ForecastResponse | null;
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
};

/* ── Helpers ── */

const SHORT_MONTHS = [
  "", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

function toMmmYy(dateStr: string): string {
  const d = new Date(dateStr);
  return `${SHORT_MONTHS[d.getMonth() + 1]} ${String(d.getFullYear()).slice(2)}`;
}

/* ── Chart management ── */

function destroyCharts(): void {
  if (state.chart) {
    state.chart.destroy();
    state.chart = null;
  }
}

/* ── Chart rendering ── */

function renderForecastChart(
  ledger: CityLedgerResponse,
  forecast: ForecastResponse,
): void {
  const chartEl = document.querySelector<HTMLElement>("#forecast-chart-inner");
  if (!chartEl) return;

  destroyCharts();

  /* Sort historical records chronologically and take last 24 months */
  const sortedRecords = [...ledger.records]
    .sort((a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime())
    .slice(-24);

  /* Build category labels and data arrays */
  const historicalCategories = sortedRecords.map((r) => toMmmYy(r.voucher_date));
  const historicalValues = sortedRecords.map((r) => r.returned);

  const forecastCategories = forecast.forecasts.map((f) => toMmmYy(f.target_date));
  const forecastValues = forecast.forecasts.map((f) => f.projected_value);
  const upperValues = forecast.forecasts.map((f) => f.upper_bound);
  const lowerValues = forecast.forecasts.map((f) => f.lower_bound);

  /* Combined categories: historical + forecast */
  const allCategories = [...historicalCategories, ...forecastCategories];

  /* Historical data padded with nulls for forecast slots */
  const historicalData: (number | null)[] = [
    ...historicalValues,
    ...forecastValues.map(() => null),
  ];

  /* Forecast data: nulls for historical, then connect from last historical point */
  const forecastData: (number | null)[] = [
    ...historicalValues.slice(0, -1).map(() => null),
    historicalValues[historicalValues.length - 1],
    ...forecastValues,
  ];

  /* Upper bound area: nulls for historical, values for forecast period */
  const upperData: (number | null)[] = [
    ...historicalValues.slice(0, -1).map(() => null),
    historicalValues[historicalValues.length - 1],
    ...upperValues,
  ];

  /* Lower bound area: nulls for historical, values for forecast period */
  const lowerData: (number | null)[] = [
    ...historicalValues.slice(0, -1).map(() => null),
    historicalValues[historicalValues.length - 1],
    ...lowerValues,
  ];

  const cityName = state.detail?.name ?? `COPO ${ledger.copo}`;
  const taxLabel = ledger.tax_type.charAt(0).toUpperCase() + ledger.tax_type.slice(1);

  const series: any[] = [
    {
      name: "Historical",
      data: historicalData,
      color: "#1d6b70",
      lineWidth: 2.5,
      marker: { enabled: sortedRecords.length <= 30, radius: 3 },
      zIndex: 3,
    },
    {
      name: "Forecast",
      data: forecastData,
      color: "#1d6b70",
      dashStyle: "ShortDash",
      lineWidth: 2.5,
      marker: { enabled: true, radius: 3, symbol: "circle" },
      zIndex: 3,
    },
    {
      name: "Upper bound",
      data: upperData,
      type: "area",
      color: "rgba(29,107,112,0.10)",
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
      color: "#fffcf6",
      lineWidth: 0,
      marker: { enabled: false },
      enableMouseTracking: false,
      zIndex: 2,
      fillOpacity: 1,
    },
  ];

  /* Optional linear trendline on historical data */
  if (state.showTrendline && historicalValues.length >= 2) {
    const n = historicalValues.length;
    let sumX = 0, sumY = 0, sumXY = 0, sumX2 = 0;
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
    /* Pad with nulls for forecast period */
    for (let i = 0; i < forecastValues.length; i++) {
      trendData.push(null);
    }
    series.push({
      name: "Trendline",
      data: trendData,
      color: "#d4a843",
      lineWidth: 1.5,
      dashStyle: "Dot",
      marker: { enabled: false },
      enableMouseTracking: false,
      zIndex: 2,
    });
  }

  state.chart = Highcharts.chart(chartEl, {
    chart: {
      type: "line",
      height: 440,
      zooming: { type: "x" },
    },
    title: { text: `${cityName} -- ${taxLabel} tax forecast` },
    subtitle: {
      text: `${sortedRecords.length} months historical + ${forecast.forecasts.length} months projected (${forecast.model})`,
    },
    xAxis: {
      categories: allCategories,
      tickInterval: Math.max(1, Math.floor(allCategories.length / 12)),
      labels: { rotation: -45, style: { fontSize: "0.72rem" } },
      title: { text: null },
      plotLines: [{
        color: "rgba(16,34,49,0.2)",
        dashStyle: "Dash",
        value: historicalCategories.length - 0.5,
        width: 1,
        label: {
          text: "Forecast start",
          style: { color: "#5d6b75", fontSize: "0.72rem" },
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

/* ── Forecast table ── */

function renderForecastTable(forecast: ForecastResponse): void {
  const container = document.querySelector<HTMLElement>("#forecast-table-area");
  if (!container) return;

  if (!forecast.forecasts.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No forecast data available.</p>';
    return;
  }

  const rows = forecast.forecasts
    .map(
      (f) => `
        <tr>
          <td>${toMmmYy(f.target_date)}</td>
          <td style="text-align:right;">${formatCurrency(f.projected_value)}</td>
          <td style="text-align:right;">${formatCurrency(f.lower_bound)}</td>
          <td style="text-align:right;">${formatCurrency(f.upper_bound)}</td>
        </tr>
      `,
    )
    .join("");

  container.innerHTML = wrapTable(
    ["Target Month", "Projected", "Lower Bound", "Upper Bound"],
    rows,
  );
}

/* ── CSV download ── */

function downloadForecastCsv(): void {
  if (!state.lastForecast || !state.lastForecast.forecasts.length) return;
  const f = state.lastForecast;
  const cityName = state.detail?.name ?? state.copo ?? "unknown";
  const lines = ["Target Month,Projected,Lower Bound,Upper Bound,Model"];
  for (const row of f.forecasts) {
    lines.push(`${row.target_date},${row.projected_value.toFixed(0)},${row.lower_bound.toFixed(0)},${row.upper_bound.toFixed(0)},${f.model}`);
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `MuniRev-Forecast-${cityName}-${state.activeTaxType}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/* ── Data loading ── */

async function loadForecast(copo: string): Promise<void> {
  state.copo = copo;

  const chartArea = document.querySelector<HTMLElement>("#forecast-chart-area");
  const tableArea = document.querySelector<HTMLElement>("#forecast-table-area");
  const controlsArea = document.querySelector<HTMLElement>("#forecast-controls");

  if (chartArea) {
    showLoading(chartArea);
  }
  if (tableArea) tableArea.innerHTML = "";
  if (controlsArea) controlsArea.style.display = "none";

  try {
    const [detail, ledger, forecast] = await Promise.all([
      getCityDetail(copo),
      getCityLedger(copo, state.activeTaxType),
      getCityForecast(copo, state.activeTaxType),
    ]);
    state.detail = detail;

    /* Render tax toggle from available types */
    const toggleContainer = document.querySelector<HTMLElement>("#forecast-tax-toggle");
    if (toggleContainer) {
      const types = detail.tax_type_summaries.map((s) => s.tax_type);
      renderTaxToggle(toggleContainer, types, state.activeTaxType, onTaxTypeChange);
    }

    /* Show heading */
    const headingEl = document.querySelector<HTMLElement>("#forecast-city-heading");
    if (headingEl) {
      headingEl.innerHTML = `
        <p class="eyebrow">${escapeHtml(detail.jurisdiction_type)} / ${detail.county_name ? escapeHtml(detail.county_name) + " County" : ""}</p>
        <h3 style="margin:4px 0 0;font-family:Georgia,serif;font-size:1.2rem;">${escapeHtml(detail.name)}</h3>
      `;
    }

    if (chartArea) {
      chartArea.innerHTML = '<div id="forecast-chart-inner" class="chart-box"></div>';
    }

    if (!ledger.records.length) {
      if (chartArea) {
        chartArea.innerHTML =
          '<p class="body-copy" style="padding:20px;text-align:center;">No historical data available for this tax type.</p>';
      }
      return;
    }

    state.lastForecast = forecast;
    renderForecastChart(ledger, forecast);
    renderForecastTable(forecast);

    if (controlsArea) controlsArea.style.display = "flex";
  } catch {
    if (chartArea) {
      chartArea.innerHTML =
        '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load forecast data.</p>';
    }
  }
}

/* ── Event handlers ── */

function onCitySelected(city: CityListItem): void {
  navigateTo(`#/forecast/${city.copo}`);
}

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  if (state.copo) loadForecast(state.copo);
}

function onToggleTrendline(): void {
  state.showTrendline = !state.showTrendline;
  const btn = document.querySelector<HTMLButtonElement>("#btn-trendline");
  if (btn) btn.classList.toggle("is-active", state.showTrendline);
  if (state.copo) reloadChart();
}

function onToggleYAxis(): void {
  state.yAxisFromZero = !state.yAxisFromZero;
  const btn = document.querySelector<HTMLButtonElement>("#btn-yaxis");
  if (btn) btn.classList.toggle("is-active", state.yAxisFromZero);
  if (state.copo) reloadChart();
}

async function reloadChart(): Promise<void> {
  if (!state.copo) return;
  try {
    const [ledger, forecast] = await Promise.all([
      getCityLedger(state.copo, state.activeTaxType),
      getCityForecast(state.copo, state.activeTaxType),
    ]);
    renderForecastChart(ledger, forecast);
  } catch {
    /* Chart already has previous state; fail silently */
  }
}

/* ── View implementation ── */

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

      <div class="panel chart-container">
        <div id="forecast-chart-area"></div>
      </div>

      <div
        id="forecast-controls"
        class="toggle-controls"
        style="display:none;gap:8px;margin:8px 0;padding:0 4px;"
      >
        <button
          id="btn-trendline"
          class="btn btn-secondary"
          style="font-size:0.82rem;padding:6px 14px;"
        >Show trendline</button>
        <button
          id="btn-yaxis"
          class="btn btn-secondary is-active"
          style="font-size:0.82rem;padding:6px 14px;"
        >Y-axis from zero</button>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <h3>Forecast data</h3>
            <button id="btn-download-forecast" class="button button-ghost" style="min-height:36px;padding:0 14px;font-size:0.82rem;">Download CSV</button>
          </div>
        </div>
        <div id="forecast-table-area"></div>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <p class="eyebrow">Methodology</p>
          <h3>About this forecast</h3>
        </div>
        <p class="body-copy">
          This projection uses a <strong>seasonal trend model</strong> that computes a seasonal profile from each
          calendar month's historical average, estimates a linear trend from the most recent 36 months, and projects
          12 months forward by applying the trend factor to each month's seasonal baseline. Confidence intervals
          are computed at 95% from the standard deviation of model residuals.
        </p>
        <p class="body-copy" style="margin-top:10px;">
          <strong>Limitations:</strong> This model assumes historical seasonal patterns continue. It does not account
          for economic shocks, policy changes, business openings/closures, or tax rate changes.
        </p>
        <details style="margin-top:14px;">
          <summary style="cursor:pointer;color:var(--teal);font-weight:600;font-size:0.9rem;">Future model enhancements</summary>
          <ul class="body-copy" style="margin:10px 0 10px 20px;line-height:1.8;">
            <li>ARIMA/SARIMA for better trend detection</li>
            <li>Prophet for seasonality + holiday effects</li>
            <li>Ensemble (weighted average of multiple models)</li>
            <li>NAICS-level forecasts by industry</li>
            <li>Economic indicator integration</li>
            <li>Backtesting with MAPE accuracy metrics</li>
          </ul>
        </details>
      </div>
    `;

    /* City search */
    const searchMount = container.querySelector<HTMLElement>("#forecast-search-mount")!;
    state.searchCleanup = renderCitySearch(searchMount, {
      onSelect: onCitySelected,
      placeholder: "Search for a city to forecast...",
    });

    /* Toggle button handlers */
    document.querySelector<HTMLButtonElement>("#btn-trendline")
      ?.addEventListener("click", onToggleTrendline);
    document.querySelector<HTMLButtonElement>("#btn-yaxis")
      ?.addEventListener("click", onToggleYAxis);
    document.querySelector<HTMLButtonElement>("#btn-download-forecast")
      ?.addEventListener("click", downloadForecastCsv);

    /* If copo in URL, load it */
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
  },
};
