/* ══════════════════════════════════════════════
   About view
   ══════════════════════════════════════════════ */

import type { View } from "../types";

export const aboutView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-about";

    container.innerHTML = `
      <div class="about-grid">
        <article class="panel about-card about-story">
          <div class="section-heading">
            <p class="eyebrow">About</p>
            <h2>Why this project exists</h2>
          </div>
          <p class="body-copy">
            The original CityTax tool helped municipalities in Oklahoma review monthly sales tax receipts and compare
            historical patterns. MuniRev keeps that mission while moving the product into a more portable web stack.
          </p>
          <p class="body-copy">
            The new version separates the user experience from the analytical engine, providing a fast, interactive
            dashboard for exploring revenue data, identifying trends, and forecasting future collections. All data
            comes from the Oklahoma Tax Commission's public records.
          </p>
        </article>

        <article class="panel about-card about-profile">
          <img src="/assets/brian-pillmore.png" alt="Brian Pillmore" class="profile-image" />
          <div>
            <p class="eyebrow">Background</p>
            <h2>Municipal context</h2>
            <p class="body-copy">
              The first version was developed under the leadership of Mayor Brian Pillmore for the City of Yukon. This
              interface keeps that origin visible while modernizing the implementation.
            </p>
            <a class="button button-ghost" href="https://pillmoreforyukon.com/" target="_blank" rel="noreferrer">Learn more</a>
          </div>
        </article>

        <article class="panel about-card about-stack">
          <div class="section-heading">
            <p class="eyebrow">Technology</p>
            <h2>How it is built</h2>
          </div>
          <p class="body-copy">
            MuniRev uses a Python FastAPI backend with direct PostgreSQL queries for full control over analytics.
            The frontend is vanilla TypeScript with Highcharts for interactive visualizations, bundled by Vite.
          </p>
          <ul class="body-copy" style="padding-left: 20px; line-height: 1.9;">
            <li>FastAPI with psycopg2 for zero-ORM database access</li>
            <li>PostgreSQL with window functions for time-series analytics</li>
            <li>TypeScript frontend with hash-based routing</li>
            <li>Highcharts for charts, treemaps, and heatmaps</li>
            <li>Vite for development and production builds</li>
          </ul>
        </article>

        <article class="panel about-card about-disclaimer">
          <div class="section-heading">
            <p class="eyebrow">Disclaimer</p>
            <h2>Use this as a decision aid, not a substitute for finance review</h2>
          </div>
          <p class="body-copy">
            This tool is provided as a resource to support municipal revenue analysis. Users should pair its forecasts and
            summaries with local knowledge, finance review, and professional judgment before making major fiscal decisions.
          </p>
        </article>
      </div>
    `;
  },

  destroy(): void {
    /* No charts or listeners to clean up */
  },
};
