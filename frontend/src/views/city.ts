/* ==================================================
   Revenue Explorer -- Coordinator
   Routes to sub-tab modules: overview, revenue,
   industry, seasonality, details
   ================================================== */

import { getCityDetail } from "../api";
import { renderCitySearch } from "../components/city-search";
import { renderKpiCards } from "../components/kpi-card";
import { showLoading } from "../components/loading";
import { renderTaxToggle } from "../components/tax-toggle";
import { navigateTo } from "../router";
import type { CityDetailResponse, CityListItem, View } from "../types";
import {
  escapeHtml,
  formatCompactCurrency,
  formatNumber,
} from "../utils";

import { createOverviewTab } from "./city/overview-tab";
import { createRevenueTab } from "./city/revenue-tab";
import { createIndustryTab } from "./city/industry-tab";
import { createSeasonalityTab } from "./city/seasonality-tab";
import { createDetailsTab } from "./city/details-tab";

/* ---- Sub-tab interface ---- */

interface SubTab {
  load(container: HTMLElement, copo: string, taxType: string, detail: CityDetailResponse): Promise<void>;
  destroy(): void;
}

/* ---- Constants ---- */

const TAB_DEFS: { key: string; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "revenue", label: "Revenue" },
  { key: "industries", label: "Industries" },
  { key: "seasonality", label: "Seasonality" },
  { key: "details", label: "Details" },
];

const VALID_TABS = TAB_DEFS.map((t) => t.key);

/* ---- Coordinator state ---- */

interface CoordinatorState {
  copo: string | null;
  detail: CityDetailResponse | null;
  activeTaxType: string;
  activeTab: string;
  searchCleanup: (() => void) | null;
  tabs: Record<string, SubTab>;
  rootContainer: HTMLElement | null;
}

const state: CoordinatorState = {
  copo: null,
  detail: null,
  activeTaxType: "sales",
  activeTab: "overview",
  searchCleanup: null,
  tabs: {},
  rootContainer: null,
};

/* ---- Tab factory ---- */

function createTabs(): Record<string, SubTab> {
  return {
    overview: createOverviewTab(),
    revenue: createRevenueTab(),
    industries: createIndustryTab(),
    seasonality: createSeasonalityTab(),
    details: createDetailsTab(),
  };
}

/* ---- Sub-tab activation ---- */

function activateTab(tabName: string): void {
  state.activeTab = tabName;
  const root = state.rootContainer;
  if (!root) return;

  root.querySelectorAll<HTMLButtonElement>(".sub-tab-btn").forEach((btn) => {
    const isActive = btn.dataset.subtab === tabName;
    btn.classList.toggle("is-active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
  });
  root.querySelectorAll<HTMLElement>(".sub-tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.subtab === tabName);
  });
}

function updateUrlForTab(tabName: string): void {
  if (!state.copo) return;
  const newHash = `#/city/${state.copo}/${tabName}`;
  history.replaceState(null, "", newHash);
}

/* ---- Destroy all active tab modules ---- */

function destroyAllTabs(): void {
  for (const key of Object.keys(state.tabs)) {
    state.tabs[key].destroy();
  }
}

/* ---- Load active sub-tab content ---- */

function loadActiveTab(): void {
  if (!state.copo || !state.detail) return;
  const tab = state.tabs[state.activeTab];
  if (!tab) return;

  const panel = state.rootContainer?.querySelector<HTMLElement>(
    `.sub-tab-panel[data-subtab="${state.activeTab}"]`,
  );
  if (!panel) return;

  tab.load(panel, state.copo, state.activeTaxType, state.detail);
}

/* ---- City selection ---- */

async function onCitySelected(city: CityListItem): Promise<void> {
  navigateTo(`#/city/${city.copo}`);
}

/* ---- Tax type change ---- */

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  destroyAllTabs();
  loadActiveTab();
}

/* ---- Load city data ---- */

