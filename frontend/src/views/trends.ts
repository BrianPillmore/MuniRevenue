/* ══════════════════════════════════════════════
   Statewide Trends view -- Revenue over time
   ══════════════════════════════════════════════ */

import { getStatewideTrend } from "../api";
import {
  renderChartControls,
  type DisplayMode,
  type SmoothingType,
} from "../components/chart-controls";
import { renderKpiCards } from "../components/kpi-card";
import { showLoading } from "../components/loading";
import { ROUTES } from "../paths";
import { renderTaxToggle } from "../components/tax-toggle";
import { setPageMetadata } from "../seo";
import Highcharts from "../theme";
import type { StatewideTrendResponse, View } from "../types";
import {
  computeSeasonalFactors,
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
  linearTrendline,
  rollingAverage,
  seasonallyAdjust,
  toPercentChange,
} from "../utils";

/* ── State ── */

let trendChart: any = null;
let activeTaxType = "sales";

/* Raw data for chart controls recomputation */
let rawTrendCategories: string[] = [];
let rawTrendValues: number[] = [];

/* ── Chart controls state ── */

interface TrendControlState {
  smoothing: SmoothingType;
  seasonal: boolean;
  trendline: boolean;
  yAxisZero: boolean;
  displayMode: DisplayMode;
}

const trendCtrl: TrendControlState = {
  smoothing: "none",
  seasonal: false,
  trendline: false,
  yAxisZero: false,
  displayMode: "amount",
};

/* ── Chart management ── */

function destroyCharts(): void {
  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }
}

/* ── Compute display values based on controls ── */

function computeTrendDisplayValues(): (number | null)[] {
  let values: number[] = [...rawTrendValues];
  const dates = rawTrendCategories;

  /* Seasonal adjustment first */
  if (trendCtrl.seasonal) {
    const factors = computeSeasonalFactors(dates, values);
    values = seasonallyAdjust(dates, values, factors);
  }

  /* Smoothing */
  let displayValues: (number | null)[];
  switch (trendCtrl.smoothing) {
    case "3mo":
      displayValues = rollingAverage(values, 3);
      break;
    case "6mo":
      displayValues = rollingAverage(values, 6);
      break;
    case "ttm":
      displayValues = rollingAverage(values, 12);
      break;
    default:
      displayValues = values;
      break;
  }

  /* Percent change transformation */
  if (trendCtrl.displayMode === "pct_change") {
    const nonNullValues = displayValues.map((v) => v ?? 0);
    displayValues = toPercentChange(nonNullValues);
  }

  return displayValues;
}

function updateTrendChart(): void {
  if (!trendChart) return;

  const displayValues = computeTrendDisplayValues();
  const isPctMode = trendCtrl.displayMode === "pct_change";

  /* Update main series */
  trendChart.series[0].setData(displayValues, false);

  /* Handle trendline series */
  const existingTrendline = trendChart.series.find(
    (s: any) => s.name === "Trendline",
  );

  if (trendCtrl.trendline) {
    const nonNull = displayValues.filter((v): v is number => v !== null);
    if (nonNull.length >= 2) {
      const trend = linearTrendline(nonNull);
      let trendIdx = 0;
      const trendData = displayValues.map((v) => {
        if (v === null) return null;
        return trend[trendIdx++] ?? null;
      });

      if (existingTrendline) {
        existingTrendline.setData(trendData, false);
      } else {
        trendChart.addSeries(
          {
            name: "Trendline",
            data: trendData,
            color: "#999",
            lineWidth: 1.5,
            dashStyle: "ShortDash",
            marker: { enabled: false },
            enableMouseTracking: false,
            zIndex: 1,
          },
          false,
        );
      }
    }
  } else if (existingTrendline) {
    existingTrendline.remove(false);
  }

  /* Update Y-axis labels and title based on display mode */
  trendChart.yAxis[0].update(
    {
      min: trendCtrl.yAxisZero ? 0 : undefined,
      title: { text: isPctMode ? "Month-over-month change (%)" : "Total returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return isPctMode
            ? formatPercent(this.value as number)
            : formatCompactCurrency(this.value as number);
        },
      },
    },
    false,
  );

  /* Update tooltip format */
  // @ts-ignore -- Highcharts update accepts tooltip options
  trendChart.update({
    tooltip: {
      formatter: function (this: any): string {
        if (isPctMode) {
          const val = this.y as number;
          const sign = val >= 0 ? "+" : "";
          return `<b>${this.x as string}</b><br/>MoM: ${sign}${val.toFixed(1)}%`;
        }
        return `<b>${this.x as string}</b><br/>Total: ${formatCurrency(this.y as number)}`;
      },
    },
  }, false);

  trendChart.redraw();
}

/* ── Chart rendering ── */

