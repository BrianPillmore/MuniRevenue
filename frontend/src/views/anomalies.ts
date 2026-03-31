/* ══════════════════════════════════════════════
   Anomalies view -- Statewide anomaly feed
   ══════════════════════════════════════════════ */

import { getAnomalies } from "../api";
import { showLoading } from "../components/loading";
import type { AnomaliesResponse, AnomalyItem, View } from "../types";
import {
  escapeHtml,
  formatCurrency,
  formatPercent,
} from "../utils";

/* ── State ── */

interface AnomaliesState {
  activeSeverity: string;
  activeTaxType: string;
  activeAnomalyType: string;
  cityFilter: string;
  minDeviation: number;
  minVariance: number;
  startDate: string;
  endDate: string;
  sortBy: string;
  data: AnomaliesResponse | null;
  allItems: AnomalyItem[];
}

const state: AnomaliesState = {
  activeSeverity: "all",
  activeTaxType: "all",
  activeAnomalyType: "all",
  cityFilter: "",
  minDeviation: 0,
  minVariance: 1000,
  startDate: "",
  endDate: "",
  sortBy: "severity",
  data: null,
  allItems: [],
};

/* ── Severity badge rendering ── */

function severityBadge(severity: string): string {
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);

  switch (severity.toLowerCase()) {
    case "critical":
      return `<span class="anomaly-badge anomaly-badge-critical" style="background:var(--brand);color:#fff;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "high":
      return `<span class="anomaly-badge anomaly-badge-high" style="background:rgba(166,61,64,0.15);color:var(--brand-deep,#a63d40);padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "medium":
      return `<span class="anomaly-badge anomaly-badge-medium" style="background:rgba(215,176,101,0.2);border:1px solid rgba(212,168,67,0.4);color:#8a6d1b;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "low":
      return `<span class="anomaly-badge anomaly-badge-low" style="background:rgba(29,107,112,0.08);color:#1d6b70;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    default:
      return `<span class="anomaly-badge" style="padding:2px 10px;border-radius:4px;font-size:0.78rem;">${label}</span>`;
  }
}

/* ── Type badge rendering ── */

function typeBadge(anomalyType: string): string {
  const labels: Record<string, string> = {
    yoy_spike: "YoY Spike",
    yoy_drop: "YoY Drop",
    mom_outlier: "MoM Outlier",
    missing_data: "Missing Data",
    naics_shift: "NAICS Shift",
  };
  const colors: Record<string, string> = {
    yoy_spike: "background:rgba(29,107,112,0.12);color:#1d6b70",
    yoy_drop: "background:rgba(166,61,64,0.12);color:#a63d40",
    mom_outlier: "background:rgba(215,176,101,0.15);color:#8a6d1b",
    missing_data: "background:rgba(93,107,117,0.12);color:#5d6b75",
    naics_shift: "background:rgba(47,111,116,0.12);color:#2f6f74",
  };
  const label = labels[anomalyType] || anomalyType;
  const style = colors[anomalyType] || "background:rgba(93,107,117,0.08);color:#5d6b75";
  return `<span style="${style};padding:2px 10px;border-radius:4px;font-size:0.75rem;font-weight:600;">${label}</span>`;
}

/* ── Card rendering ── */

function renderAnomalyCard(item: AnomalyItem): string {
  const taxLabel = item.tax_type.charAt(0).toUpperCase() + item.tax_type.slice(1);
  const deviationSign = item.deviation_pct >= 0 ? "+" : "";

  const expectedStr = item.expected_value !== null
    ? `Expected: ${formatCurrency(item.expected_value)}`
    : "";
  const actualStr = item.actual_value !== null
    ? `Actual: ${formatCurrency(item.actual_value)}`
    : "";
  const variance = (item.actual_value !== null && item.expected_value !== null)
    ? Math.abs(item.actual_value - item.expected_value)
    : 0;
  const metricsLine = [expectedStr, actualStr, `Variance: ${formatCurrency(variance)}`]
    .filter(Boolean)
    .join(" | ");

  return `
    <article class="anomaly-card panel" style="padding:18px 24px;margin-bottom:10px;">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
        ${severityBadge(item.severity)}
        ${typeBadge(item.anomaly_type)}
        <a href="#/city/${encodeURIComponent(item.copo)}" class="city-link" style="font-weight:600;font-size:0.95rem;">
          ${escapeHtml(item.city_name)}
        </a>
        <span class="body-copy" style="color:#5d6b75;font-size:0.82rem;">
          ${escapeHtml(taxLabel)} tax
        </span>
        <span class="body-copy" style="color:#5d6b75;font-size:0.82rem;margin-left:auto;">
          ${escapeHtml(item.anomaly_date)}
        </span>
      </div>
      <p class="body-copy" style="margin:0 0 6px;">${escapeHtml(item.description)}</p>
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        ${metricsLine ? `<span class="body-copy" style="font-size:0.85rem;color:#5d6b75;">${metricsLine}</span>` : ""}
        <span class="body-copy" style="font-size:0.85rem;font-weight:600;color:${item.deviation_pct >= 0 ? "#1d6b70" : "var(--brand)"};">
          Deviation: ${deviationSign}${item.deviation_pct.toFixed(1)}%
        </span>
        <a href="#/city/${encodeURIComponent(item.copo)}" class="city-link" style="font-size:0.82rem;margin-left:auto;">
          View city &rarr;
        </a>
      </div>
    </article>
  `;
}

