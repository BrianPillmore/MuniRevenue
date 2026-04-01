/* ══════════════════════════════════════════════
   Rankings view -- Jurisdictions ranked by revenue
   with peer group filtering by revenue band
   ══════════════════════════════════════════════ */

import { getRankings } from "../api";
import { showLoading } from "../components/loading";
import { cityPath, ROUTES } from "../paths";
import { renderTaxToggle } from "../components/tax-toggle";
import { setPageMetadata } from "../seo";
import type { RankingItem, View } from "../types";
import {
  escapeHtml,
  formatCompactCurrency,
  trendArrow,
  wrapTable,
} from "../utils";

/* ── Revenue bands ── */

type RevenueBand = "all" | "micro" | "small" | "medium" | "large" | "metro";
type JurisdictionFilter = "all" | "city" | "county";

interface BandRange {
  min: number;
  max: number;
}

const BAND_RANGES: Record<Exclude<RevenueBand, "all">, BandRange> = {
  micro:  { min: 0,           max: 1_000_000 },
  small:  { min: 1_000_000,   max: 10_000_000 },
  medium: { min: 10_000_000,  max: 100_000_000 },
  large:  { min: 100_000_000, max: 500_000_000 },
  metro:  { min: 500_000_000, max: Infinity },
};

function matchesBand(metricValue: number | null, band: RevenueBand): boolean {
  if (band === "all") return true;
  if (metricValue === null) return false;
  const range = BAND_RANGES[band];
  return metricValue >= range.min && metricValue < range.max;
}

/* ── State ── */

interface RankingsState {
  activeTaxType: string;
  currentPage: number;
  pageSize: number;
  searchQuery: string;
  activeBand: RevenueBand;
  activeJurisdictionFilter: JurisdictionFilter;
  totalItems: RankingItem[];
  yoyMap: Map<string, number | null>;
  loading: boolean;
}

const state: RankingsState = {
  activeTaxType: "sales",
  currentPage: 0,
  pageSize: 50,
  searchQuery: "",
  activeBand: "all",
  activeJurisdictionFilter: "all",
  totalItems: [],
  yoyMap: new Map(),
  loading: false,
};

/* ── Helpers: compute avg monthly ── */

const ESTIMATED_MONTHS = 60;

function avgMonthly(total: number | null): number | null {
  if (total === null) return null;
  return total / ESTIMATED_MONTHS;
}

/* ── Data fetching ── */

async function loadRankings(): Promise<void> {
  const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
  if (!tableContainer) return;

  showLoading(tableContainer);

  state.loading = true;

  try {
    /* Fetch a large batch for client-side filtering, plus YoY data */
    const [totalData, yoyData] = await Promise.all([
      getRankings(state.activeTaxType, "total_returned", 600, 0),
      getRankings(state.activeTaxType, "yoy_change", 600, 0),
    ]);

    /* Store full dataset */
    state.totalItems = totalData.items;

    /* Build YoY lookup map keyed by copo */
    state.yoyMap = new Map<string, number | null>();
    for (const item of yoyData.items) {
      state.yoyMap.set(item.copo, item.metric_value);
    }

    renderFilteredTable(tableContainer);
  } catch {
    tableContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load rankings data.</p>';
  } finally {
    state.loading = false;
  }
}

/* ── Filtering and rendering ── */

function getFilteredItems(): RankingItem[] {
  let items = state.totalItems;

  /* Revenue band filter */
  if (state.activeBand !== "all") {
    items = items.filter((item) => matchesBand(item.metric_value, state.activeBand));
  }

  /* Jurisdiction type filter */
  if (state.activeJurisdictionFilter !== "all") {
    items = items.filter(
      (item) => item.jurisdiction_type === state.activeJurisdictionFilter,
    );
  }

  /* Text search filter */
  const query = state.searchQuery.toLowerCase();
  if (query) {
    items = items.filter((item) => item.name.toLowerCase().includes(query));
  }

  return items;
}

