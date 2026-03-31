/* ══════════════════════════════════════════════
   KPI / metric card component
   ══════════════════════════════════════════════ */

import { escapeHtml, trendArrow } from "../utils";

export interface KpiCardData {
  label: string;
  value: string;
  subtitle?: string;
  trend?: number | null;
}

/**
 * Render a grid of KPI metric cards into the given container.
 */
export function renderKpiCards(
  container: HTMLElement,
  cards: KpiCardData[],
): void {
  const html = cards
    .map((card) => {
      const trendHtml =
        card.trend !== undefined && card.trend !== null
          ? trendArrow(card.trend)
          : "";
      const subtitleHtml = card.subtitle
        ? `<span class="dash-metric-subtitle">${escapeHtml(card.subtitle)}</span>`
        : "";

      return `
        <article class="dash-metric-card">
          <p>${escapeHtml(card.label)}</p>
          <strong>${escapeHtml(card.value)}</strong>
          ${trendHtml}
          ${subtitleHtml}
        </article>
      `;
    })
    .join("");

  container.innerHTML = `<div class="dash-summary-grid">${html}</div>`;
}
