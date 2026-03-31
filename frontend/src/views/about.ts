/* ══════════════════════════════════════════════
   About view
   ══════════════════════════════════════════════ */

import type { View } from "../types";

export const aboutView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-about";

    container.innerHTML = `
      <div style="max-width:900px;">

        <!-- Hero section -->
        <div class="panel" style="padding:40px 36px;margin-bottom:24px;">
          <p class="eyebrow">About MuniRevenue</p>
          <h2 style="font-size:2rem;margin-top:8px;line-height:1.3;">Revenue intelligence for every Oklahoma city and county</h2>
          <p class="body-copy" style="font-size:1.05rem;margin-top:16px;max-width:700px;">
            MuniRevenue gives municipal leaders the tools to understand, forecast, and act on their tax revenue data.
            Explore trends across sales, use, and lodging tax. Identify anomalies before they become budget crises.
            Compare performance against peer cities. All powered by public data from the Oklahoma Tax Commission.
          </p>
        </div>

        <!-- Origin story + profile -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:24px;">
          <article class="panel" style="padding:32px 30px;">
            <p class="eyebrow">Origin</p>
            <h2 style="margin-top:8px;">Built by a mayor, for municipalities</h2>
            <p class="body-copy" style="margin-top:14px;">
              MuniRevenue started as an internal tool built by <strong>Mayor Brian Pillmore</strong> for the
              <strong>City of Yukon, Oklahoma</strong>. For over two years, it has been used to track Yukon's
              sales tax trends, identify seasonal patterns, and support budget planning.
            </p>
            <p class="body-copy" style="margin-top:12px;">
              Now, just in time for budget season, MuniRevenue has been expanded to cover
              <strong>all 600+ cities and 77 counties</strong> across Oklahoma — with over 9 million
              industry-level data points spanning five years of history.
            </p>
          </article>

          <article class="panel" style="padding:32px 30px;display:flex;flex-direction:column;align-items:center;text-align:center;">
            <img src="/assets/brian-pillmore.png" alt="Mayor Brian Pillmore"
              style="width:200px;height:200px;border-radius:50%;object-fit:cover;border:4px solid var(--line);margin-bottom:20px;box-shadow:0 4px 16px rgba(26,31,43,0.1);" />
            <p class="eyebrow">Mayor</p>
            <h3 style="margin:4px 0 8px;font-family:Merriweather,Georgia,serif;font-size:1.2rem;">Brian Pillmore</h3>
            <p class="body-copy" style="font-size:0.9rem;">City of Yukon, Oklahoma</p>
            <a class="button button-ghost" href="https://pillmoreforyukon.com/" target="_blank" rel="noreferrer"
              style="margin-top:16px;">pillmoreforyukon.com</a>
          </article>
        </div>

        <!-- What's inside -->
        <div class="panel" style="padding:32px 30px;margin-bottom:24px;">
          <p class="eyebrow">Platform</p>
          <h2 style="margin-top:8px;">What MuniRevenue provides</h2>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px;">
            <div>
              <h4 style="color:var(--brand);margin:0 0 6px;">Revenue Analysis</h4>
              <p class="body-copy" style="font-size:0.9rem;">Monthly revenue trends with smoothing, seasonal adjustment, and trendline overlays for sales, use, and lodging tax.</p>
            </div>
            <div>
              <h4 style="color:var(--brand);margin:0 0 6px;">Industry Breakdown</h4>
              <p class="body-copy" style="font-size:0.9rem;">NAICS industry data showing which businesses drive your city's economy — with drill-down to individual industry trends.</p>
            </div>
            <div>
              <h4 style="color:var(--brand);margin:0 0 6px;">Anomaly Detection</h4>
              <p class="body-copy" style="font-size:0.9rem;">Automatic flagging of unusual revenue changes with industry-level decomposition showing exactly what drove each anomaly.</p>
            </div>
            <div>
              <h4 style="color:var(--brand);margin:0 0 6px;">Forecasting</h4>
              <p class="body-copy" style="font-size:0.9rem;">12-month revenue projections with confidence intervals, built from seasonal patterns and historical trends.</p>
            </div>
            <div>
              <h4 style="color:var(--brand);margin:0 0 6px;">Peer Comparison</h4>
              <p class="body-copy" style="font-size:0.9rem;">Compare your city's performance against similar-sized municipalities or overlay multiple cities on the same chart.</p>
            </div>
            <div>
              <h4 style="color:var(--brand);margin:0 0 6px;">Data Export</h4>
              <p class="body-copy" style="font-size:0.9rem;">Download revenue data, forecasts, and charts in CSV, PNG, and SVG formats for council presentations and audits.</p>
            </div>
          </div>
        </div>

        <!-- Data source -->
        <div class="panel" style="padding:32px 30px;margin-bottom:24px;">
          <p class="eyebrow">Data</p>
          <h2 style="margin-top:8px;">Powered by public records</h2>
          <p class="body-copy" style="margin-top:14px;">
            All data comes from the <strong>Oklahoma Tax Commission's</strong> publicly available reporting system.
            MuniRevenue aggregates and analyzes this data to make it accessible and actionable for municipal leaders.
          </p>
          <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-top:20px;">
            <div class="dash-metric-card"><p>Jurisdictions</p><strong>644</strong></div>
            <div class="dash-metric-card"><p>Ledger Records</p><strong>78,756</strong></div>
            <div class="dash-metric-card"><p>Industry Records</p><strong>9,057,555</strong></div>
            <div class="dash-metric-card"><p>History</p><strong>2020–2026</strong></div>
          </div>
        </div>

        <!-- Disclaimer -->
        <div class="panel" style="padding:32px 30px;border-left:3px solid var(--gold);">
          <p class="eyebrow">Disclaimer</p>
          <h2 style="margin-top:8px;">A decision aid, not a substitute for finance review</h2>
          <p class="body-copy" style="margin-top:14px;">
            MuniRevenue is provided as a resource to support municipal revenue analysis. Users should pair its
            forecasts and summaries with local knowledge, finance review, and professional judgment before making
            major fiscal decisions. This tool does not constitute financial advice.
          </p>
        </div>

        <!-- Footer -->
        <div style="text-align:center;padding:24px 0;margin-top:8px;">
          <p class="body-copy" style="font-size:0.85rem;">
            <a href="https://munirevenue.com" class="city-link">munirevenue.com</a> &nbsp;·&nbsp;
            <a href="https://github.com/BrianPillmore/MuniRevenue" class="city-link" target="_blank">GitHub</a> &nbsp;·&nbsp;
            MIT License &nbsp;·&nbsp; &copy; 2026 Brian Pillmore
          </p>
        </div>

      </div>
    `;
  },

  destroy(): void {
    /* No charts or listeners to clean up */
  },
};
