/*
   Missed Filings view -- statewide NAICS gap feed
   ══════════════════════════════════════════════ */

import { getMissedFilings } from "../api";
import { showLoading } from "../components/loading";
import { cityPath, ROUTES } from "../paths";
import { setPageMetadata } from "../seo";
import type { MissedFilingItem, MissedFilingsResponse, View } from "../types";
import { escapeHtml, formatCurrency } from "../utils";

interface MissedFilingsState {
  activeSeverity: string;
  activeTaxType: string;
  cityFilter: string;
  naicsFilter: string;
  runRateMethod: string;
  minExpectedValue: number;
  minMissingAmount: number;
  minMissingPct: number;
  minBaselineSharePct: number;
  highMissingAmount: number;
  highMissingPct: number;
  criticalMissingAmount: number;
  criticalMissingPct: number;
  startDate: string;
  endDate: string;
  sortBy: string;
  response: MissedFilingsResponse | null;
  items: MissedFilingItem[];
  requestToken: number;
  searchDebounce: number | null;
}

const PAGE_SIZE = 100;
const RUN_RATE_OPTIONS = [
  { value: "hybrid", label: "Hybrid (default)" },
  { value: "yoy", label: "YoY same month" },
  { value: "trailing_mean_3", label: "Trailing 3m avg" },
  { value: "trailing_mean_6", label: "Trailing 6m avg" },
  { value: "trailing_mean_12", label: "Trailing 12m avg" },
  { value: "trailing_median_12", label: "Trailing 12m median" },
  { value: "exp_weighted_12", label: "Exp weighted 12m" },
] as const;

const RUN_RATE_LABELS: Record<string, string> = Object.fromEntries(
  RUN_RATE_OPTIONS.map((option) => [option.value, option.label]),
);

