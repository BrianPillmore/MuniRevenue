/* ══════════════════════════════════════════════
   Overview view — Statewide landing page
   ══════════════════════════════════════════════ */

import { getOverview } from "../api";
import { renderKpiCards } from "../components/kpi-card";
import { showLoading } from "../components/loading";
import Highcharts from "../theme";
import type { OverviewResponse, View } from "../types";
import {
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
} from "../utils";

let topCitiesChart: any = null;

function destroyCharts(): void {
  if (topCitiesChart) {
    topCitiesChart.destroy();
    topCitiesChart = null;
  }
}

function renderOverviewKpis(
  container: HTMLElement,
  overview: OverviewResponse,
): void {
  renderKpiCards(container, [
    {
      label: "Jurisdictions",
      value: formatNumber(overview.jurisdictions_with_data),
    },
    {
      label: "Ledger records",
      value: formatNumber(overview.total_ledger_records),
    },
    {
      label: "NAICS records",
      value: formatNumber(overview.total_naics_records),
    },
    {
      label: "Date range",
      value: overview.earliest_ledger_date && overview.latest_ledger_date
        ? `${overview.earliest_ledger_date} to ${overview.latest_ledger_date}`
        : "N/A",
    },
  ]);
}

function renderTopCitiesChart(
  container: HTMLElement,
  overview: OverviewResponse,
): void {
  const topCities = overview.top_cities_by_sales.slice(0, 10).reverse();
  const categories = topCities.map((c) => c.name);
  const values = topCities.map((c) => c.total_sales_returned);

  topCitiesChart = Highcharts.chart(container, {
    chart: { type: "bar", height: 420 },
    title: { text: "Top 10 cities by total sales tax returned" },
    subtitle: {
      text: "All-time cumulative sales tax distributions from the Oklahoma Tax Commission",
    },
    xAxis: {
      categories,
      title: { text: null },
      labels: { style: { fontSize: "0.84rem" } },
    },
    yAxis: {
      min: 0,
      title: { text: "Total returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return formatCompactCurrency(this.value as number);
        },
      },
    },
    tooltip: {
      formatter: function (this: any): string {
        return `<b>${this.point.category as string}</b><br/>Total: ${formatCurrency(this.point.y as number)}`;
      },
    },
    plotOptions: {
      bar: {
        borderRadius: 4,
        dataLabels: {
          enabled: true,
          formatter: function (this: any): string {
            return formatCompactCurrency(this.point.y as number);
          },
          style: {
            fontWeight: "normal",
            color: "#5d6b75",
            fontSize: "0.78rem",
            textOutline: "none",
          },
        },
      },
    },
    legend: { enabled: false },
    series: [
      {
        name: "Sales tax returned",
        data: values,
        color: "#a63d40",
      },
    ],
  });
}

async function loadOverview(container: HTMLElement): Promise<void> {
  showLoading(container);

  try {
    const overview = await getOverview();

    container.innerHTML = `
      <div class="panel dashboard-overview-header">
        <div class="section-heading">
          <p class="eyebrow">Oklahoma overview</p>
          <h2>Statewide municipal revenue</h2>
        </div>
        <div id="overview-kpis" class="overview-stats"></div>
      </div>
      <div class="panel chart-container">
        <div id="top-cities-chart" class="chart-box"></div>
        <p class="body-copy" style="margin-top:12px;">
          See <a href="#/rankings">Rankings</a> to filter by city size and compare peer groups.
        </p>
      </div>
    `;

    const kpiContainer = container.querySelector<HTMLElement>("#overview-kpis")!;
    const chartContainer = container.querySelector<HTMLElement>("#top-cities-chart")!;

    renderOverviewKpis(kpiContainer, overview);
    renderTopCitiesChart(chartContainer, overview);
  } catch {
    container.innerHTML = `
      <div class="panel dashboard-overview-header">
        <div class="section-heading">
          <p class="eyebrow">Oklahoma overview</p>
          <h2>Statewide municipal revenue</h2>
        </div>
        <p class="body-copy" style="color:var(--brand)">Failed to load overview data. Ensure the API server is running.</p>
      </div>
    `;
  }
}

export const overviewView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-overview";
    container.innerHTML = '<div class="dashboard-overview" id="overview-root"></div>';
    const root = container.querySelector<HTMLElement>("#overview-root")!;
    loadOverview(root);
  },

  destroy(): void {
    destroyCharts();
  },
};