function renderFilteredTable(container: HTMLElement): void {
  const filtered = getFilteredItems();

  if (!filtered.length) {
    const msg = state.searchQuery
      ? `No jurisdictions matching "${escapeHtml(state.searchQuery)}".`
      : "No ranking data available for these filters.";
    container.innerHTML = `<p class="body-copy" style="padding:20px;text-align:center;">${msg}</p>`;
    updatePaginationControls(filtered.length);
    return;
  }

  /* Paginate */
  const start = state.currentPage * state.pageSize;
  const page = filtered.slice(start, start + state.pageSize);

  const rows = page
    .map((item, idx) => {
      const displayRank = start + idx + 1;
      const yoy = state.yoyMap.get(item.copo) ?? null;
      const avg = avgMonthly(item.metric_value);

      return `
        <tr>
          <td>${displayRank}</td>
          <td>
            <a href="${cityPath(item.copo)}" class="city-link">
              ${escapeHtml(item.name)}
            </a>
          </td>
          <td>${item.county_name ? escapeHtml(item.county_name) : "N/A"}</td>
          <td>${item.metric_value !== null ? formatCompactCurrency(item.metric_value) : "N/A"}</td>
          <td>${avg !== null ? formatCompactCurrency(avg) : "N/A"}</td>
          <td>${trendArrow(yoy) || '<span style="color:var(--muted)">--</span>'}</td>
        </tr>
      `;
    })
    .join("");

  container.innerHTML = wrapTable(
    ["#", "City / County", "County", "Total Returned", "Avg Monthly", "YoY Growth"],
    rows,
  );

  updatePaginationControls(filtered.length);
}

function updatePaginationControls(totalFiltered: number): void {
  const prevBtn = document.querySelector<HTMLButtonElement>("#rankings-prev");
  const nextBtn = document.querySelector<HTMLButtonElement>("#rankings-next");
  const pageInfo = document.querySelector<HTMLElement>("#rankings-page-info");

  const start = state.currentPage * state.pageSize;

  if (prevBtn) {
    prevBtn.disabled = state.currentPage === 0;
  }
  if (nextBtn) {
    nextBtn.disabled = start + state.pageSize >= totalFiltered;
  }
  if (pageInfo) {
    const startItem = totalFiltered === 0 ? 0 : start + 1;
    const endItem = Math.min(start + state.pageSize, totalFiltered);
    pageInfo.textContent = `${startItem}--${endItem} of ${totalFiltered}`;
  }
}

/* ── Event handlers ── */

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  state.currentPage = 0;
  state.searchQuery = "";

  const searchInput = document.querySelector<HTMLInputElement>("#rankings-search");
  if (searchInput) searchInput.value = "";

  loadRankings();
}

function onSearchInput(event: Event): void {
  const target = event.target as HTMLInputElement;
  state.searchQuery = target.value.trim();
  state.currentPage = 0;

  if (!state.loading) {
    const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
    if (tableContainer) {
      renderFilteredTable(tableContainer);
    }
  }
}

function onBandClick(event: Event): void {
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-band]");
  if (!target) return;

  state.activeBand = target.dataset.band as RevenueBand;
  state.currentPage = 0;

  /* Update active class on band buttons */
  const bandGroup = target.closest(".control-group");
  if (bandGroup) {
    bandGroup.querySelectorAll<HTMLButtonElement>(".control-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn === target);
    });
  }

  const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
  if (tableContainer && !state.loading) {
    renderFilteredTable(tableContainer);
  }
}

function onTypeClick(event: Event): void {
  const target = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-jtype]");
  if (!target) return;

  state.activeJurisdictionFilter = target.dataset.jtype as JurisdictionFilter;
  state.currentPage = 0;

  /* Update active class on type buttons */
  const typeGroup = target.closest(".control-group");
  if (typeGroup) {
    typeGroup.querySelectorAll<HTMLButtonElement>(".control-btn").forEach((btn) => {
      btn.classList.toggle("is-active", btn === target);
    });
  }

  const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
  if (tableContainer && !state.loading) {
    renderFilteredTable(tableContainer);
  }
}

function onPrevPage(): void {
  if (state.currentPage > 0) {
    state.currentPage -= 1;
    const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
    if (tableContainer) renderFilteredTable(tableContainer);
  }
}

function onNextPage(): void {
  const filtered = getFilteredItems();
  if ((state.currentPage + 1) * state.pageSize < filtered.length) {
    state.currentPage += 1;
    const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
    if (tableContainer) renderFilteredTable(tableContainer);
  }
}

