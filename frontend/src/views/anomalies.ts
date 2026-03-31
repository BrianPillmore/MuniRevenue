/* ══════════════════════════════════════════════
   Anomalies view -- Statewide anomaly feed
   ══════════════════════════════════════════════ */

import { getAnomalies } from "../api";
import type { AnomaliesResponse, AnomalyItem, View } from "../types";
import {
  escapeHtml,
  formatCurrency,
  formatPercent,
} from "../utils";

/* ── State ── */

interface AnomaliesState {
  activeSeverity: string;
  data: AnomaliesResponse | null;
}

const state: AnomaliesState = {
  activeSeverity: "all",
  data: null,
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
  const metricsLine = [expectedStr, actualStr]
    .filter(Boolean)
    .join(" | ");

  return `
    <article class="anomaly-card panel" style="padding:18px 24px;margin-bottom:10px;">
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px;">
        ${severityBadge(item.severity)}
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

/* ── Data loading and rendering ── */

async function loadAnomalies(): Promise<void> {
  const listContainer = document.querySelector<HTMLElement>("#anomalies-list");
  if (!listContainer) return;

  listContainer.innerHTML =
    '<p class="body-copy" style="padding:20px;text-align:center;">Loading anomalies...</p>';

  try {
    const severity = state.activeSeverity === "all" ? undefined : state.activeSeverity;
    const data = await getAnomalies(severity, undefined, undefined, 100);
    state.data = data;
    renderAnomalyList(data, listContainer);
  } catch {
    listContainer.innerHTML =
      '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load anomaly data.</p>';
  }
}

function renderAnomalyList(
  data: AnomaliesResponse,
  container: HTMLElement,
): void {
  if (!data.items.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:20px;text-align:center;">No anomalies found for this filter.</p>';
    return;
  }

  const countLabel = `<p class="body-copy" style="margin-bottom:12px;color:#5d6b75;">${data.count} anomalies found</p>`;
  const cards = data.items.map(renderAnomalyCard).join("");
  container.innerHTML = countLabel + cards;
}

/* ── Filter handlers ── */

function onSeverityFilter(severity: string): void {
  state.activeSeverity = severity;

  /* Update button styles */
  document.querySelectorAll<HTMLButtonElement>(".severity-filter-btn").forEach((btn) => {
    const isActive = btn.dataset.severity === severity;
    btn.classList.toggle("is-active", isActive);
    btn.setAttribute("aria-pressed", String(isActive));
  });

  loadAnomalies();
}

/* ── View implementation ── */

export const anomaliesView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-anomalies";

    /* Reset state */
    state.activeSeverity = "all";
    state.data = null;

    const severityLevels = ["all", "critical", "high", "medium", "low"];
    const filterButtons = severityLevels
      .map((s) => {
        const label = s.charAt(0).toUpperCase() + s.slice(1);
        const isActive = s === "all";
        return `
          <button
            class="severity-filter-btn btn btn-secondary${isActive ? " is-active" : ""}"
            data-severity="${s}"
            aria-pressed="${isActive}"
            style="font-size:0.82rem;padding:6px 14px;"
          >${label}</button>
        `;
      })
      .join("");

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Anomalies</h2>
        </div>
        <p class="body-copy" style="margin-bottom:16px;">
          Detected revenue anomalies across all Oklahoma municipalities. Filter by severity to focus on specific events.
        </p>
        <div class="severity-filters" role="group" aria-label="Severity filter" style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
          ${filterButtons}
        </div>
      </div>

      <div id="anomalies-list" style="padding:0 4px;"></div>
    `;

    /* Attach filter handlers */
    container.querySelectorAll<HTMLButtonElement>(".severity-filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sev = btn.dataset.severity ?? "all";
        onSeverityFilter(sev);
      });
    });

    /* Initial load */
    loadAnomalies();
  },

  destroy(): void {
    state.activeSeverity = "all";
    state.data = null;
  },
};
