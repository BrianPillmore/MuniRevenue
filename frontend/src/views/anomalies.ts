/* ══════════════════════════════════════════════
   Anomalies view -- Statewide anomaly feed
   ══════════════════════════════════════════════ */

import { getAnomalies, getAnomalyDecomposition } from "../api";
import { showLoading } from "../components/loading";
import { cityPath, ROUTES } from "../paths";
import { setPageMetadata } from "../seo";
import Highcharts from "../theme";
import type { AnomaliesResponse, AnomalyItem, View } from "../types";
import {
  escapeHtml,
  formatCompactCurrency,
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
  expandedCardId: string | null;
  visibleCount: number;
}

const CARD_PAGE_SIZE = 100;

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

const state: AnomaliesState = {
  activeSeverity: "all",
  activeTaxType: "all",
  activeAnomalyType: "all",
  cityFilter: "",
  minDeviation: 0,
  minVariance: 1000,
  startDate: defaultRecentStartDate(),
  endDate: defaultRecentEndDate(),
  sortBy: "severity",
  data: null,
  allItems: [],
  expandedCardId: null,
  visibleCount: CARD_PAGE_SIZE,
};

/* ── Decomposition chart instance (destroyed on collapse) ── */

let decompChart: any = null;

function destroyDecompChart(): void {
  if (decompChart) {
    decompChart.destroy();
    decompChart = null;
  }
}

/* ── Severity badge rendering ── */

