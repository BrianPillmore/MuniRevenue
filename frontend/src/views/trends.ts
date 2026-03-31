/* ══════════════════════════════════════════════
   Statewide Trends view — placeholder for future release
   ══════════════════════════════════════════════ */

import type { View } from "../types";

export const trendsView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-trends";

    container.innerHTML = `
      <div class="panel" style="padding: 40px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>Statewide trends</h2>
        </div>
        <div class="results-empty" style="margin-top: 20px; min-height: 200px;">
          <div>
            <p style="font-size:1.8rem; margin: 0;">&#8599;</p>
            <p>Statewide trend analysis is coming in a future release.</p>
            <p class="body-copy">
              This view will show aggregate revenue time series, sector breakdowns, and anomaly detection
              using the <code>/api/stats/statewide-trend</code> and <code>/api/stats/naics-sectors</code> endpoints.
            </p>
          </div>
        </div>
      </div>
    `;
  },

  destroy(): void {
    /* Nothing to clean up */
  },
};
