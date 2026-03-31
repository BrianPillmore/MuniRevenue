/* ══════════════════════════════════════════════
   City Explorer view
   ══════════════════════════════════════════════ */

import {
  getCityDetail,
  getCityLedger,
  getCityNaicsTop,
} from "../api";
import { renderCitySearch } from "../components/city-search";
import { renderKpiCards } from "../components/kpi-card";
import { renderTaxToggle } from "../components/tax-toggle";
import { navigateTo } from "../router";
import Highcharts from "../theme";
import type {
  CityDetailResponse,
  CityLedgerResponse,
  CityListItem,
  TopNaicsResponse,
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

/* ── State ── */

interface CityViewState {
  copo: string | null;
  detail: CityDetailResponse | null;
  activeTaxType: string;
  activeSubTab: string;
  revenueChart: any;
  searchCleanup: (() => void) | null;
}

const state: CityViewState = {
  copo: null,
  detail: null,
  activeTaxType: "sales",
  activeSubTab: "revenue",
  revenueChart: null,
  searchCleanup: null,
};

/* ── Chart management ── */

function destroyCharts(): void {
  if (state.revenueChart) {
    state.revenueChart.destroy();
    state.revenueChart = null;
  }
}

/* ── Sub-tab rendering ── */

function activateSubTab(tabName: string): void {
  state.activeSubTab = tabName;

  /* Toggle tab buttons */
  document.querySelectorAll<HTMLButtonElement>(".sub-tab-btn").forEach((btn) => {
    const isActive = btn.dataset.subtab === tabName;
    btn.classList.toggle("is-active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
  });

  /* Toggle tab panels */
  document.querySelectorAll<HTMLElement>(".sub-tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.subtab === tabName);
  });
}

/* ── Revenue tab ── */

async function loadRevenueTab(copo: string, taxType: string): Promise<void> {
  const container = document.querySelector<HTMLElement>("#subtab-revenue");
  if (!container) return;

  container.innerHTML =
    '<p class="body-copy" style="padding:20px;text-align:center;">Loading chart data...</p>';

  try {
    const ledger = await getCityLedger(copo, taxType);
    renderRevenueChart(ledger, container);
  } catch {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load ledger data.</p>';
  }
}

function renderRevenueChart(
  ledger: CityLedgerResponse,
  container: HTMLElement,
): void {
  if (!ledger.records.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No records found for this tax type.</p>';
    return;
  }

  container.innerHTML = '<div id="revenue-chart-inner" class="chart-box"></div>';
  const chartEl = container.querySelector<HTMLElement>("#revenue-chart-inner")!;

  const sortedRecords = [...ledger.records].sort(
    (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );

  const categories = sortedRecords.map((r) => r.voucher_date);
  const values = sortedRecords.map((r) => r.returned);

  const cityName = state.detail?.name ?? `COPO ${ledger.copo}`;
  const taxLabel =
    ledger.tax_type.charAt(0).toUpperCase() + ledger.tax_type.slice(1);

  destroyCharts();

  state.revenueChart = Highcharts.chart(chartEl, {
    chart: {
      type: "line",
      height: 420,
      zooming: { type: "x" },
    },
    title: { text: `${cityName} -- ${taxLabel} tax revenue` },
    subtitle: {
      text: `${sortedRecords.length} monthly records from the Oklahoma Tax Commission`,
    },
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

/* ── Industries tab ── */

async function loadIndustriesTab(copo: string, taxType: string): Promise<void> {
  const container = document.querySelector<HTMLElement>("#subtab-industries");
  if (!container) return;

  container.innerHTML =
    '<p class="body-copy" style="padding:20px;text-align:center;">Loading industry data...</p>';

  try {
    const data = await getCityNaicsTop(copo, taxType, 15);
    renderIndustriesTable(data, container);
  } catch {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load industry data.</p>';
  }
}

function renderIndustriesTable(
  data: TopNaicsResponse,
  container: HTMLElement,
): void {
  if (!data.records.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No NAICS industry data available.</p>';
    return;
  }

  const rows = data.records
    .map(
      (r) => `
        <tr>
          <td>${escapeHtml(r.sector)}</td>
          <td>${r.activity_description ? escapeHtml(r.activity_description) : escapeHtml(r.activity_code)}</td>
          <td>${formatCurrency(r.avg_sector_total)}</td>
          <td>${formatNumber(r.months_present)}</td>
          <td>${formatCurrency(r.total_across_months)}</td>
        </tr>
      `,
    )
    .join("");

  container.innerHTML = `
    <div class="block-header" style="margin-bottom: 12px;">
      <h3>Top industries by average revenue</h3>
      <p class="body-copy">Ranked by average monthly sector total across all reporting periods.</p>
    </div>
    ${wrapTable(["Sector", "Description", "Avg. Monthly", "Months", "Total"], rows)}
  `;
}

/* ── Seasonality tab (placeholder) ── */

function renderSeasonalityTab(): void {
  const container = document.querySelector<HTMLElement>("#subtab-seasonality");
  if (!container) return;

  container.innerHTML = `
    <div class="results-empty" style="min-height: 200px;">
      <div>
        <p style="font-size:1.8rem; margin: 0;">&#9684;</p>
        <p>Seasonality analysis will be available in a future release.</p>
        <p class="body-copy">This feature will use monthly averages to identify recurring revenue patterns.</p>
      </div>
    </div>
  `;
}

/* ── Details tab ── */

function renderDetailsTab(detail: CityDetailResponse): void {
  const container = document.querySelector<HTMLElement>("#subtab-details");
  if (!container) return;

  const rows = detail.tax_type_summaries
    .map(
      (t) => `
        <tr>
          <td>${escapeHtml(t.tax_type.charAt(0).toUpperCase() + t.tax_type.slice(1))}</td>
          <td>${formatNumber(t.record_count)}</td>
          <td>${t.earliest_date ?? "N/A"}</td>
          <td>${t.latest_date ?? "N/A"}</td>
          <td>${t.total_returned !== null ? formatCurrency(t.total_returned) : "N/A"}</td>
        </tr>
      `,
    )
    .join("");

  container.innerHTML = `
    <div class="block-header" style="margin-bottom: 12px;">
      <p class="eyebrow">${escapeHtml(detail.jurisdiction_type)} / ${detail.county_name ? escapeHtml(detail.county_name) + " County" : "Unknown County"}</p>
      <h3>${escapeHtml(detail.name)}</h3>
      ${detail.population ? `<p class="body-copy">Population: ${formatNumber(detail.population)}</p>` : ""}
    </div>
    ${wrapTable(["Tax type", "Records", "Earliest", "Latest", "Total returned"], rows)}
    <p class="body-copy" style="margin-top: 14px;">NAICS industry records: ${formatNumber(detail.naics_record_count)}</p>
  `;
}

/* ── City selection handler ── */

async function onCitySelected(city: CityListItem): Promise<void> {
  /* Navigate to the city route */
  navigateTo(`#/city/${city.copo}`);
}

async function loadCity(copo: string): Promise<void> {
  state.copo = copo;
  state.activeTaxType = "sales";
  state.activeSubTab = "revenue";

  const kpiContainer = document.querySelector<HTMLElement>("#city-kpis");
  const toggleContainer = document.querySelector<HTMLElement>("#city-tax-toggle");
  const contentArea = document.querySelector<HTMLElement>("#city-content");

  if (kpiContainer) {
    kpiContainer.innerHTML =
      '<p class="body-copy">Loading city data...</p>';
  }
  if (contentArea) contentArea.style.display = "none";

  try {
    const detail = await getCityDetail(copo);
    state.detail = detail;

    /* KPI cards */
    if (kpiContainer) {
      const cards: { label: string; value: string }[] = [];

      const salesSummary = detail.tax_type_summaries.find(
        (t) => t.tax_type === "sales",
      );
      const useSummary = detail.tax_type_summaries.find(
        (t) => t.tax_type === "use",
      );
      const lodgingSummary = detail.tax_type_summaries.find(
        (t) => t.tax_type === "lodging",
      );

      if (salesSummary && salesSummary.total_returned !== null) {
        cards.push({
          label: "Sales tax total",
          value: formatCompactCurrency(salesSummary.total_returned),
        });
      }
      if (useSummary && useSummary.total_returned !== null) {
        cards.push({
          label: "Use tax total",
          value: formatCompactCurrency(useSummary.total_returned),
        });
      }
      if (lodgingSummary && lodgingSummary.total_returned !== null) {
        cards.push({
          label: "Lodging tax total",
          value: formatCompactCurrency(lodgingSummary.total_returned),
        });
      }

      const totalRecords = detail.tax_type_summaries.reduce(
        (sum, t) => sum + t.record_count,
        0,
      );
      cards.push({ label: "Records", value: formatNumber(totalRecords) });

      const dates = detail.tax_type_summaries
        .flatMap((t) => [t.earliest_date, t.latest_date])
        .filter(Boolean)
        .sort();
      if (dates.length) {
        cards.push({
          label: "Date range",
          value: `${dates[0]} to ${dates[dates.length - 1]}`,
        });
      }

      kpiContainer.innerHTML = `
        <div class="section-heading" style="margin-bottom:14px;">
          <p class="eyebrow">${escapeHtml(detail.jurisdiction_type)} / ${detail.county_name ? escapeHtml(detail.county_name) + " County" : ""}</p>
          <h2 style="font-size:1.3rem;">${escapeHtml(detail.name)}</h2>
        </div>
      `;
      const grid = document.createElement("div");
      kpiContainer.appendChild(grid);
      renderKpiCards(grid, cards);
    }

    /* Tax type toggle */
    if (toggleContainer) {
      const types = detail.tax_type_summaries.map((s) => s.tax_type);
      renderTaxToggle(toggleContainer, types, state.activeTaxType, onTaxTypeChange);
    }

    /* Show content area and render active sub-tab */
    if (contentArea) contentArea.style.display = "block";

    renderSubTabContent();
  } catch {
    if (kpiContainer) {
      kpiContainer.innerHTML =
        '<p class="body-copy" style="color:var(--brand)">Failed to load city data. Check that the COPO code is valid.</p>';
    }
  }
}

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  renderSubTabContent();
}

function renderSubTabContent(): void {
  if (!state.copo) return;

  switch (state.activeSubTab) {
    case "revenue":
      loadRevenueTab(state.copo, state.activeTaxType);
      break;
    case "industries":
      loadIndustriesTab(state.copo, state.activeTaxType);
      break;
    case "seasonality":
      renderSeasonalityTab();
      break;
    case "details":
      if (state.detail) renderDetailsTab(state.detail);
      break;
  }
}

/* ── View implementation ── */

export const cityView: View = {
  render(container: HTMLElement, params: Record<string, string>): void {
    container.className = "view-city";

    container.innerHTML = `
      <div class="city-explorer-layout">
        <div class="panel city-explorer-search">
          <div class="section-heading">
            <p class="eyebrow">Explore</p>
            <h2>City Explorer</h2>
          </div>
          <div id="city-search-mount"></div>
        </div>

        <div id="city-kpis"></div>

        <div id="city-tax-toggle"></div>

        <div id="city-content" style="display: none;">
          <div class="sub-tabs" role="tablist" aria-label="City data sections">
            <button class="sub-tab-btn is-active" data-subtab="revenue" role="tab" aria-selected="true">Revenue</button>
            <button class="sub-tab-btn" data-subtab="industries" role="tab" aria-selected="false">Industries</button>
            <button class="sub-tab-btn" data-subtab="seasonality" role="tab" aria-selected="false">Seasonality</button>
            <button class="sub-tab-btn" data-subtab="details" role="tab" aria-selected="false">Details</button>
          </div>

          <div class="panel chart-container sub-tab-panel is-active" data-subtab="revenue" id="subtab-revenue" role="tabpanel">
          </div>
          <div class="panel sub-tab-panel" data-subtab="industries" id="subtab-industries" role="tabpanel" style="padding:22px;">
          </div>
          <div class="panel sub-tab-panel" data-subtab="seasonality" id="subtab-seasonality" role="tabpanel" style="padding:22px;">
          </div>
          <div class="panel sub-tab-panel" data-subtab="details" id="subtab-details" role="tabpanel" style="padding:22px;">
          </div>
        </div>
      </div>
    `;

    /* City search */
    const searchMount = container.querySelector<HTMLElement>("#city-search-mount")!;
    state.searchCleanup = renderCitySearch(searchMount, {
      onSelect: onCitySelected,
      placeholder: "Search cities or counties...",
    });

    /* Sub-tab click handlers */
    container.querySelectorAll<HTMLButtonElement>(".sub-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.subtab;
        if (tab && tab !== state.activeSubTab) {
          destroyCharts();
          activateSubTab(tab);
          renderSubTabContent();
        }
      });
    });

    /* If a copo was passed in the URL, load that city */
    if (params.copo) {
      loadCity(params.copo);
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
    state.activeSubTab = "revenue";
  },
};
