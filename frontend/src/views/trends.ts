/* ══════════════════════════════════════════════
   Statewide Trends view -- Revenue over time
   ══════════════════════════════════════════════ */

import { getStatewideTrend } from "../api";
import { renderKpiCards } from "../components/kpi-card";
import { renderTaxToggle } from "../components/tax-toggle";
import Highcharts from "../theme";
import type { StatewideTrendResponse, View } from "../types";
import {
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
} from "../utils";

/* ── State ── */

let trendChart: any = null;
let activeTaxType = "sales";

/* ── Chart management ── */

function destroyCharts(): void {
  if (trendChart) {
    trendChart.destroy();
    trendChart = null;
  }
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

  container.innerHTML = '<div id="trend-chart-inner" class="chart-box"></div>';
  const chartEl = container.querySelector<HTMLElement>("#trend-chart-inner")!;

  const sortedRecords = [...data.records].sort(
    (a, b) =>
      new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );

  const categories = sortedRecords.map((r) => r.voucher_date);
  const values = sortedRecords.map((r) => r.total_returned);

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
        color: "#1d6b70",
      },
    ],
  });
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
    chartContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">Loading trend data...</p>';
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
        '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load statewide trend data.</p>';
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
    container.className = "view-trends";

    /* Reset state */
    activeTaxType = "sales";

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
  },
};
