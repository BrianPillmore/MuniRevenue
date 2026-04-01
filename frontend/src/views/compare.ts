/* ══════════════════════════════════════════════
   Compare view -- Multi-city revenue comparison
   ══════════════════════════════════════════════ */

import { getCityDetail, getCityLedger } from "../api";
import { renderCitySearch } from "../components/city-search";
import {
  renderChartControls,
  type DisplayMode,
  type SmoothingType,
} from "../components/chart-controls";
import { showLoading } from "../components/loading";
import { renderTaxToggle } from "../components/tax-toggle";
import { cityPath, ROUTES } from "../paths";
import { setPageMetadata } from "../seo";
import Highcharts from "../theme";
import type {
  CityDetailResponse,
  CityLedgerResponse,
  CityListItem,
  View,
} from "../types";
import {
  computeSeasonalFactors,
  escapeHtml,
  formatCompactCurrency,
  formatCurrency,
  formatPercent,
  linearTrendline,
  rollingAverage,
  seasonallyAdjust,
  toPercentChange,
  wrapTable,
} from "../utils";

/* ── Constants ── */

const MAX_CITIES = 5;
const SERIES_COLORS = ["#1b3a5c", "#c8922a", "#2b7a9e", "#d4793a", "#6b5b95"];

/* ── State ── */

interface CityEntry {
  copo: string;
  name: string;
  county: string | null;
  ledger: CityLedgerResponse | null;
  detail: CityDetailResponse | null;
}

interface CompareControlState {
  smoothing: SmoothingType;
  seasonal: boolean;
  trendline: boolean;
  yAxisZero: boolean;
  displayMode: DisplayMode;
}

interface CompareState {
  cities: CityEntry[];
  activeTaxType: string;
  chart: any;
  searchCleanups: (() => void)[];
}

const state: CompareState = {
  cities: [],
  activeTaxType: "sales",
  chart: null,
  searchCleanups: [],
};