async function loadCity(copo: string, initialTab?: string): Promise<void> {
  state.copo = copo;
  state.activeTaxType = "sales";
  state.activeTab =
    initialTab && VALID_TABS.includes(initialTab) ? initialTab : "overview";

  /* Activate the correct tab visually */
  activateTab(state.activeTab);

  const root = state.rootContainer;
  if (!root) return;

  const kpiContainer = root.querySelector<HTMLElement>("#city-kpis");
  const toggleContainer = root.querySelector<HTMLElement>("#city-tax-toggle");
  const contentArea = root.querySelector<HTMLElement>("#city-content");

  if (kpiContainer) showLoading(kpiContainer);
  if (contentArea) contentArea.style.display = "none";

  try {
    const detail = await getCityDetail(copo);
    state.detail = detail;

    /* KPI cards */
    if (kpiContainer) {
      const cards: { label: string; value: string }[] = [];
      const salesSummary = detail.tax_type_summaries.find((t) => t.tax_type === "sales");
      const useSummary = detail.tax_type_summaries.find((t) => t.tax_type === "use");
      const lodgingSummary = detail.tax_type_summaries.find((t) => t.tax_type === "lodging");

      if (salesSummary && salesSummary.total_returned !== null)
        cards.push({ label: "Sales tax total", value: formatCompactCurrency(salesSummary.total_returned) });
      if (useSummary && useSummary.total_returned !== null)
        cards.push({ label: "Use tax total", value: formatCompactCurrency(useSummary.total_returned) });
      if (lodgingSummary && lodgingSummary.total_returned !== null)
        cards.push({ label: "Lodging tax total", value: formatCompactCurrency(lodgingSummary.total_returned) });

      const totalRecords = detail.tax_type_summaries.reduce((sum, t) => sum + t.record_count, 0);
      cards.push({ label: "Records", value: formatNumber(totalRecords) });

      const dates = detail.tax_type_summaries
        .flatMap((t) => [t.earliest_date, t.latest_date])
        .filter(Boolean)
        .sort();
      if (dates.length)
        cards.push({ label: "Date range", value: `${dates[0]} to ${dates[dates.length - 1]}` });

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

    /* Show content area */
    if (contentArea) contentArea.style.display = "block";

    /* Activate tab and load content */
    activateTab(state.activeTab);
    loadActiveTab();
  } catch {
    if (kpiContainer)
      kpiContainer.innerHTML =
        '<p class="body-copy" style="color:var(--danger);">Failed to load city data. Check that the COPO code is valid.</p>';
  }
}

/* ---- View implementation ---- */

export const cityView: View = {
  render(container: HTMLElement, params: Record<string, string>): void {
    state.rootContainer = container;
    state.tabs = createTabs();

    const initialTab =
      params.tab && VALID_TABS.includes(params.tab) ? params.tab : "overview";

    container.className = "view-city";

    /* Build tab buttons */
    const tabButtons = TAB_DEFS.map(
      (t) =>
        `<button class="sub-tab-btn${t.key === initialTab ? " is-active" : ""}" data-subtab="${t.key}" role="tab" aria-selected="${t.key === initialTab}">${escapeHtml(t.label)}</button>`,
    ).join("");

    /* Build tab panels */
    const tabPanels = TAB_DEFS.map(
      (t) =>
        `<div class="panel ${t.key === "revenue" ? "chart-container " : ""}sub-tab-panel${t.key === initialTab ? " is-active" : ""}" data-subtab="${t.key}" role="tabpanel" style="padding:${t.key === "revenue" ? "0" : "22px"};"></div>`,
    ).join("");

    container.innerHTML = `
      <div class="city-explorer-layout">
        <div class="panel city-explorer-search">
          <div class="section-heading">
            <p class="eyebrow">Explore</p>
            <h2>Revenue Explorer</h2>
          </div>
          <div id="city-search-mount"></div>
        </div>
        <div id="city-kpis"></div>
        <div id="city-tax-toggle"></div>
        <div id="city-content" style="display:none;">
          <div class="sub-tabs" role="tablist" aria-label="City data sections">
            ${tabButtons}
          </div>
          ${tabPanels}
        </div>
      </div>
    `;

    /* Mount city search */
    const searchMount = container.querySelector<HTMLElement>("#city-search-mount")!;
    state.searchCleanup = renderCitySearch(searchMount, {
      onSelect: onCitySelected,
      placeholder: "Search cities or counties...",
    });

    /* Tab button handlers */
    container.querySelectorAll<HTMLButtonElement>(".sub-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.dataset.subtab;
        if (tab && tab !== state.activeTab) {
          /* Destroy the previously active tab before switching */
          const prevTab = state.tabs[state.activeTab];
          if (prevTab) prevTab.destroy();

          activateTab(tab);
          updateUrlForTab(tab);
          loadActiveTab();
        }
      });
    });

    /* Load city if COPO in URL */
    if (params.copo) loadCity(params.copo, initialTab);
  },

  destroy(): void {
    destroyAllTabs();
    if (state.searchCleanup) {
      state.searchCleanup();
      state.searchCleanup = null;
    }
    state.copo = null;
    state.detail = null;
    state.activeTaxType = "sales";
    state.activeTab = "overview";
    state.tabs = {};
    state.rootContainer = null;
  },
};