function severityBadge(severity: string): string {
  const label = severity.charAt(0).toUpperCase() + severity.slice(1);

  switch (severity.toLowerCase()) {
    case "critical":
      return `<span class="anomaly-badge anomaly-badge-critical" style="background:var(--danger);color:#fff;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "high":
      return `<span class="anomaly-badge anomaly-badge-high" style="background:rgba(198,40,40,0.10);color:#91231e;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "medium":
      return `<span class="anomaly-badge anomaly-badge-medium" style="background:rgba(200,146,42,0.15);border:1px solid rgba(200,146,42,0.35);color:#7a5c10;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
    case "low":
      return `<span class="anomaly-badge anomaly-badge-low" style="background:rgba(43,122,158,0.08);color:#1b3a5c;padding:2px 10px;border-radius:4px;font-size:0.78rem;font-weight:600;">${label}</span>`;
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
    yoy_spike: "background:rgba(43,122,158,0.10);color:#1b3a5c",
    yoy_drop: "background:rgba(198,40,40,0.10);color:#c62828",
    mom_outlier: "background:rgba(200,146,42,0.12);color:#7a5c10",
    missing_data: "background:rgba(92,101,120,0.10);color:#5c6578",
    naics_shift: "background:rgba(43,122,158,0.10);color:#2b7a9e",
  };
  const label = labels[anomalyType] || anomalyType;
  const style = colors[anomalyType] || "background:rgba(92,101,120,0.08);color:#5c6578";
  return `<span style="${style};padding:2px 10px;border-radius:4px;font-size:0.75rem;font-weight:600;">${label}</span>`;
}

/* ── Unique card ID for expand/collapse tracking ── */

function cardId(item: AnomalyItem): string {
  return `${item.copo}__${item.anomaly_date}__${item.tax_type}__${item.anomaly_type}`;
}

/* ── Determine comparison parameter from anomaly type ── */

function comparisonForType(anomalyType: string): string {
  if (anomalyType === "mom_outlier") return "mom";
  return "yoy";
}

/* ── Whether a tax type supports NAICS investigation ── */

function supportsInvestigation(taxType: string): boolean {
  const t = taxType.toLowerCase();
  return t === "sales" || t === "use";
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

  const cid = cardId(item);
  const isExpanded = state.expandedCardId === cid;
  const showInvestigate = supportsInvestigation(item.tax_type);

  const investigateBtn = showInvestigate
    ? `<button class="investigate-btn" data-card-id="${cid}" data-copo="${escapeHtml(item.copo)}" data-anomaly-date="${escapeHtml(item.anomaly_date)}" data-tax-type="${escapeHtml(item.tax_type)}" data-anomaly-type="${escapeHtml(item.anomaly_type)}" style="font-size:0.82rem;padding:4px 14px;border:1px solid #2b7a9e;border-radius:6px;background:${isExpanded ? "#2b7a9e" : "rgba(43,122,158,0.08)"};color:${isExpanded ? "#fff" : "#2b7a9e"};cursor:pointer;font-weight:600;transition:background 0.15s,color 0.15s;">${isExpanded ? "Close" : "Investigate"}</button>`
    : "";

  const drilldownPanel = isExpanded
    ? `<div class="investigate-panel" id="panel-${cid}" style="margin-top:14px;padding:18px 20px;background:rgba(43,122,158,0.03);border:1px solid rgba(43,122,158,0.12);border-radius:8px;">
        <div class="investigate-panel-content" style="display:flex;align-items:center;justify-content:center;padding:30px 0;">
          <span class="body-copy" style="color:#5c6578;">Loading decomposition...</span>
        </div>
      </div>`
    : "";

  return `
    <article class="anomaly-card panel" data-card-id="${cid}" style="padding:18px 24px;margin-bottom:10px;">
      <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
        ${severityBadge(item.severity)}
        ${typeBadge(item.anomaly_type)}
        <a href="${cityPath(item.copo)}" class="city-link" style="font-weight:600;font-size:0.95rem;">
          ${escapeHtml(item.city_name)}
        </a>
        <span class="body-copy" style="color:#5c6578;font-size:0.82rem;">
          ${escapeHtml(taxLabel)} tax
        </span>
        <span class="body-copy" style="color:#5c6578;font-size:0.82rem;margin-left:auto;">
          ${escapeHtml(item.anomaly_date)}
        </span>
      </div>
      <p class="body-copy" style="margin:0 0 6px;">${escapeHtml(item.description)}</p>
      <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
        ${metricsLine ? `<span class="body-copy" style="font-size:0.85rem;color:#5c6578;">${metricsLine}</span>` : ""}
        <span class="body-copy" style="font-size:0.85rem;font-weight:600;color:${item.deviation_pct >= 0 ? "#2e7d32" : "#c62828"};">
          Deviation: ${deviationSign}${item.deviation_pct.toFixed(1)}%
        </span>
        ${investigateBtn}
        <a href="${cityPath(item.copo)}" class="city-link" style="font-size:0.82rem;margin-left:auto;">
          View city &rarr;
        </a>
      </div>
      ${drilldownPanel}
    </article>
  `;
}

/* ── Decomposition rendering ── */

function renderDecompositionContent(panelContent: HTMLElement, data: any): void {
  destroyDecompChart();

  const industries: any[] = data.industries || [];
  const totalChangePct = data.total_change_pct ?? 0;
  const changePctSign = totalChangePct >= 0 ? "+" : "";

  /* Sort by absolute change descending */
  const sorted = [...industries].sort(
    (a, b) => Math.abs(b.change_amount ?? 0) - Math.abs(a.change_amount ?? 0),
  );

  /* Top 5 increases and top 5 decreases */
  const increases = sorted.filter((i) => (i.change_amount ?? 0) > 0).slice(0, 5);
  const decreases = sorted.filter((i) => (i.change_amount ?? 0) < 0).slice(0, 5);
  const chartItems = [...decreases.reverse(), ...increases];

  /* Summary line */
  const shiftCount = industries.filter(
    (i) => Math.abs(i.change_amount ?? 0) > 0,
  ).length;
  const summaryLine = `Revenue changed ${changePctSign}${totalChangePct.toFixed(1)}% &mdash; driven by ${shiftCount} industry shift${shiftCount !== 1 ? "s" : ""}`;

  /* Find max absolute contribution for inline bar scaling */
  const maxContrib = Math.max(
    ...industries.map((i) => Math.abs(i.contribution_pct ?? 0)),
    1,
  );

  /* Build decomposition table rows */
  const tableRows = sorted.map((ind) => {
    const changeAmt = ind.change_amount ?? 0;
    const changePct = ind.change_pct ?? 0;
    const contribPct = ind.contribution_pct ?? 0;
    const changeColor = changeAmt >= 0 ? "#2e7d32" : "#c62828";
    const barWidth = Math.min(Math.abs(contribPct) / maxContrib * 100, 100);
    const barColor = contribPct >= 0 ? "rgba(46,125,50,0.25)" : "rgba(198,40,40,0.25)";
    const contribSign = contribPct >= 0 ? "+" : "";

    return `
      <tr>
        <td style="font-size:0.82rem;font-family:monospace;">${escapeHtml(String(ind.naics_code ?? ind.activity_code ?? ""))}</td>
        <td style="font-size:0.82rem;">${escapeHtml(String(ind.industry ?? ind.activity_description ?? "Unknown"))}</td>
        <td style="font-size:0.82rem;text-align:right;">${formatCompactCurrency(ind.current_period ?? 0)}</td>
        <td style="font-size:0.82rem;text-align:right;">${formatCompactCurrency(ind.prior_period ?? 0)}</td>
        <td style="font-size:0.82rem;text-align:right;color:${changeColor};font-weight:600;">${changeAmt >= 0 ? "+" : ""}${formatCompactCurrency(changeAmt)}</td>
        <td style="font-size:0.82rem;text-align:right;color:${changeColor};font-weight:600;">${changePct >= 0 ? "+" : ""}${changePct.toFixed(1)}%</td>
        <td style="font-size:0.82rem;min-width:120px;">
          <div style="display:flex;align-items:center;gap:6px;">
            <div style="width:${barWidth}%;height:14px;background:${barColor};border-radius:3px;min-width:2px;"></div>
            <span style="font-size:0.75rem;color:#5c6578;white-space:nowrap;">${contribSign}${contribPct.toFixed(1)}%</span>
          </div>
        </td>
      </tr>
    `;
  }).join("");

  /* Build HTML */
  panelContent.innerHTML = `
    <p class="body-copy" style="margin:0 0 14px;font-weight:600;font-size:0.92rem;">${summaryLine}</p>
    <div id="decomp-chart-container" style="margin-bottom:18px;min-height:260px;"></div>
    ${industries.length > 0 ? `
      <div class="table-shell" style="max-height:360px;overflow-y:auto;">
        <table>
          <thead>
            <tr>
              <th>NAICS Code</th>
              <th>Industry</th>
              <th style="text-align:right;">This Period</th>
              <th style="text-align:right;">Prior Period</th>
              <th style="text-align:right;">Change $</th>
              <th style="text-align:right;">Change %</th>
              <th>Contribution</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
    ` : '<p class="body-copy" style="color:#5c6578;">No industry-level data available for this anomaly.</p>'}
  `;

  /* Render diverging bar chart */
  if (chartItems.length > 0) {
    const chartEl = panelContent.querySelector<HTMLElement>("#decomp-chart-container");
    if (chartEl) {
      const categories = chartItems.map(
        (i) => String(i.industry ?? i.activity_description ?? i.naics_code ?? "Unknown"),
      );
      const values = chartItems.map((i) => i.change_amount ?? 0);
      const colors = values.map((v) => (v >= 0 ? "#2e7d32" : "#c62828"));

      decompChart = Highcharts.chart(chartEl, {
        chart: {
          type: "bar",
          height: Math.max(220, chartItems.length * 36 + 60),
        },
        title: { text: "Top Industry Changes", style: { fontSize: "1rem" } },
        xAxis: {
          categories,
          labels: {
            style: { fontSize: "0.75rem" },
            formatter: function (this: any): string {
              const text = String(this.value);
              return text.length > 30 ? text.substring(0, 28) + "..." : text;
            },
          },
        },
        yAxis: {
          title: { text: "Change ($)" },
          labels: {
            formatter: function (this: any): string {
              return formatCompactCurrency(this.value as number);
            },
          },
          plotLines: [{
            value: 0,
            color: "rgba(26,31,43,0.3)",
            width: 1,
            zIndex: 3,
          }],
        },
        tooltip: {
          formatter: function (this: any): string {
            const val = this.y as number;
            const sign = val >= 0 ? "+" : "";
            return `<b>${this.x as string}</b><br/>Change: ${sign}${formatCurrency(val)}`;
          },
        },
        plotOptions: {
          bar: {
            colorByPoint: true,
            colors,
            borderRadius: 3,
          },
        },
        legend: { enabled: false },
        series: [{
          name: "Change",
          data: values,
          type: "bar",
        }],
      });
    }
  } else {
    const chartEl = panelContent.querySelector<HTMLElement>("#decomp-chart-container");
    if (chartEl) chartEl.style.display = "none";
  }
}

function renderDecompositionError(panelContent: HTMLElement, message: string): void {
  panelContent.innerHTML = `
    <p class="body-copy" style="color:var(--danger);padding:10px 0;">${escapeHtml(message)}</p>
  `;
}

/* ── Load decomposition data for an expanded card ── */

async function loadDecomposition(item: AnomalyItem): Promise<void> {
  const cid = cardId(item);
  const panel = document.querySelector<HTMLElement>(`#panel-${CSS.escape(cid)} .investigate-panel-content`);
  if (!panel) return;

  const comparison = comparisonForType(item.anomaly_type);

  try {
    const data = await getAnomalyDecomposition(
      item.copo,
      item.anomaly_date,
      item.tax_type,
      comparison,
    );
    /* Verify the panel is still visible (user may have collapsed it) */
    if (state.expandedCardId !== cid) return;
    renderDecompositionContent(panel, data);
  } catch (err) {
    if (state.expandedCardId !== cid) return;
    const msg = err instanceof Error ? err.message : "Failed to load decomposition data.";
    renderDecompositionError(panel, msg);
  }
}

/* ── Data loading and filtering ── */

async function loadAnomalies(): Promise<void> {
  const listContainer = document.querySelector<HTMLElement>("#anomalies-list");
  if (!listContainer) return;

  showLoading(listContainer);

  try {
    const data = await getAnomalies({
      startDate: state.startDate,
      endDate: state.endDate,
    });
    state.data = data;
    state.allItems = data.items;
    state.visibleCount = CARD_PAGE_SIZE;
    applyFiltersAndRender();
  } catch {
    listContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--danger)">Failed to load anomaly data.</p>';
  }
}