/* ── View implementation ── */

export const rankingsView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    setPageMetadata({
      title: "Oklahoma Revenue Rankings",
      description:
        "Rank Oklahoma cities and counties by municipal revenue, average monthly distributions, and year-over-year movement.",
      path: ROUTES.rankings,
    });
    container.className = "view-rankings";

    /* Reset state on fresh render */
    state.activeTaxType = "sales";
    state.currentPage = 0;
    state.searchQuery = "";
    state.activeBand = "all";
    state.activeJurisdictionFilter = "all";
    state.totalItems = [];
    state.yoyMap = new Map();
    state.loading = false;

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Revenue Rankings</h2>
        </div>
        <div id="rankings-tax-toggle" style="margin: 16px 0;"></div>
        <div class="chart-controls" style="margin-bottom:16px;" id="rankings-band-controls">
          <div class="control-group" id="band-group">
            <span class="control-label">Revenue Size</span>
            <button class="control-btn is-active" data-band="all">All</button>
            <button class="control-btn" data-band="micro">Micro &lt;$1M</button>
            <button class="control-btn" data-band="small">Small $1-10M</button>
            <button class="control-btn" data-band="medium">Med $10-100M</button>
            <button class="control-btn" data-band="large">Large $100-500M</button>
            <button class="control-btn" data-band="metro">Metro $500M+</button>
          </div>
          <div class="control-group" id="type-group">
            <span class="control-label">Type</span>
            <button class="control-btn is-active" data-jtype="all">All Types</button>
            <button class="control-btn" data-jtype="city">Cities Only</button>
            <button class="control-btn" data-jtype="county">Counties Only</button>
          </div>
        </div>
        <div style="margin-bottom: 16px;">
          <input
            type="text"
            id="rankings-search"
            class="search-input"
            placeholder="Filter by city name..."
            aria-label="Filter rankings by city name"
            style="width:100%;max-width:400px;padding:8px 12px;border:1px solid rgba(16,34,49,0.15);border-radius:6px;font-size:0.92rem;"
          />
        </div>
      </div>

      <div class="panel" style="padding: 0 30px 22px;">
        <div id="rankings-table-area"></div>
        <div class="pagination-controls" style="display:flex;align-items:center;justify-content:center;gap:14px;padding:16px 0;">
          <button id="rankings-prev" class="btn btn-secondary" disabled>Previous</button>
          <span id="rankings-page-info" class="body-copy">--</span>
          <button id="rankings-next" class="btn btn-secondary" disabled>Next</button>
        </div>
      </div>
    `;

    /* Tax toggle */
    const toggleContainer = document.querySelector<HTMLElement>("#rankings-tax-toggle");
    if (toggleContainer) {
      renderTaxToggle(
        toggleContainer,
        ["sales", "use", "lodging"],
        state.activeTaxType,
        onTaxTypeChange,
      );
    }

    /* Filter controls */
    const bandGroup = document.querySelector<HTMLElement>("#band-group");
    if (bandGroup) bandGroup.addEventListener("click", onBandClick);

    const typeGroup = document.querySelector<HTMLElement>("#type-group");
    if (typeGroup) typeGroup.addEventListener("click", onTypeClick);

    /* Search input */
    const searchInput = document.querySelector<HTMLInputElement>("#rankings-search");
    if (searchInput) {
      searchInput.addEventListener("input", onSearchInput);
    }

    /* Pagination buttons */
    const prevBtn = document.querySelector<HTMLButtonElement>("#rankings-prev");
    const nextBtn = document.querySelector<HTMLButtonElement>("#rankings-next");
    if (prevBtn) prevBtn.addEventListener("click", onPrevPage);
    if (nextBtn) nextBtn.addEventListener("click", onNextPage);

    /* Initial data load */
    loadRankings();
  },

  destroy(): void {
    state.totalItems = [];
    state.yoyMap = new Map();
    state.searchQuery = "";
    state.currentPage = 0;
    state.activeTaxType = "sales";
    state.activeBand = "all";
    state.activeJurisdictionFilter = "all";
    state.loading = false;
  },
};