const compareCtrl: CompareControlState = {
  smoothing: "none",
  seasonal: false,
  trendline: false,
  yAxisZero: false,
  displayMode: "amount",
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

/* ── Transform a single city's values through the control pipeline ── */

function transformCityValues(
  dates: string[],
  values: number[],
): (number | null)[] {
  let processed: number[] = [...values];

  /* Seasonal adjustment */
  if (compareCtrl.seasonal) {
    const factors = computeSeasonalFactors(dates, processed);
    processed = seasonallyAdjust(dates, processed, factors);
  }

  /* Smoothing */
  let displayValues: (number | null)[];
  switch (compareCtrl.smoothing) {
    case "3mo":
      displayValues = rollingAverage(processed, 3);
      break;
    case "6mo":
      displayValues = rollingAverage(processed, 6);
      break;
    case "ttm":
      displayValues = rollingAverage(processed, 12);
      break;
    default:
      displayValues = processed;
      break;
  }

  /* Percent change transformation */
  if (compareCtrl.displayMode === "pct_change") {
    const nonNullValues = displayValues.map((v) => v ?? 0);
    displayValues = toPercentChange(nonNullValues);
  }

  return displayValues;
}

/* ── Render the overlay chart ── */

function renderCompareChart(): void {
  const chartEl = document.querySelector<HTMLElement>("#compare-chart-inner");
  if (!chartEl) return;

  destroyCharts();

  /* Collect all series that have data */
  const validEntries = state.cities.filter(
    (c) => c.ledger && c.ledger.records.length > 0,
  );

  if (!validEntries.length) {
    chartEl.parentElement!.innerHTML = `
      <div id="compare-chart-inner" class="chart-box">
        <p class="body-copy" style="padding:20px;text-align:center;">Add cities above to compare their revenue trends.</p>
      </div>
      <div id="compare-chart-controls"></div>
    `;
    return;
  }

  /* Ensure controls container exists */
  const chartParent = chartEl.parentElement!;
  if (!chartParent.querySelector("#compare-chart-controls")) {
    const controlsDiv = document.createElement("div");
    controlsDiv.id = "compare-chart-controls";
    chartParent.appendChild(controlsDiv);
  }

  const isPctMode = compareCtrl.displayMode === "pct_change";

  /* Build a unified time axis from all records */
  const allDatesSet = new Set<string>();
  for (const entry of validEntries) {
    for (const rec of entry.ledger!.records) {
      allDatesSet.add(rec.voucher_date);
    }
  }
  const allDates = Array.from(allDatesSet).sort(
    (a, b) => new Date(a).getTime() - new Date(b).getTime(),
  );
  const categories = allDates.map(toMmmYy);

  /* Build one Highcharts series per city */
  const series: any[] = validEntries.map((entry, idx) => {
    /* Build a map of date -> returned for this city */
    const dateMap = new Map<string, number>();
    for (const rec of entry.ledger!.records) {
      dateMap.set(rec.voucher_date, rec.returned);
    }

    /* Get the raw values aligned to the unified time axis */
    const rawAligned = allDates.map((d) => dateMap.get(d) ?? 0);
    /* Dates for this city's aligned data (using allDates for seasonal factors) */
    const data = transformCityValues(allDates, rawAligned);

    return {
      name: entry.name,
      data,
      color: SERIES_COLORS[idx % SERIES_COLORS.length],
      lineWidth: 2.5,
      marker: { enabled: allDates.length <= 36, radius: 3 },
    };
  });

  /* Add trendlines if enabled */
  if (compareCtrl.trendline) {
    const trendSeries: any[] = [];
    for (let idx = 0; idx < series.length; idx++) {
      const mainData = series[idx].data as (number | null)[];
      const nonNull = mainData.filter((v): v is number => v !== null);
      if (nonNull.length >= 2) {
        const trend = linearTrendline(nonNull);
        let trendIdx = 0;
        const trendData = mainData.map((v) => {
          if (v === null) return null;
          return trend[trendIdx++] ?? null;
        });
        trendSeries.push({
          name: `${series[idx].name} Trendline`,
          data: trendData,
          color: SERIES_COLORS[idx % SERIES_COLORS.length],
          lineWidth: 1.5,
          dashStyle: "ShortDash",
          marker: { enabled: false },
          enableMouseTracking: false,
          zIndex: 1,
          showInLegend: false,
        });
      }
    }
    series.push(...trendSeries);
  }

  const taxLabel =
    state.activeTaxType.charAt(0).toUpperCase() + state.activeTaxType.slice(1);

  state.chart = Highcharts.chart(chartEl, {
    chart: {
      type: "line",
      height: 440,
      zooming: { type: "x" },
    },
    title: { text: `${taxLabel} Tax Revenue Comparison` },
    subtitle: {
      text: isPctMode
        ? `${validEntries.length} cities -- month-over-month % change`
        : `${validEntries.length} cities overlaid on a common time axis`,
    },
    xAxis: {
      categories,
      tickInterval: Math.max(1, Math.floor(categories.length / 12)),
      labels: { rotation: -45, style: { fontSize: "0.72rem" } },
      title: { text: null },
    },
    yAxis: {
      min: compareCtrl.yAxisZero ? 0 : undefined,
      title: { text: isPctMode ? "Month-over-month change (%)" : "Returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return isPctMode
            ? formatPercent(this.value as number)
            : formatCompactCurrency(this.value as number);
        },
      },
    },
    tooltip: {
      formatter: function (this: any): string {
        if (isPctMode) {
          const val = this.point.y as number;
          const sign = val >= 0 ? "+" : "";
          return `<b>${this.series.name as string}</b><br/>${this.point.category as string}<br/>MoM: ${sign}${val.toFixed(1)}%`;
        }
        return `<b>${this.series.name as string}</b><br/>${this.point.category as string}<br/>Returned: ${formatCurrency(this.point.y as number)}`;
      },
    },
    plotOptions: {
      line: { connectNulls: false },
    },
    legend: {
      enabled: true,
      itemStyle: { fontWeight: "normal" },
    },
    series,
  });

  /* Wire up chart controls */
  const controlsEl = chartParent.querySelector<HTMLElement>("#compare-chart-controls");
  if (controlsEl && !controlsEl.hasChildNodes()) {
    renderChartControls(controlsEl, {
      onSmoothingChange: (type) => {
        compareCtrl.smoothing = type;
        renderCompareChart();
      },
      onSeasonalToggle: (adjusted) => {
        compareCtrl.seasonal = adjusted;
        renderCompareChart();
      },
      onTrendlineToggle: (show) => {
        compareCtrl.trendline = show;
        renderCompareChart();
      },
      onYAxisZeroToggle: (fromZero) => {
        compareCtrl.yAxisZero = fromZero;
        renderCompareChart();
      },
      onDisplayModeChange: (mode) => {
        compareCtrl.displayMode = mode;
        renderCompareChart();
      },
      showSeasonalToggle: true,
      showTrendline: true,
      showDisplayMode: true,
    });
  }
}

