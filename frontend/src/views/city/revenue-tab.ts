/* ==================================================
   Revenue Trends sub-tab
   ================================================== */

import { getCityLedger } from "../../api";
import { renderChartDownloadBar } from "../../components/chart-download";
import {
  renderChartControls,
  type DisplayMode,
  type SmoothingType,
} from "../../components/chart-controls";
import { showLoading } from "../../components/loading";
import Highcharts from "../../theme";
import type { CityDetailResponse, CityLedgerResponse } from "../../types";
import {
  computeSeasonalFactors,
  formatCompactCurrency,
  formatCurrency,
  formatPercent,
  linearTrendline,
  rollingAverage,
  seasonallyAdjust,
  toPercentChange,
} from "../../utils";

export interface SubTab {
  load(container: HTMLElement, copo: string, taxType: string, detail: CityDetailResponse): Promise<void>;
  destroy(): void;
}

/* ---- Control state ---- */

interface ControlState {
  smoothing: SmoothingType;
  seasonal: boolean;
  trendline: boolean;
  yAxisZero: boolean;
  displayMode: DisplayMode;
}

/* ---- Module ---- */

export function createRevenueTab(): SubTab {
  let chart: any = null;
  let rawCategories: string[] = [];
  let rawValues: number[] = [];
  let cityName = "";
  let taxLabel = "";
  let currentCopo = "";
  let currentTaxType = "";
  let currentContainer: HTMLElement | null = null;
  let currentDetail: CityDetailResponse | null = null;

  const ctrl: ControlState = {
    smoothing: "none",
    seasonal: false,
    trendline: false,
    yAxisZero: false,
    displayMode: "amount",
  };

  function resetCtrl(): void {
    ctrl.smoothing = "none";
    ctrl.seasonal = false;
    ctrl.trendline = false;
    ctrl.yAxisZero = false;
    ctrl.displayMode = "amount";
  }

  /* ---- Compute display values based on control state ---- */

  function computeDisplayValues(): (number | null)[] {
    let values: number[] = [...rawValues];
    const dates = rawCategories;

    if (ctrl.seasonal) {
      const factors = computeSeasonalFactors(dates, values);
      values = seasonallyAdjust(dates, values, factors);
    }

    let displayValues: (number | null)[];
    switch (ctrl.smoothing) {
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
    }

    if (ctrl.displayMode === "pct_change") {
      const nonNullValues = displayValues.map((v) => v ?? 0);
      displayValues = toPercentChange(nonNullValues);
    }

    return displayValues;
  }

  /* ---- Update existing chart ---- */

  function updateChart(): void {
    if (!chart) return;
    const displayValues = computeDisplayValues();
    const isPctMode = ctrl.displayMode === "pct_change";

    chart.series[0].setData(displayValues, false);

    /* Trendline */
    const existingTrendline = chart.series.find((s: any) => s.name === "Trendline");
    if (ctrl.trendline) {
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
          chart.addSeries(
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

    chart.yAxis[0].update(
      {
        min: ctrl.yAxisZero ? 0 : undefined,
        title: { text: isPctMode ? "Month-over-month change (%)" : "Returned (USD)" },
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

    // @ts-ignore
    chart.update(
      {
        tooltip: {
          formatter: function (this: any): string {
            if (isPctMode) {
              const val = this.y as number;
              const sign = val >= 0 ? "+" : "";
              return `<b>${this.x as string}</b><br/>MoM: ${sign}${val.toFixed(1)}%`;
            }
            return `<b>${this.x as string}</b><br/>Returned: ${formatCurrency(this.y as number)}`;
          },
        },
      },
      false,
    );

    chart.redraw();
  }

  /* ---- Build the Highchart ---- */

  function buildChart(
    chartEl: HTMLElement,
    categories: string[],
    values: (number | null)[],
  ): void {
    if (chart) {
      chart.destroy();
      chart = null;
    }
    chart = Highcharts.chart(chartEl, {
      chart: { type: "line", height: 420, zooming: { type: "x" } },
      title: { text: `${cityName} -- ${taxLabel} tax revenue` },
      subtitle: { text: `${categories.length} monthly records from the Oklahoma Tax Commission` },
      xAxis: {
        categories,
        tickInterval: Math.max(1, Math.floor(categories.length / 12)),
        labels: { rotation: -45, style: { fontSize: "0.72rem" } },
        title: { text: "Voucher date" },
      },
      yAxis: {
        title: { text: "Returned (USD)" },
        labels: {
          formatter: function (this: any): string {
            return formatCompactCurrency(this.value as number);
          },
        },
      },
      tooltip: {
        formatter: function (this: any): string {
          return `<b>${this.x as string}</b><br/>Returned: ${formatCurrency(this.y as number)}`;
        },
      },
      plotOptions: {
        line: {
          marker: { enabled: categories.length <= 60, radius: 3 },
          lineWidth: 2.5,
        },
      },
      legend: { enabled: false },
      series: [{ name: `${taxLabel} tax returned`, data: values, color: "#1b3a5c" }],
    });
  }

  /* ---- Generate insights text ---- */

  function generateInsights(): string {
    if (rawValues.length < 2) return "";

    const n = rawValues.length;
    const first = rawValues[0];
    const last = rawValues[n - 1];
    const direction = last > first ? "upward" : "downward";

    const max = Math.max(...rawValues);
    const maxIdx = rawValues.indexOf(max);
    const strongestDate = rawCategories[maxIdx] ?? "N/A";

    const avg = rawValues.reduce((a, b) => a + b, 0) / n;

    return `
      <div class="insights-box">
        <p class="body-copy" style="margin:0 0 6px;font-weight:600;">Key Insights</p>
        <ul class="body-copy" style="margin:0;padding-left:20px;">
          <li>Revenue shows <strong>${direction}</strong> trend over <strong>${n}</strong> months.</li>
          <li>Strongest month: <strong>${strongestDate}</strong> at <strong>${formatCurrency(max)}</strong>.</li>
          <li>Average monthly: <strong>${formatCurrency(avg)}</strong>.</li>
        </ul>
      </div>
    `;
  }

  /* ---- Render full content ---- */

  function renderContent(ledger: CityLedgerResponse, container: HTMLElement): void {
    if (!ledger.records.length) {
      container.innerHTML =
        '<p class="body-copy" style="padding:20px;text-align:center;">No records found for this tax type.</p>';
      return;
    }

    const sortedRecords = [...ledger.records].sort(
      (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
    );
    rawCategories = sortedRecords.map((r) => r.voucher_date);
    rawValues = sortedRecords.map((r) => r.returned);
    resetCtrl();

    /* Find date range for filters */
    const firstDate = rawCategories[0] ?? "";
    const lastDate = rawCategories[rawCategories.length - 1] ?? "";

    container.innerHTML = `
      <div id="rev-chart-controls"></div>
      <div id="rev-chart-inner" class="chart-box"></div>
      <div id="rev-chart-download"></div>
      <div style="display:flex;gap:12px;align-items:center;margin:14px 0 0;">
        <label class="body-copy" style="font-size:0.82rem;">From
          <input type="date" id="rev-date-start" value="${firstDate}" style="margin-left:4px;font-size:0.82rem;padding:3px 6px;border:1px solid var(--line);border-radius:6px;" />
        </label>
        <label class="body-copy" style="font-size:0.82rem;">To
          <input type="date" id="rev-date-end" value="${lastDate}" style="margin-left:4px;font-size:0.82rem;padding:3px 6px;border:1px solid var(--line);border-radius:6px;" />
        </label>
        <button id="rev-date-apply" class="chart-dl-btn" style="font-size:0.78rem;">Apply</button>
      </div>
      <div id="rev-insights"></div>
    `;

    /* Build chart */
    const chartEl = container.querySelector<HTMLElement>("#rev-chart-inner")!;
    buildChart(chartEl, rawCategories, rawValues);

    /* Chart controls */
    const controlsEl = container.querySelector<HTMLElement>("#rev-chart-controls")!;
    renderChartControls(controlsEl, {
      onSmoothingChange: (type) => { ctrl.smoothing = type; updateChart(); },
      onSeasonalToggle: (adjusted) => { ctrl.seasonal = adjusted; updateChart(); },
      onTrendlineToggle: (show) => { ctrl.trendline = show; updateChart(); },
      onYAxisZeroToggle: (fromZero) => { ctrl.yAxisZero = fromZero; updateChart(); },
      onDisplayModeChange: (mode) => { ctrl.displayMode = mode; updateChart(); },
    });

    /* Download bar */
    const dlEl = container.querySelector<HTMLElement>("#rev-chart-download")!;
    renderChartDownloadBar(dlEl, chart, rawCategories, [{ name: taxLabel + " tax", data: rawValues }], `${cityName}-${taxLabel}-revenue`);

    /* Insights */
    const insightsEl = container.querySelector<HTMLElement>("#rev-insights")!;
    insightsEl.innerHTML = generateInsights();

    /* Date range filter */
    const applyBtn = container.querySelector<HTMLButtonElement>("#rev-date-apply");
    if (applyBtn) {
      applyBtn.addEventListener("click", async () => {
        const startInput = container.querySelector<HTMLInputElement>("#rev-date-start");
        const endInput = container.querySelector<HTMLInputElement>("#rev-date-end");
        const start = startInput?.value || undefined;
        const end = endInput?.value || undefined;
        showLoading(container);
        try {
          const filtered = await getCityLedger(currentCopo, currentTaxType, start, end);
          renderContent(filtered, container);
        } catch {
          container.innerHTML =
            '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load filtered data.</p>';
        }
      });
    }
  }

  return {
    async load(container, copo, taxType, detail) {
      currentCopo = copo;
      currentTaxType = taxType;
      currentContainer = container;
      currentDetail = detail;
      cityName = detail.name;
      taxLabel = taxType.charAt(0).toUpperCase() + taxType.slice(1);
      showLoading(container);

      try {
        const ledger = await getCityLedger(copo, taxType);
        renderContent(ledger, container);
      } catch {
        container.innerHTML =
          '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load ledger data.</p>';
      }
    },

    destroy() {
      if (chart) {
        chart.destroy();
        chart = null;
      }
      rawCategories = [];
      rawValues = [];
      currentContainer = null;
      currentDetail = null;
    },
  };
}
