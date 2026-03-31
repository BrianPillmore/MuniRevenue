/* ══════════════════════════════════════════════
   Rankings view -- Jurisdictions ranked by revenue
   ══════════════════════════════════════════════ */

import { getRankings } from "../api";
import { renderTaxToggle } from "../components/tax-toggle";
import type { RankingsResponse, View } from "../types";
import {
  escapeHtml,
  formatCompactCurrency,
  wrapTable,
} from "../utils";

/* ── State ── */

interface RankingsState {
  activeTaxType: string;
  currentOffset: number;
  pageSize: number;
  searchQuery: string;
  latestData: RankingsResponse | null;
}

const state: RankingsState = {
  activeTaxType: "sales",
  currentOffset: 0,
  pageSize: 50,
  searchQuery: "",
  latestData: null,
};

/* ── Data fetching and rendering ── */

async function loadRankings(): Promise<void> {
  const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
  if (!tableContainer) return;

  tableContainer.innerHTML =
    '<p class="body-copy" style="padding:20px;text-align:center;">Loading rankings...</p>';

  try {
    const data = await getRankings(
      state.activeTaxType,
      "total_returned",
      state.pageSize,
      state.currentOffset,
    );
    state.latestData = data;
    renderTable(data, tableContainer);
  } catch {
    tableContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load rankings data.</p>';
  }
}

function renderTable(data: RankingsResponse, container: HTMLElement): void {
  if (!data.items.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No ranking data available for this tax type.</p>';
    return;
  }

  /* Apply client-side search filter */
  const query = state.searchQuery.toLowerCase();
  const filtered = query
    ? data.items.filter((item) => item.name.toLowerCase().includes(query))
    : data.items;

  if (!filtered.length) {
    container.innerHTML = `
      <p class="body-copy" style="padding:20px;text-align:center;">
        No jurisdictions matching "${escapeHtml(state.searchQuery)}".
      </p>
    `;
    updatePaginationControls(data);
    return;
  }

  const rows = filtered
    .map(
      (item) => `
        <tr>
          <td>${item.rank}</td>
          <td>
            <a href="#/city/${encodeURIComponent(item.copo)}" class="city-link">
              ${escapeHtml(item.name)}
            </a>
          </td>
          <td>${item.county_name ? escapeHtml(item.county_name) : "N/A"}</td>
          <td>${escapeHtml(item.jurisdiction_type)}</td>
          <td>${item.metric_value !== null ? formatCompactCurrency(item.metric_value) : "N/A"}</td>
          <td>${item.rank}</td>
        </tr>
      `,
    )
    .join("");

  container.innerHTML = wrapTable(
    ["#", "City / County", "County", "Type", "Total Returned", "Rank"],
    rows,
  );

  updatePaginationControls(data);
}

function updatePaginationControls(data: RankingsResponse): void {
  const prevBtn = document.querySelector<HTMLButtonElement>("#rankings-prev");
  const nextBtn = document.querySelector<HTMLButtonElement>("#rankings-next");
  const pageInfo = document.querySelector<HTMLElement>("#rankings-page-info");

  if (prevBtn) {
    prevBtn.disabled = state.currentOffset === 0;
  }
  if (nextBtn) {
    nextBtn.disabled = state.currentOffset + state.pageSize >= data.total;
  }
  if (pageInfo) {
    const startItem = data.total === 0 ? 0 : state.currentOffset + 1;
    const endItem = Math.min(state.currentOffset + state.pageSize, data.total);
    pageInfo.textContent = `${startItem}--${endItem} of ${data.total}`;
  }
}

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;
  state.currentOffset = 0;
  state.searchQuery = "";

  /* Clear the search input */
  const searchInput = document.querySelector<HTMLInputElement>("#rankings-search");
  if (searchInput) searchInput.value = "";

  loadRankings();
}

function onSearchInput(event: Event): void {
  const target = event.target as HTMLInputElement;
  state.searchQuery = target.value.trim();

  /* Re-render current data with the new filter (no refetch needed) */
  if (state.latestData) {
    const tableContainer = document.querySelector<HTMLElement>("#rankings-table-area");
    if (tableContainer) {
      renderTable(state.latestData, tableContainer);
    }
  }
}

function onPrevPage(): void {
  if (state.currentOffset > 0) {
    state.currentOffset = Math.max(0, state.currentOffset - state.pageSize);
    loadRankings();
  }
}

function onNextPage(): void {
  if (state.latestData && state.currentOffset + state.pageSize < state.latestData.total) {
    state.currentOffset += state.pageSize;
    loadRankings();
  }
}

/* ── View implementation ── */

export const rankingsView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-rankings";

    /* Reset state on fresh render */
    state.activeTaxType = "sales";
    state.currentOffset = 0;
    state.searchQuery = "";
    state.latestData = null;

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Revenue Rankings</h2>
        </div>
        <div id="rankings-tax-toggle" style="margin: 16px 0;"></div>
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
    state.latestData = null;
    state.searchQuery = "";
    state.currentOffset = 0;
    state.activeTaxType = "sales";
  },
};