function resetVisibleCount(): void {
  state.visibleCount = CARD_PAGE_SIZE;
}

function applyFiltersAndRender(): void {
  const listContainer = document.querySelector<HTMLElement>("#anomalies-list");
  if (!listContainer) return;

  /* Destroy any open decomposition chart before re-rendering */
  destroyDecompChart();

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
    default: { // severity
      const sevOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
      filtered.sort((a, b) => (sevOrder[a.severity] ?? 4) - (sevOrder[b.severity] ?? 4));
      break;
    }
  }

  if (!filtered.length) {
    listContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No anomalies match these filters.</p>';
    return;
  }

  const showing = Math.min(filtered.length, state.visibleCount);
  const countLabel = `<p class="body-copy" style="margin-bottom:12px;color:#5c6578;">Showing ${showing} of ${filtered.length} filtered anomalies (${state.allItems.length} in the 24-month window)</p>`;
  const cards = filtered.slice(0, showing).map(renderAnomalyCard).join("");
  const loadMore = filtered.length > showing
    ? `<div style="display:flex;justify-content:center;padding:12px 0 4px;">
        <button id="anomaly-load-more" class="button button-ghost" style="min-height:38px;padding:0 18px;font-size:0.84rem;">Load 100 more</button>
      </div>`
    : "";
  listContainer.innerHTML = countLabel + cards + loadMore;

  /* Wire investigate buttons */
  wireInvestigateButtons(listContainer, filtered.slice(0, showing));

  listContainer.querySelector<HTMLButtonElement>("#anomaly-load-more")
    ?.addEventListener("click", () => {
      state.visibleCount += CARD_PAGE_SIZE;
      applyFiltersAndRender();
    });

  /* If a card is expanded, load its decomposition */
  if (state.expandedCardId) {
    const expandedItem = filtered.find((f) => cardId(f) === state.expandedCardId);
    if (expandedItem) {
      loadDecomposition(expandedItem);
    }
  }
}