/* ── Data loading and filtering ── */

async function loadAnomalies(): Promise<void> {
  const listContainer = document.querySelector<HTMLElement>("#anomalies-list");
  if (!listContainer) return;

  showLoading(listContainer);

  try {
    const data = await getAnomalies(undefined, undefined, undefined, 5000);
    state.data = data;
    state.allItems = data.items;
    applyFiltersAndRender();
  } catch {
    listContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load anomaly data.</p>';
  }
}

function applyFiltersAndRender(): void {
  const listContainer = document.querySelector<HTMLElement>("#anomalies-list");
  if (!listContainer) return;

  let filtered = [...state.allItems];

  // Severity filter
  if (state.activeSeverity !== "all") {
    filtered = filtered.filter((a) => a.severity === state.activeSeverity);
  }

  // Tax type filter
  if (state.activeTaxType !== "all") {
    filtered = filtered.filter((a) => a.tax_type === state.activeTaxType);
  }

  // Anomaly type filter
  if (state.activeAnomalyType !== "all") {
    filtered = filtered.filter((a) => a.anomaly_type === state.activeAnomalyType);
  }

  // City name search
  if (state.cityFilter) {
    const q = state.cityFilter.toLowerCase();
    filtered = filtered.filter((a) => a.city_name.toLowerCase().includes(q));
  }

  // Min deviation filter
  if (state.minDeviation > 0) {
    filtered = filtered.filter((a) => Math.abs(a.deviation_pct) >= state.minDeviation);
  }

  // Min variance filter (absolute dollar difference)
  if (state.minVariance > 0) {
    filtered = filtered.filter((a) => {
      if (a.actual_value === null || a.expected_value === null) return true;
      return Math.abs(a.actual_value - a.expected_value) >= state.minVariance;
    });
  }

  // Date range filter
  if (state.startDate) {
    filtered = filtered.filter((a) => a.anomaly_date >= state.startDate);
  }
  if (state.endDate) {
    filtered = filtered.filter((a) => a.anomaly_date <= state.endDate);
  }

  // Sort
  switch (state.sortBy) {
    case "deviation":
      filtered.sort((a, b) => Math.abs(b.deviation_pct) - Math.abs(a.deviation_pct));
      break;
    case "amount":
      filtered.sort((a, b) => (b.actual_value ?? 0) - (a.actual_value ?? 0));
      break;
    case "date":
      filtered.sort((a, b) => b.anomaly_date.localeCompare(a.anomaly_date));
      break;
    case "city":
      filtered.sort((a, b) => a.city_name.localeCompare(b.city_name));
      break;
    default: // severity
      const sevOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
      filtered.sort((a, b) => (sevOrder[a.severity] ?? 4) - (sevOrder[b.severity] ?? 4));
      break;
  }

  if (!filtered.length) {
    listContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No anomalies match these filters.</p>';
    return;
  }

  const showing = Math.min(filtered.length, 100);
  const countLabel = `<p class="body-copy" style="margin-bottom:12px;color:#5d6b75;">Showing ${showing} of ${filtered.length} anomalies (${state.allItems.length} total)</p>`;
  const cards = filtered.slice(0, 100).map(renderAnomalyCard).join("");
  listContainer.innerHTML = countLabel + cards;
}

/* ── Filter control helpers ── */

function makeFilterGroup(label: string, groupClass: string, options: {value: string, text: string}[], active: string): string {
  return `
    <div class="control-group">
      <span class="control-label">${label}</span>
      ${options.map((o) => `
        <button class="control-btn ${groupClass}${o.value === active ? " is-active" : ""}" data-value="${o.value}">${o.text}</button>
      `).join("")}
    </div>
  `;
}

function wireFilterGroup(container: HTMLElement, groupClass: string, callback: (value: string) => void): void {
  container.querySelectorAll<HTMLButtonElement>(`.${groupClass}`).forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll<HTMLButtonElement>(`.${groupClass}`).forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      callback(btn.dataset.value ?? "all");
    });
  });
}