function renderTrendChart(
  data: StatewideTrendResponse,
  container: HTMLElement,
): void {
  if (!data.records.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No trend data available for this tax type.</p>';
    return;
  }

  container.innerHTML = `
    <div id="trend-chart-inner" class="chart-box"></div>
    <div id="trend-chart-controls"></div>
  `;
  const chartEl = container.querySelector<HTMLElement>("#trend-chart-inner")!;

  const sortedRecords = [...data.records].sort(
    (a, b) =>
      new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );

  const categories = sortedRecords.map((r) => r.voucher_date);
  const values = sortedRecords.map((r) => r.total_returned);

  /* Store raw data */
  rawTrendCategories = categories;
  rawTrendValues = values;

  /* Reset controls */
  trendCtrl.smoothing = "none";
  trendCtrl.seasonal = false;
  trendCtrl.trendline = false;
  trendCtrl.yAxisZero = false;
  trendCtrl.displayMode = "amount";

  const taxLabel =
    data.tax_type.charAt(0).toUpperCase() + data.tax_type.slice(1);

  destroyCharts();

  trendChart = Highcharts.chart(chartEl, {
    chart: {
      type: "line",
      height: 440,
      zooming: { type: "x" },
    },
    title: { text: `Statewide ${taxLabel} Tax Revenue` },
    subtitle: {
      text: `${sortedRecords.length} monthly periods from the Oklahoma Tax Commission`,
    },
    xAxis: {
      categories,
      tickInterval: Math.max(1, Math.floor(categories.length / 12)),
      labels: { rotation: -45, style: { fontSize: "0.72rem" } },
      title: { text: "Voucher date" },
    },
    yAxis: {
      title: { text: "Total returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return formatCompactCurrency(this.value as number);
        },
      },
    },
    tooltip: {
      formatter: function (this: any): string {
        return `<b>${this.x as string}</b><br/>Total: ${formatCurrency(this.y as number)}`;
      },
    },
    plotOptions: {
      line: {
        marker: { enabled: sortedRecords.length <= 60, radius: 3 },
        lineWidth: 2.5,
      },
    },
    legend: { enabled: false },
    series: [
      {
        name: `${taxLabel} tax returned`,
        data: values,
        color: "#1b3a5c",
      },
    ],
  });

  /* Wire up chart controls */
  const controlsEl = container.querySelector<HTMLElement>("#trend-chart-controls");
  if (controlsEl) {
    renderChartControls(controlsEl, {
      onSmoothingChange: (type) => {
        trendCtrl.smoothing = type;
        updateTrendChart();
      },
      onSeasonalToggle: (adjusted) => {
        trendCtrl.seasonal = adjusted;
        updateTrendChart();
      },
      onTrendlineToggle: (show) => {
        trendCtrl.trendline = show;
        updateTrendChart();
      },
      onYAxisZeroToggle: (fromZero) => {
        trendCtrl.yAxisZero = fromZero;
        updateTrendChart();
      },
      onDisplayModeChange: (mode) => {
        trendCtrl.displayMode = mode;
        updateTrendChart();
      },
    });
  }
}

/* ── Summary stats ── */

function renderSummaryStats(
  data: StatewideTrendResponse,
  container: HTMLElement,
): void {
  if (!data.records.length) {
    container.innerHTML = "";
    return;
  }

  /* Get the latest record (last in chronological order) */
  const sorted = [...data.records].sort(
    (a, b) =>
      new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );
  const latest = sorted[sorted.length - 1];

  renderKpiCards(container, [
    {
      label: "Latest month total",
      value: formatCompactCurrency(latest.total_returned),
      subtitle: latest.voucher_date,
    },
    {
      label: "Jurisdictions reporting",
      value: formatNumber(latest.jurisdiction_count),
    },
    {
      label: "Month-over-month",
      value: formatPercent(latest.mom_pct),
      trend: latest.mom_pct,
    },
    {
      label: "Year-over-year",
      value: formatPercent(latest.yoy_pct),
      trend: latest.yoy_pct,
    },
  ]);
}

/* ── Data loading ── */

async function loadTrends(): Promise<void> {
  const chartContainer = document.querySelector<HTMLElement>("#trend-chart-area");
  const statsContainer = document.querySelector<HTMLElement>("#trend-summary-stats");

  if (chartContainer) {
    showLoading(chartContainer);
  }
  if (statsContainer) {
    statsContainer.innerHTML = "";
  }

  try {
    const data = await getStatewideTrend(activeTaxType);
    if (chartContainer) renderTrendChart(data, chartContainer);
    if (statsContainer) renderSummaryStats(data, statsContainer);
  } catch {
    if (chartContainer) {
      chartContainer.innerHTML =
        '<p class="body-copy" style="padding:20px;color:var(--danger)">Failed to load statewide trend data.</p>';
    }
  }
}

function onTaxTypeChange(taxType: string): void {
  activeTaxType = taxType;
  loadTrends();
}

/* ── View implementation ── */

export const trendsView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    setPageMetadata({
      title: "Oklahoma Revenue Trends",
      description:
        "Analyze statewide Oklahoma sales, use, and lodging tax trends with smoothing, seasonal adjustment, and percent-change views.",
      path: ROUTES.trends,
    });
    container.className = "view-trends";

    /* Reset state */
    activeTaxType = "sales";
    rawTrendCategories = [];
    rawTrendValues = [];

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Statewide Revenue Trends</h2>
        </div>
        <div id="trends-tax-toggle" style="margin: 16px 0;"></div>
      </div>

      <div class="panel chart-container">
        <div id="trend-chart-area"></div>
      </div>

      <div id="trend-summary-stats" style="margin-top: 4px;"></div>
    `;

    /* Tax toggle */
    const toggleContainer = document.querySelector<HTMLElement>("#trends-tax-toggle");
    if (toggleContainer) {
      renderTaxToggle(
        toggleContainer,
        ["sales", "use", "lodging"],
        activeTaxType,
        onTaxTypeChange,
      );
    }

    /* Initial data load */
    loadTrends();
  },

  destroy(): void {
    destroyCharts();
    activeTaxType = "sales";
    rawTrendCategories = [];
    rawTrendValues = [];
  },
};
