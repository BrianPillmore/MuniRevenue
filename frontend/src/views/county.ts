/* ══════════════════════════════════════════════
   County view -- Aggregate county revenue
   ══════════════════════════════════════════════ */

import { getCountySummary } from "../api";
import { renderKpiCards } from "../components/kpi-card";
import { renderTaxToggle } from "../components/tax-toggle";
import { cityPath, countyPath, reportPath, ROUTES } from "../paths";
import { navigateTo } from "../router";
import { setPageMetadata } from "../seo";
import Highcharts from "../theme";
import type { CountySummaryResponse, View } from "../types";
import {
    escapeHtml,
    formatCompactCurrency,
    formatCurrency,
    formatNumber,
    wrapTable,
} from "../utils";

/* ── State ── */

interface CountyViewState {
  countyName: string | null;
  activeTaxType: string;
  chart: any;
  data: CountySummaryResponse | null;
}

const state: CountyViewState = {
  countyName: null,
  activeTaxType: "sales",
  chart: null,
  data: null,
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

function renderCountyChart(data: CountySummaryResponse): void {
  const chartEl = document.querySelector<HTMLElement>("#county-chart-inner");
  if (!chartEl) return;

  destroyCharts();

  if (!data.monthly_totals.length) {
    chartEl.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No monthly totals available.</p>';
    return;
  }

  /* Sort chronologically */
  const sorted = [...data.monthly_totals].sort(
    (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );

  const categories = sorted.map((r) => toMmmYy(r.voucher_date));
  const values = sorted.map((r) => r.total_returned);

  const taxLabel =
    state.activeTaxType.charAt(0).toUpperCase() + state.activeTaxType.slice(1);

  state.chart = Highcharts.chart(chartEl, {
    chart: {
      type: "line",
      height: 420,
      zooming: { type: "x" },
    },
    title: { text: `${escapeHtml(data.county_name)} County -- Aggregate ${taxLabel} tax revenue` },
    subtitle: {
      text: `${data.city_count} jurisdictions, ${sorted.length} monthly periods`,
    },
    xAxis: {
      categories,
      tickInterval: Math.max(1, Math.floor(categories.length / 12)),
      labels: { rotation: -45, style: { fontSize: "0.72rem" } },
      title: { text: null },
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
      line: {
        marker: { enabled: sorted.length <= 60, radius: 3 },
        lineWidth: 2.5,
      },
    },
    legend: { enabled: false },
    series: [
      {
        name: "Total returned",
        data: values,
        color: "#1b3a5c",
      },
    ],
  });
}

/* ── City table ── */

function renderCityTable(data: CountySummaryResponse): void {
  const container = document.querySelector<HTMLElement>("#county-city-table");
  if (!container) return;

  if (!data.cities.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No cities found in this county.</p>';
    return;
  }

  /* Derive latest available period from county monthly_totals */
  const latestTotal = data.monthly_totals.length
    ? [...data.monthly_totals].sort(
        (a, b) => new Date(b.voucher_date).getTime() - new Date(a.voucher_date).getTime(),
      )[0]
    : null;
  const latestDate = latestTotal ? new Date(latestTotal.voucher_date) : null;
  const latestYear = latestDate ? latestDate.getFullYear() : null;
  const latestMonth = latestDate ? latestDate.getMonth() + 1 : null;

  const rows = data.cities
    .map(
      (c) => {
        const reportLink =
          latestYear && latestMonth
            ? `<a href="${reportPath(c.copo, latestYear, latestMonth)}" class="city-link" style="font-size:0.82rem;">Report &rarr;</a>`
            : "";
        return `
        <tr>
          <td>
            <a href="${cityPath(c.copo)}" class="city-link">
              ${escapeHtml(c.name)}
            </a>
          </td>
          <td style="text-align:right;">${c.total_returned !== null ? formatCurrency(c.total_returned) : "N/A"}</td>
          <td style="text-align:right;">${c.latest_returned !== null ? formatCurrency(c.latest_returned) : "N/A"}</td>
          <td>${reportLink}</td>
          <td>
            <a href="${cityPath(c.copo)}" class="city-link" style="font-size:0.82rem;">
              Explore &rarr;
            </a>
          </td>
        </tr>
      `;
      },
    )
    .join("");

  container.innerHTML = wrapTable(
    ["City", "Total Returned", "Latest Month", "Report", ""],
    rows,
  );
}

/* ── Data loading ── */

async function loadCounty(countyName: string): Promise<void> {
  state.countyName = countyName;

  const headingEl = document.querySelector<HTMLElement>("#county-heading");
  const chartArea = document.querySelector<HTMLElement>("#county-chart-area");
  const tableArea = document.querySelector<HTMLElement>("#county-city-table");
  const kpiArea = document.querySelector<HTMLElement>("#county-kpis");

  if (headingEl) headingEl.innerHTML = "";
  if (kpiArea) kpiArea.innerHTML = "";
  if (chartArea) {
    chartArea.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">Loading county data...</p>';
  }
  if (tableArea) tableArea.innerHTML = "";

  try {
    const data = await getCountySummary(countyName, state.activeTaxType);
    state.data = data;
    setPageMetadata({
      title: `${data.county_name} County Revenue Data`,
      description:
        `${data.county_name} County revenue totals, city rollups, and monthly tax trends for Oklahoma municipal distributions.`,
      path: countyPath(data.county_name),
    });

    /* Heading */
    if (headingEl) {
      headingEl.innerHTML = `
        <p class="eyebrow">County</p>
        <h3 style="margin:4px 0 0;font-family:Georgia,serif;font-size:1.2rem;">
          ${escapeHtml(data.county_name)} County
        </h3>
        <p class="body-copy" style="margin-top:4px;color:#5c6578;">
          ${formatNumber(data.city_count)} jurisdictions
        </p>
      `;
    }

    /* KPI cards */
    if (kpiArea) {
      const totalReturned = data.cities.reduce(
        (sum, c) => sum + (c.total_returned ?? 0),
        0,
      );
      const latestTotal = data.monthly_totals.length
        ? data.monthly_totals[data.monthly_totals.length - 1].total_returned
        : 0;

      renderKpiCards(kpiArea, [
        { label: "Jurisdictions", value: formatNumber(data.city_count) },
        { label: "Total returned", value: formatCompactCurrency(totalReturned) },
        { label: "Latest month", value: formatCompactCurrency(latestTotal) },
        { label: "Monthly periods", value: formatNumber(data.monthly_totals.length) },
      ]);
    }

    /* Chart */
    if (chartArea) {
      chartArea.innerHTML = '<div id="county-chart-inner" class="chart-box"></div>';
    }
    renderCountyChart(data);

    /* Table */
    renderCityTable(data);
  } catch (err) {
    if (chartArea) {
      const msg = err instanceof Error ? err.message : "Unknown error";
      chartArea.innerHTML = `<p class="body-copy" style="padding:20px;color:var(--danger)">${escapeHtml(msg)}</p>`;
    }
  }
}

/* ── Event handlers ── */

function onSearchSubmit(): void {
  const input = document.querySelector<HTMLInputElement>("#county-search-input");
  if (!input) return;
  const val = input.value.trim();
  if (val.length < 2) return;
  navigateTo(countyPath(val));
}

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  if (state.countyName) loadCounty(state.countyName);
}

/* ── View implementation ── */

export const countyView: View = {
  render(container: HTMLElement, params: Record<string, string>): void {
    setPageMetadata({
      title: "Oklahoma County Revenue Data",
      description:
        "Search Oklahoma counties to view aggregate municipal revenue, monthly totals, and the cities reporting within each county.",
      path: params.county ? countyPath(params.county) : ROUTES.county,
    });
    container.className = "view-county";

    /* Reset state */
    state.countyName = null;
    state.activeTaxType = "sales";
    state.chart = null;
    state.data = null;

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Explore</p>
          <h2>County View</h2>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap;">
          <input
            type="text"
            id="county-search-input"
            class="search-input"
            placeholder="Enter county name (e.g., Oklahoma, Tulsa, Canadian)..."
            aria-label="County name search"
            style="flex:1;min-width:200px;max-width:400px;padding:8px 12px;border:1px solid rgba(26,31,43,0.12);border-radius:6px;font-size:0.92rem;"
          />
          <button id="county-search-btn" class="btn btn-secondary" style="padding:8px 18px;">
            Search
          </button>
        </div>
        <div id="county-heading"></div>
        <div id="county-tax-toggle" style="margin: 16px 0;"></div>
      </div>

      <div id="county-kpis"></div>

      <div class="panel chart-container">
        <div id="county-chart-area">
          <p class="body-copy" style="padding:40px;text-align:center;">
            Enter a county name above to see aggregate revenue data.
          </p>
        </div>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>Cities in county</h3>
        </div>
        <div id="county-city-table"></div>
      </div>
    `;

    /* Tax toggle */
    const toggleContainer = document.querySelector<HTMLElement>("#county-tax-toggle");
    if (toggleContainer) {
      renderTaxToggle(
        toggleContainer,
        ["sales", "use", "lodging"],
        state.activeTaxType,
        onTaxTypeChange,
      );
    }

    /* Search button */
    document.querySelector<HTMLButtonElement>("#county-search-btn")
      ?.addEventListener("click", onSearchSubmit);

    /* Enter key in search input */
    document.querySelector<HTMLInputElement>("#county-search-input")
      ?.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          onSearchSubmit();
        }
      });

    /* If county was passed in the URL, load it */
    if (params.county) {
      const input = document.querySelector<HTMLInputElement>("#county-search-input");
      if (input) input.value = decodeURIComponent(params.county);
      loadCounty(decodeURIComponent(params.county));
    }
  },

  destroy(): void {
    destroyCharts();
    state.countyName = null;
    state.data = null;
    state.activeTaxType = "sales";
  },
};