/* ── View implementation ── */

export const anomaliesView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-anomalies";

    /* Reset state */
    state.activeSeverity = "all";
    state.activeTaxType = "all";
    state.activeAnomalyType = "all";
    state.cityFilter = "";
    state.minDeviation = 0;
    state.sortBy = "severity";
    state.data = null;
    state.allItems = [];

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 20px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Anomalies</h2>
        </div>
        <p class="body-copy" style="margin-bottom:16px;">
          Revenue anomalies detected across all Oklahoma municipalities. Use filters to narrow results.
        </p>

        <div class="chart-controls" style="gap:12px;">
          ${makeFilterGroup("Severity", "sev-btn", [
            {value: "all", text: "All"}, {value: "critical", text: "Critical"},
            {value: "high", text: "High"}, {value: "medium", text: "Medium"}, {value: "low", text: "Low"},
          ], "all")}

          ${makeFilterGroup("Tax Type", "tax-btn", [
            {value: "all", text: "All"}, {value: "sales", text: "Sales"},
            {value: "use", text: "Use"}, {value: "lodging", text: "Lodging"},
          ], "all")}

          ${makeFilterGroup("Type", "type-btn", [
            {value: "all", text: "All"}, {value: "yoy_spike", text: "YoY Spike"},
            {value: "yoy_drop", text: "YoY Drop"}, {value: "mom_outlier", text: "MoM Outlier"},
          ], "all")}

          ${makeFilterGroup("Sort", "sort-btn", [
            {value: "severity", text: "Severity"}, {value: "deviation", text: "Deviation"},
            {value: "amount", text: "Amount"}, {value: "date", text: "Date"}, {value: "city", text: "City"},
          ], "severity")}
        </div>

        <div style="display:flex;gap:12px;margin-top:12px;flex-wrap:wrap;align-items:center;">
          <input id="anomaly-city-search" type="text" placeholder="Filter by city name..."
            class="city-search-input" style="max-width:240px;padding:8px 12px;font-size:0.85rem;" />
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Min deviation:
            <input id="anomaly-min-dev" type="number" min="0" max="100" value="0" step="5"
              style="width:60px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />%
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Min variance:
            <input id="anomaly-min-variance" type="number" min="0" value="1000" step="1000"
              style="width:80px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />$
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            From:
            <input id="anomaly-start-date" type="date"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            To:
            <input id="anomaly-end-date" type="date"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
        </div>
      </div>

      <div id="anomalies-list" style="padding:0 4px;"></div>
    `;

    /* Wire filter buttons */
    wireFilterGroup(container, "sev-btn", (v) => { state.activeSeverity = v; applyFiltersAndRender(); });
    wireFilterGroup(container, "tax-btn", (v) => { state.activeTaxType = v; applyFiltersAndRender(); });
    wireFilterGroup(container, "type-btn", (v) => { state.activeAnomalyType = v; applyFiltersAndRender(); });
    wireFilterGroup(container, "sort-btn", (v) => { state.sortBy = v; applyFiltersAndRender(); });

    /* City search */
    const cityInput = container.querySelector<HTMLInputElement>("#anomaly-city-search");
    cityInput?.addEventListener("input", () => {
      state.cityFilter = cityInput.value;
      applyFiltersAndRender();
    });

    /* Min deviation */
    const devInput = container.querySelector<HTMLInputElement>("#anomaly-min-dev");
    devInput?.addEventListener("input", () => {
      state.minDeviation = parseFloat(devInput.value) || 0;
      applyFiltersAndRender();
    });

    /* Min variance */
    const varInput = container.querySelector<HTMLInputElement>("#anomaly-min-variance");
    varInput?.addEventListener("input", () => {
      state.minVariance = parseFloat(varInput.value) || 0;
      applyFiltersAndRender();
    });

    /* Date range */
    const startInput = container.querySelector<HTMLInputElement>("#anomaly-start-date");
    startInput?.addEventListener("input", () => {
      state.startDate = startInput.value;
      applyFiltersAndRender();
    });
    const endInput = container.querySelector<HTMLInputElement>("#anomaly-end-date");
    endInput?.addEventListener("input", () => {
      state.endDate = endInput.value;
      applyFiltersAndRender();
    });

    /* Initial load */
    loadAnomalies();
  },

  destroy(): void {
    state.activeSeverity = "all";
    state.activeTaxType = "all";
    state.activeAnomalyType = "all";
    state.cityFilter = "";
    state.minDeviation = 0;
    state.minVariance = 1000;
    state.startDate = "";
    state.endDate = "";
    state.sortBy = "severity";
    state.data = null;
    state.allItems = [];
  },
};