/* ── Wire investigate button click handlers ── */

function wireInvestigateButtons(container: HTMLElement, visibleItems: AnomalyItem[]): void {
  container.querySelectorAll<HTMLButtonElement>(".investigate-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();

      const cid = btn.dataset.cardId ?? "";

      if (state.expandedCardId === cid) {
        /* Collapse */
        state.expandedCardId = null;
        destroyDecompChart();
        applyFiltersAndRender();
      } else {
        /* Expand this card, collapse any other */
        state.expandedCardId = cid;
        destroyDecompChart();
        applyFiltersAndRender();
      }
    });
  });
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
    setPageMetadata({
      title: "Oklahoma Revenue Anomalies",
      description:
        "Review statewide Oklahoma municipal revenue anomalies, unusual tax shifts, and industry-level decomposition for abnormal months.",
      path: ROUTES.anomalies,
    });
    container.className = "view-anomalies";

    /* Reset state */
    state.activeSeverity = "all";
    state.activeTaxType = "all";
    state.activeAnomalyType = "all";
    state.cityFilter = "";
    state.minDeviation = 0;
    state.minVariance = 1000;
    state.startDate = defaultRecentStartDate();
    state.endDate = defaultRecentEndDate();
    state.sortBy = "severity";
    state.data = null;
    state.allItems = [];
    state.expandedCardId = null;
    state.visibleCount = CARD_PAGE_SIZE;
    destroyDecompChart();

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
            {value: "missing_data", text: "Missing Data"}, {value: "naics_shift", text: "NAICS Shift"},
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
              value="${state.startDate}"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
          <label style="display:flex;align-items:center;gap:6px;font-size:0.82rem;color:var(--muted);">
            To:
            <input id="anomaly-end-date" type="date"
              value="${state.endDate}"
              style="padding:6px 8px;border:1px solid var(--line);border-radius:8px;font-size:0.85rem;" />
          </label>
        </div>
      </div>

      <div id="anomalies-list" style="padding:0 4px;"></div>
    `;

    /* Wire filter buttons */
    wireFilterGroup(container, "sev-btn", (v) => { state.activeSeverity = v; state.expandedCardId = null; destroyDecompChart(); resetVisibleCount(); applyFiltersAndRender(); });
    wireFilterGroup(container, "tax-btn", (v) => { state.activeTaxType = v; state.expandedCardId = null; destroyDecompChart(); resetVisibleCount(); applyFiltersAndRender(); });
    wireFilterGroup(container, "type-btn", (v) => { state.activeAnomalyType = v; state.expandedCardId = null; destroyDecompChart(); resetVisibleCount(); applyFiltersAndRender(); });
    wireFilterGroup(container, "sort-btn", (v) => { state.sortBy = v; resetVisibleCount(); applyFiltersAndRender(); });

    /* City search */
    const cityInput = container.querySelector<HTMLInputElement>("#anomaly-city-search");
    cityInput?.addEventListener("input", () => {
      state.cityFilter = cityInput.value;
      resetVisibleCount();
      applyFiltersAndRender();
    });

    /* Min deviation */
    const devInput = container.querySelector<HTMLInputElement>("#anomaly-min-dev");
    devInput?.addEventListener("input", () => {
      state.minDeviation = parseFloat(devInput.value) || 0;
      resetVisibleCount();
      applyFiltersAndRender();
    });

    /* Min variance */
    const varInput = container.querySelector<HTMLInputElement>("#anomaly-min-variance");
    varInput?.addEventListener("input", () => {
      state.minVariance = parseFloat(varInput.value) || 0;
      resetVisibleCount();
      applyFiltersAndRender();
    });

    /* Date range */
    const startInput = container.querySelector<HTMLInputElement>("#anomaly-start-date");
    startInput?.addEventListener("input", () => {
      state.startDate = startInput.value;
      resetVisibleCount();
      loadAnomalies();
    });
    const endInput = container.querySelector<HTMLInputElement>("#anomaly-end-date");
    endInput?.addEventListener("input", () => {
      state.endDate = endInput.value;
      resetVisibleCount();
      loadAnomalies();
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
    state.startDate = defaultRecentStartDate();
    state.endDate = defaultRecentEndDate();
    state.sortBy = "severity";
    state.data = null;
    state.allItems = [];
    state.expandedCardId = null;
    state.visibleCount = CARD_PAGE_SIZE;
    destroyDecompChart();
  },
};