/* ── Comparison table ── */

function renderCompareTable(): void {
  const container = document.querySelector<HTMLElement>("#compare-table-area");
  if (!container) return;

  const validEntries = state.cities.filter(
    (c) => c.ledger && c.ledger.records.length > 0,
  );

  if (!validEntries.length) {
    container.innerHTML = "";
    return;
  }

  const rows = validEntries
    .map((entry) => {
      const records = entry.ledger!.records;
      const sorted = [...records].sort(
        (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
      );
      const totalReturned = sorted.reduce((s, r) => s + r.returned, 0);
      const latest = sorted[sorted.length - 1];
      const yoy = latest?.yoy_pct;

      return `
        <tr>
          <td>
            <a href="${cityPath(entry.copo)}" class="city-link">
              ${escapeHtml(entry.name)}
            </a>
          </td>
          <td>${entry.county ? escapeHtml(entry.county) : "N/A"}</td>
          <td style="text-align:right;">${formatCurrency(totalReturned)}</td>
          <td style="text-align:right;">${latest ? formatCurrency(latest.returned) : "N/A"}</td>
          <td style="text-align:right;">${yoy !== null && yoy !== undefined ? formatPercent(yoy) : "N/A"}</td>
        </tr>
      `;
    })
    .join("");

  container.innerHTML = wrapTable(
    ["City", "County", "Total Sales", "Latest Month", "YoY%"],
    rows,
  );
}

/* ── City management ── */

async function addCity(city: CityListItem): Promise<void> {
  /* Prevent duplicates */
  if (state.cities.some((c) => c.copo === city.copo)) return;
  if (state.cities.length >= MAX_CITIES) return;

  const entry: CityEntry = {
    copo: city.copo,
    name: city.name,
    county: city.county_name,
    ledger: null,
    detail: null,
  };
  state.cities.push(entry);

  updateCityTags();
  updateAddButton();

  /* Show loading in chart area while fetching */
  const chartEl = document.querySelector<HTMLElement>("#compare-chart-inner");
  if (chartEl && state.cities.length === 1) {
    showLoading(chartEl);
  }

  try {
    const [detail, ledger] = await Promise.all([
      getCityDetail(city.copo),
      getCityLedger(city.copo, state.activeTaxType),
    ]);
    entry.detail = detail;
    entry.ledger = ledger;
    entry.county = detail.county_name;

    renderCompareChart();
    renderCompareTable();
    updateCityTags();
  } catch {
    /* Remove the entry if data load fails */
    state.cities = state.cities.filter((c) => c.copo !== city.copo);
    updateCityTags();
    updateAddButton();
  }
}

function removeCity(copo: string): void {
  state.cities = state.cities.filter((c) => c.copo !== copo);
  updateCityTags();
  updateAddButton();

  /* Reset controls container so it re-renders with the chart */
  const controlsEl = document.querySelector<HTMLElement>("#compare-chart-controls");
  if (controlsEl) controlsEl.innerHTML = "";

  renderCompareChart();
  renderCompareTable();
}

function updateCityTags(): void {
  const container = document.querySelector<HTMLElement>("#compare-city-tags");
  if (!container) return;

  if (!state.cities.length) {
    container.innerHTML =
      '<p class="body-copy" style="color:#5c6578;">No cities selected. Use the search above to add up to 5 cities.</p>';
    return;
  }

  container.innerHTML = state.cities
    .map(
      (c, idx) => `
        <span
          class="city-tag"
          style="
            display:inline-flex;align-items:center;gap:6px;
            background:rgba(43,122,158,0.06);border:1px solid rgba(43,122,158,0.18);
            border-left:3px solid ${SERIES_COLORS[idx % SERIES_COLORS.length]};
            padding:4px 10px;border-radius:6px;font-size:0.85rem;
          "
        >
          ${escapeHtml(c.name)}
          <button
            class="remove-city-btn"
            data-copo="${escapeHtml(c.copo)}"
            style="
              background:none;border:none;cursor:pointer;font-size:1rem;
              color:#5c6578;line-height:1;padding:0 2px;
            "
            aria-label="Remove ${escapeHtml(c.name)}"
          >&times;</button>
        </span>
      `,
    )
    .join(" ");

  /* Attach remove handlers */
  container.querySelectorAll<HTMLButtonElement>(".remove-city-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const copo = btn.dataset.copo ?? "";
      removeCity(copo);
    });
  });
}