function toIsoDate(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function defaultRecentStartDate(): string {
  const value = new Date();
  value.setDate(1);
  value.setMonth(value.getMonth() - 23);
  return toIsoDate(value);
}

function defaultRecentEndDate(): string {
  return toIsoDate(new Date());
}

const state: MissedFilingsState = {
  activeSeverity: "all",
  activeTaxType: "all",
  cityFilter: "",
  naicsFilter: "",
  runRateMethod: "hybrid",
  minExpectedValue: 5000,
  minMissingAmount: 2500,
  minMissingPct: 40,
  minBaselineSharePct: 2,
  highMissingAmount: 10000,
  highMissingPct: 60,
  criticalMissingAmount: 25000,
  criticalMissingPct: 85,
  startDate: defaultRecentStartDate(),
  endDate: defaultRecentEndDate(),
  sortBy: "severity",
  response: null,
  items: [],
  requestToken: 0,
  searchDebounce: null,
};

function resetState(): void {
  state.activeSeverity = "all";
  state.activeTaxType = "all";
  state.cityFilter = "";
  state.naicsFilter = "";
  state.runRateMethod = "hybrid";
  state.minExpectedValue = 5000;
  state.minMissingAmount = 2500;
  state.minMissingPct = 40;
  state.minBaselineSharePct = 2;
  state.highMissingAmount = 10000;
  state.highMissingPct = 60;
  state.criticalMissingAmount = 25000;
  state.criticalMissingPct = 85;
  state.startDate = defaultRecentStartDate();
  state.endDate = defaultRecentEndDate();
  state.sortBy = "severity";
  state.response = null;
  state.items = [];
  state.requestToken = 0;
  if (state.searchDebounce !== null) {
    window.clearTimeout(state.searchDebounce);
    state.searchDebounce = null;
  }
}

function severityBadge(severity: string): string {
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);

  switch (severity.toLowerCase()) {
    case "critical":
      return `<span class="anomaly-badge anomaly-badge-critical" style="background:var(--danger);color:#fff;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "high":
      return `<span class="anomaly-badge anomaly-badge-high" style="background:rgba(198,40,40,0.10);color:#91231e;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    default:
      return `<span class="anomaly-badge anomaly-badge-medium" style="background:rgba(200,146,42,0.15);border:1px solid rgba(200,146,42,0.35);color:#7a5c10;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
  }
}

function makeFilterGroup(
  label: string,
  groupClass: string,
  options: Array<{ value: string; text: string }>,
  active: string,
): string {
  return `
    <div class="control-group">
      <span class="control-label">${label}</span>
      ${options.map((option) => `
        <button class="control-btn ${groupClass}${option.value === active ? " is-active" : ""}" data-value="${option.value}">${option.text}</button>
      `).join("")}
    </div>
  `;
}

function wireFilterGroup(
  container: HTMLElement,
  groupClass: string,
  callback: (value: string) => void,
): void {
  container.querySelectorAll<HTMLButtonElement>(`.${groupClass}`).forEach((btn) => {
    btn.addEventListener("click", () => {
      container.querySelectorAll<HTMLButtonElement>(`.${groupClass}`).forEach((node) => node.classList.remove("is-active"));
      btn.classList.add("is-active");
      callback(btn.dataset.value ?? "all");
    });
  });
}

function parseNumberInput(element: HTMLInputElement, fallback: number): number {
  const parsed = Number.parseFloat(element.value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function taxLabel(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function runRateLabel(value: string): string {
  return RUN_RATE_LABELS[value] ?? value;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Not refreshed yet";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function referenceSummary(item: MissedFilingItem): string {
  const references: string[] = [];
  if (item.prior_year_value !== null) {
    references.push(`YoY: ${formatCurrency(item.prior_year_value)}`);
  }
  if (item.trailing_median_12 !== null) {
    references.push(`12m median: ${formatCurrency(item.trailing_median_12)}`);
  }
  if (item.exp_weighted_avg_12 !== null) {
    references.push(`Exp weighted: ${formatCurrency(item.exp_weighted_avg_12)}`);
  }
  return references.join(" · ");
}

function renderCard(item: MissedFilingItem): string {
  const references = referenceSummary(item);
  const monthsLabel = item.baseline_months_used === 1 ? "month" : "months";

  return `
    <article class="anomaly-card panel" style="padding:18px 24px;margin-bottom:10px;">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
        ${severityBadge(item.severity)}
        <span style="background:rgba(43,122,158,0.10);color:#1b3a5c;padding:2px 10px;border-radius:4px;font-size:0.75rem;font-weight:600;">Potential Missed Filing</span>
        <a href="${cityPath(item.copo)}" class="city-link" style="font-weight:600;font-size:0.95rem;">
          ${escapeHtml(item.city_name)}
        </a>
        <span class="body-copy" style="color:#5c6578;font-size:0.82rem;">
          ${escapeHtml(taxLabel(item.tax_type))} tax
        </span>
        <span class="body-copy" style="color:#5c6578;font-size:0.82rem;margin-left:auto;">
          ${escapeHtml(item.anomaly_date)}
        </span>
      </div>
      <p class="body-copy" style="margin:0 0 6px;font-weight:600;">
        Investigate NAICS ${escapeHtml(item.activity_code)}: ${escapeHtml(item.activity_description)}
      </p>
      <p class="body-copy" style="margin:0 0 8px;">${escapeHtml(item.recommendation)}</p>
      <p class="body-copy" style="margin:0 0 10px;color:#5c6578;font-size:0.84rem;">
        Baseline: ${escapeHtml(runRateLabel(item.baseline_method))} using ${item.baseline_months_used} ${monthsLabel}
        ${references ? ` · ${escapeHtml(references)}` : ""}
      </p>
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        <span class="body-copy" style="font-size:0.84rem;color:#5c6578;">Expected: ${formatCurrency(item.expected_value)}</span>
        <span class="body-copy" style="font-size:0.84rem;color:#5c6578;">Actual: ${formatCurrency(item.actual_value)}</span>
        <span class="body-copy" style="font-size:0.84rem;font-weight:600;color:#c62828;">Gap: ${formatCurrency(item.missing_amount)}</span>
        <span class="body-copy" style="font-size:0.84rem;color:#5c6578;">Missing: ${item.missing_pct.toFixed(1)}%</span>
        <span class="body-copy" style="font-size:0.84rem;color:#5c6578;">City baseline share: ${item.baseline_share_pct.toFixed(1)}%</span>
        <a href="${cityPath(item.copo, "industries")}" class="city-link" style="font-size:0.82rem;margin-left:auto;">
          Open industries &rarr;
        </a>
      </div>
    </article>
  `;
}

function requestOptions(offset: number): Parameters<typeof getMissedFilings>[0] {
  return {
    severity: state.activeSeverity !== "all" ? state.activeSeverity : undefined,
    taxType: state.activeTaxType !== "all" ? state.activeTaxType : undefined,
    cityQuery: state.cityFilter || undefined,
    naicsQuery: state.naicsFilter || undefined,
    runRateMethod: state.runRateMethod,
    sortBy: state.sortBy,
    startDate: state.startDate,
    endDate: state.endDate,
    minExpectedValue: state.minExpectedValue,
    minMissingAmount: state.minMissingAmount,
    minMissingPct: state.minMissingPct,
    minBaselineSharePct: state.minBaselineSharePct,
    highMissingAmount: state.highMissingAmount,
    highMissingPct: state.highMissingPct,
    criticalMissingAmount: state.criticalMissingAmount,
    criticalMissingPct: state.criticalMissingPct,
    limit: PAGE_SIZE,
    offset,
  };
}

function renderList(container: HTMLElement): void {
  const response = state.response;
  if (!response) {
    container.innerHTML = "";
    return;
  }

  if (!state.items.length) {
    container.innerHTML = `
      <div class="panel" style="padding:20px 24px;">
        <p class="body-copy" style="margin:0 0 6px;">No missed filing candidates match these filters.</p>
        <p class="body-copy" style="margin:0;color:#5c6578;font-size:0.84rem;">
          Snapshot refreshed ${escapeHtml(formatTimestamp(response.refresh_info.last_refresh_at))}.
        </p>
      </div>
    `;
    return;
  }

  const dataWindow = [
    response.refresh_info.data_min_month,
    response.refresh_info.data_max_month,
  ].filter(Boolean).join(" to ");
  const cards = state.items.map(renderCard).join("");
  const loadMore = response.has_more
    ? `<div style="display:flex;justify-content:center;padding:12px 0 4px;">
        <button id="missed-filings-load-more" class="button button-ghost" style="min-height:38px;padding:0 18px;font-size:0.84rem;">Load 100 more</button>
      </div>`
    : "";

  container.innerHTML = `
    <div class="panel" style="padding:16px 20px;margin-bottom:12px;">
      <p class="body-copy" style="margin:0 0 6px;color:#5c6578;">
        Showing ${state.items.length} candidate${state.items.length === 1 ? "" : "s"} from a ${response.refresh_info.snapshot_row_count.toLocaleString()}-row snapshot${response.has_more ? " with more available." : "."}
      </p>
      <p class="body-copy" style="margin:0;color:#5c6578;font-size:0.84rem;">
        Last refreshed: ${escapeHtml(formatTimestamp(response.refresh_info.last_refresh_at))}
        ${dataWindow ? ` · Data window: ${escapeHtml(dataWindow)}` : ""}
        ${response.refresh_info.refresh_duration_seconds !== null ? ` · Refresh runtime: ${escapeHtml(response.refresh_info.refresh_duration_seconds.toFixed(1))}s` : ""}
      </p>
    </div>
    ${cards}
    ${loadMore}
  `;

  container.querySelector<HTMLButtonElement>("#missed-filings-load-more")
    ?.addEventListener("click", () => {
      void loadMissedFilings(false);
    });
}

async function loadMissedFilings(reset: boolean): Promise<void> {
  const listContainer = document.querySelector<HTMLElement>("#missed-filings-list");
  if (!listContainer) return;

  const requestToken = ++state.requestToken;
  const offset = reset ? 0 : state.items.length;

  if (reset) {
    showLoading(listContainer);
  }

  try {
    const data = await getMissedFilings(requestOptions(offset));
    if (requestToken !== state.requestToken) {
      return;
    }

    state.response = data;
    state.items = reset ? data.items : [...state.items, ...data.items];
    state.response = {
      ...data,
      items: state.items,
      count: state.items.length,
      offset: 0,
      has_more: data.has_more,
    };
    renderList(listContainer);
  } catch (error) {
    if (requestToken !== state.requestToken) {
      return;
    }
    listContainer.innerHTML = `
      <p class="body-copy" style="padding:20px;color:var(--danger)">
        ${escapeHtml(error instanceof Error ? error.message : "Failed to load missed filing data.")}
      </p>
    `;
  }
}

function queueSearchReload(): void {
  if (state.searchDebounce !== null) {
    window.clearTimeout(state.searchDebounce);
  }
  state.searchDebounce = window.setTimeout(() => {
    state.searchDebounce = null;
    void loadMissedFilings(true);
  }, 250);
}

function wireReloadInput(
  container: HTMLElement,
  selector: string,
  callback: (element: HTMLInputElement) => void,
): void {
  container.querySelector<HTMLInputElement>(selector)?.addEventListener("change", (event) => {
    callback(event.target as HTMLInputElement);
    void loadMissedFilings(true);
  });
}

export const missedFilingsView: View = {
  render(container: HTMLElement): void {
    setPageMetadata({
      title: "Missed Filings Detection",
      description:
        "Identify likely missed Oklahoma municipal tax filings using NAICS-level run-rate gaps, severity thresholds, and trailing revenue baselines.",
      path: ROUTES.missedFilings,
    });
    container.className = "view-anomalies";
    resetState();

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 20px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Missed Filings</h2>
        </div>
        <p class="body-copy" style="margin-bottom:8px;">
          Directional NAICS-level filing gaps for the last 24 months. The default baseline blends same-month prior year with a trailing 12-month median so low-sided anomalies keep seasonality while staying robust to one-off spikes.
        </p>
        <p class="body-copy" style="margin-bottom:16px;color:#5c6578;font-size:0.85rem;">
          Sales and use only. Lodging is excluded because the current data pipeline does not have lodging-by-NAICS source files. Share thresholds are measured against a city-level baseline, not the already-depressed current month.
        </p>

        <div class="chart-controls" style="gap:12px;">
          ${makeFilterGroup("Severity", "missed-sev-btn", [
            { value: "all", text: "All" },
            { value: "critical", text: "Critical" },
            { value: "high", text: "High" },
            { value: "medium", text: "Medium" },
          ], "all")}

          ${makeFilterGroup("Tax Type", "missed-tax-btn", [
            { value: "all", text: "All" },
            { value: "sales", text: "Sales" },
            { value: "use", text: "Use" },
          ], "all")}

          ${makeFilterGroup("Sort", "missed-sort-btn", [
            { value: "severity", text: "Severity" },
            { value: "amount", text: "Gap $" },
            { value: "pct", text: "Gap %" },
            { value: "share", text: "City share %" },
            { value: "date", text: "Date" },
            { value: "city", text: "City" },
          ], "severity")}
        </div>

        <div style="display:flex;gap:12px;margin-top:12px;flex-wrap:wrap;align-items:center;">
          <input id="missed-city-search" type="text" placeholder="Search city name..."
            class="city-search-input" style="max-width:240px;padding:8px 12px;font-size:0.85rem;" />
          <input id="missed-naics-search" type="text" placeholder="Search NAICS code or industry..."
            class="city-search-input" style="max-width:280px;padding:8px 12px;font-size:0.85rem;" />
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Run rate:
            <select id="missed-run-rate"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;">
              ${RUN_RATE_OPTIONS.map((option) => `
                <option value="${option.value}"${option.value === state.runRateMethod ? " selected" : ""}>${option.label}</option>
              `).join("")}
            </select>
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Min expected:
            <input id="missed-min-expected" type="number" min="0" value="${state.minExpectedValue}" step="2500"
              style="width:96px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />$
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Min gap:
            <input id="missed-min-gap" type="number" min="0" value="${state.minMissingAmount}" step="2500"
              style="width:96px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />$
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Min gap %:
            <input id="missed-min-gap-pct" type="number" min="0" max="100" value="${state.minMissingPct}" step="5"
              style="width:72px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />%
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Min city share %:
            <input id="missed-min-share-pct" type="number" min="0" max="100" value="${state.minBaselineSharePct}" step="0.5"
              style="width:72px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />%
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            From:
            <input id="missed-start-date" type="date" value="${state.startDate}"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            To:
            <input id="missed-end-date" type="date" value="${state.endDate}"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
        </div>

        <div style="display:flex;gap:12px;margin-top:10px;flex-wrap:wrap;align-items:center;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;font-weight:600;">Severity thresholds:</span>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            High $:
            <input id="missed-high-gap" type="number" min="0" value="${state.highMissingAmount}" step="2500"
              style="width:96px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            High %:
            <input id="missed-high-gap-pct" type="number" min="0" max="100" value="${state.highMissingPct}" step="5"
              style="width:72px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Critical $:
            <input id="missed-critical-gap" type="number" min="0" value="${state.criticalMissingAmount}" step="2500"
              style="width:96px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            Critical %:
            <input id="missed-critical-gap-pct" type="number" min="0" max="100" value="${state.criticalMissingPct}" step="5"
              style="width:72px;padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
        </div>
      </div>

      <div id="missed-filings-list" style="padding:0 4px;"></div>
    `;

    wireFilterGroup(container, "missed-sev-btn", (value) => {
      state.activeSeverity = value;
      void loadMissedFilings(true);
    });
    wireFilterGroup(container, "missed-tax-btn", (value) => {
      state.activeTaxType = value;
      void loadMissedFilings(true);
    });
    wireFilterGroup(container, "missed-sort-btn", (value) => {
      state.sortBy = value;
      void loadMissedFilings(true);
    });

    container.querySelector<HTMLInputElement>("#missed-city-search")
      ?.addEventListener("input", (event) => {
        state.cityFilter = (event.target as HTMLInputElement).value.trim();
        queueSearchReload();
      });

    container.querySelector<HTMLInputElement>("#missed-naics-search")
      ?.addEventListener("input", (event) => {
        state.naicsFilter = (event.target as HTMLInputElement).value.trim();
        queueSearchReload();
      });

    container.querySelector<HTMLSelectElement>("#missed-run-rate")
      ?.addEventListener("change", (event) => {
        state.runRateMethod = (event.target as HTMLSelectElement).value;
        void loadMissedFilings(true);
      });

    wireReloadInput(container, "#missed-min-expected", (element) => {
      state.minExpectedValue = parseNumberInput(element, state.minExpectedValue);
    });
    wireReloadInput(container, "#missed-min-gap", (element) => {
      state.minMissingAmount = parseNumberInput(element, state.minMissingAmount);
    });
    wireReloadInput(container, "#missed-min-gap-pct", (element) => {
      state.minMissingPct = parseNumberInput(element, state.minMissingPct);
    });
    wireReloadInput(container, "#missed-min-share-pct", (element) => {
      state.minBaselineSharePct = parseNumberInput(element, state.minBaselineSharePct);
    });
    wireReloadInput(container, "#missed-high-gap", (element) => {
      state.highMissingAmount = parseNumberInput(element, state.highMissingAmount);
    });
    wireReloadInput(container, "#missed-high-gap-pct", (element) => {
      state.highMissingPct = parseNumberInput(element, state.highMissingPct);
    });
    wireReloadInput(container, "#missed-critical-gap", (element) => {
      state.criticalMissingAmount = parseNumberInput(element, state.criticalMissingAmount);
    });
    wireReloadInput(container, "#missed-critical-gap-pct", (element) => {
      state.criticalMissingPct = parseNumberInput(element, state.criticalMissingPct);
    });
    wireReloadInput(container, "#missed-start-date", (element) => {
      state.startDate = element.value;
    });
    wireReloadInput(container, "#missed-end-date", (element) => {
      state.endDate = element.value;
    });

    void loadMissedFilings(true);
  },

  destroy(): void {
    resetState();
  },
};
