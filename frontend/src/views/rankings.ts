/* ══════════════════════════════════════════════
   Rankings view — placeholder for future release
   ══════════════════════════════════════════════ */

import type { View } from "../types";

export const rankingsView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-rankings";

    container.innerHTML = `
      <div class="panel" style="padding: 40px;">
        <div class="section-heading">
          <p class="eyebrow">Intelligence</p>
          <h2>City rankings</h2>
        </div>
        <div class="results-empty" style="margin-top: 20px; min-height: 200px;">
          <div>
            <p style="font-size:1.8rem; margin: 0;">&#9733;</p>
            <p>Rankings dashboard is coming in a future release.</p>
            <p class="body-copy">
              This view will rank jurisdictions by total revenue, year-over-year growth, and other metrics
              using the <code>/api/stats/rankings</code> endpoint.
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