function updateAddButton(): void {
  const btn = document.querySelector<HTMLElement>("#compare-add-area");
  if (!btn) return;
  btn.style.display = state.cities.length >= MAX_CITIES ? "none" : "block";
}

/* ── Tax type change ── */

async function onTaxTypeChange(taxType: string): Promise<void> {
  state.activeTaxType = taxType;

  /* Show loading in chart area during reload */
  const chartEl = document.querySelector<HTMLElement>("#compare-chart-inner");
  if (chartEl && state.cities.length > 0) {
    showLoading(chartEl);
  }

  /* Reset controls container so it re-renders after data reload */
  const controlsEl = document.querySelector<HTMLElement>("#compare-chart-controls");
  if (controlsEl) controlsEl.innerHTML = "";

  /* Reload ledger for all selected cities */
  const loadPromises = state.cities.map(async (entry) => {
    try {
      entry.ledger = await getCityLedger(entry.copo, taxType);
    } catch {
      entry.ledger = null;
    }
  });

  await Promise.all(loadPromises);
  renderCompareChart();
  renderCompareTable();
}

/* ── View implementation ── */

export const compareView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    setPageMetadata({
      title: "Compare Oklahoma City Revenues",
      description:
        "Overlay revenue trends for multiple Oklahoma cities to compare tax performance, percent change, seasonality, and peer movement.",
      path: ROUTES.compare,
    });
    container.className = "view-compare";

    /* Reset state */
    state.cities = [];
    state.activeTaxType = "sales";
    state.chart = null;

    /* Reset chart controls */
    compareCtrl.smoothing = "none";
    compareCtrl.seasonal = false;
    compareCtrl.trendline = false;
    compareCtrl.yAxisZero = false;
    compareCtrl.displayMode = "amount";

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Explore</p>
          <h2>Compare Cities</h2>
        </div>
        <p class="body-copy" style="margin-bottom:16px;">
          Select up to ${MAX_CITIES} cities to overlay their revenue trends on one chart.
          Use <strong>% Change</strong> mode to compare cities of different sizes on the same scale.
        </p>
        <div id="compare-tax-toggle" style="margin-bottom:16px;"></div>
        <div id="compare-add-area">
          <div id="compare-search-mount" style="max-width:400px;margin-bottom:12px;"></div>
        </div>
        <div
          id="compare-city-tags"
          style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;"
        ></div>
      </div>

      <div class="panel chart-container">
        <div id="compare-chart-inner" class="chart-box">
          <p class="body-copy" style="padding:40px;text-align:center;">
            Add cities above to compare their revenue trends.
          </p>
        </div>
        <div id="compare-chart-controls"></div>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div id="compare-table-area"></div>
      </div>
    `;

    /* Tax toggle */
    const toggleContainer = document.querySelector<HTMLElement>("#compare-tax-toggle");
    if (toggleContainer) {
      renderTaxToggle(
        toggleContainer,
        ["sales", "use", "lodging"],
        state.activeTaxType,
        (t) => { onTaxTypeChange(t); },
      );
    }

    /* City search */
    const searchMount = container.querySelector<HTMLElement>("#compare-search-mount")!;
    const cleanup = renderCitySearch(searchMount, {
      onSelect: (city) => { addCity(city); },
      placeholder: "Search and add a city...",
    });
    state.searchCleanups.push(cleanup);

    /* Initial empty state */
    updateCityTags();
  },

  destroy(): void {
    destroyCharts();
    state.searchCleanups.forEach((fn) => fn());
    state.searchCleanups = [];
    state.cities = [];
    state.activeTaxType = "sales";
  },
};
