import "./styles.css";

import type { AnalysisResponse, ChangeRow, ForecastPoint, SeasonalRow } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Unable to find app root.");
}

app.innerHTML = `
  <div class="page-shell">
    <div class="ambient ambient-one"></div>
    <div class="ambient ambient-two"></div>

    <header class="hero">
      <div class="hero-copy">
        <p class="eyebrow">MuniRev</p>
        <h1>Municipal revenue analysis, rebuilt in TypeScript and Python.</h1>
        <p class="hero-text">
          Upload monthly sales tax receipts, review trend and seasonality signals, and export a shareable report.
        </p>
        <div class="hero-actions">
          <a class="button button-ghost" href="${API_BASE}/api/sample-data">Sample data</a>
          <a class="button button-ghost" href="${API_BASE}/api/sample-report">Legacy sample report</a>
        </div>
      </div>
      <aside class="hero-panel">
        <p class="panel-label">Migration Status</p>
        <ul class="panel-list">
          <li>TypeScript client for uploads and report actions</li>
          <li>Python API for analysis and report generation</li>
          <li>Legacy R implementation preserved for reference</li>
        </ul>
      </aside>
    </header>

    <nav class="tabbar" aria-label="Sections">
      <button class="tab is-active" data-tab="analysis">Analysis</button>
      <button class="tab" data-tab="about">About</button>
    </nav>

    <main>
      <section class="tab-panel is-active" data-panel="analysis">
        <div class="analysis-grid">
          <section class="panel upload-panel">
            <div class="section-heading">
              <p class="eyebrow">Upload</p>
              <h2>Analyze a municipal tax workbook</h2>
            </div>
            <p class="body-copy">
              MuniRev expects one date column and one revenue column in an Excel .xlsx file. The backend will detect the
              likely columns automatically.
            </p>

            <form id="analyze-form" class="upload-form">
              <label class="file-picker" for="tax-file">
                <span class="file-picker-title">Choose workbook</span>
                <span class="file-picker-subtitle" id="file-name">No file selected yet</span>
              </label>
              <input id="tax-file" name="tax-file" type="file" accept=".xlsx" />

              <div class="action-row">
                <button class="button button-solid" id="analyze-button" type="submit">Run analysis</button>
                <button class="button button-secondary" id="report-button" type="button" disabled>Download report</button>
              </div>
            </form>

            <div id="status" class="status">Choose a workbook to begin.</div>
          </section>

          <section class="panel results-panel">
            <div class="section-heading">
              <p class="eyebrow">Results</p>
              <h2>Analysis view</h2>
            </div>
            <div id="results" class="results-empty">
              <p>Your summary cards, monthly changes, seasonality table, and forecast will appear here.</p>
            </div>
          </section>
        </div>
      </section>

      <section class="tab-panel" data-panel="about">
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
              The new version separates the user experience from the analytical engine so the application can evolve more
              easily inside its own GitHub repository.
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
      </section>
    </main>
  </div>
`;

const fileInput = document.querySelector<HTMLInputElement>("#tax-file");
const fileName = document.querySelector<HTMLSpanElement>("#file-name");
const status = document.querySelector<HTMLDivElement>("#status");
const form = document.querySelector<HTMLFormElement>("#analyze-form");
const analyzeButton = document.querySelector<HTMLButtonElement>("#analyze-button");
const reportButton = document.querySelector<HTMLButtonElement>("#report-button");
const results = document.querySelector<HTMLDivElement>("#results");
const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>(".tab"));
const panels = Array.from(document.querySelectorAll<HTMLElement>(".tab-panel"));

let selectedFile: File | null = null;
let latestAnalysis: AnalysisResponse | null = null;

fileInput?.addEventListener("change", () => {
  selectedFile = fileInput.files?.[0] ?? null;
  fileName!.textContent = selectedFile ? selectedFile.name : "No file selected yet";
  reportButton!.disabled = !selectedFile;
  setStatus(selectedFile ? `Ready to analyze ${selectedFile.name}.` : "Choose a workbook to begin.");
});

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedFile) {
    setStatus("Please choose an .xlsx workbook first.", true);
    return;
  }

  try {
    toggleBusy(true, "Analyzing workbook...");
    latestAnalysis = await analyzeWorkbook(selectedFile);
    renderAnalysis(latestAnalysis);
    setStatus(`Analysis complete for ${selectedFile.name}.`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "The workbook could not be analyzed.";
    setStatus(message, true);
  } finally {
    toggleBusy(false);
  }
});

reportButton?.addEventListener("click", async () => {
  if (!selectedFile) {
    setStatus("Choose a workbook before generating a report.", true);
    return;
  }

  try {
    toggleBusy(true, "Generating HTML report...");
    const response = await uploadWorkbook("/api/report", selectedFile);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "MuniRev-Analysis-Report.html";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Report downloaded.");
  } catch (error) {
    const message = error instanceof Error ? error.message : "The report could not be generated.";
    setStatus(message, true);
  } finally {
    toggleBusy(false);
  }
});

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === target));
  });
});

async function analyzeWorkbook(file: File): Promise<AnalysisResponse> {
  const response = await uploadWorkbook("/api/analyze", file);
  return (await response.json()) as AnalysisResponse;
}

async function uploadWorkbook(path: string, file: File): Promise<Response> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const payload = (await safeJson(response)) as { detail?: string } | null;
    throw new Error(payload?.detail ?? `Request failed with status ${response.status}.`);
  }

  return response;
}

async function safeJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function toggleBusy(isBusy: boolean, message?: string): void {
  analyzeButton!.disabled = isBusy;
  reportButton!.disabled = isBusy || !selectedFile;
  if (message) {
    setStatus(message);
  }
}

function setStatus(message: string, isError = false): void {
  if (!status) {
    return;
  }
  status.textContent = message;
  status.classList.toggle("is-error", isError);
}

function renderAnalysis(analysis: AnalysisResponse): void {
  if (!results) {
    return;
  }

  const summary = analysis.summary;
  results.className = "results-ready";
  results.innerHTML = `
    <section class="summary-grid">
      ${buildMetricCard("Records", `${summary.records}`)}
      ${buildMetricCard("Coverage", `${summary.first_date} to ${summary.last_date}`)}
      ${buildMetricCard("Average returned", formatCurrency(summary.average_returned))}
      ${buildMetricCard("Latest returned", formatCurrency(summary.latest_returned))}
      ${buildMetricCard("Latest MoM", formatPercent(summary.latest_mom_pct))}
      ${buildMetricCard("Latest YoY", formatPercent(summary.latest_yoy_pct))}
    </section>

    <section class="result-block">
      <div class="block-header">
        <h3>Highlights</h3>
        <p>Key signals pulled from the uploaded workbook.</p>
      </div>
      <ul class="highlight-list">
        ${analysis.highlights.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
    </section>

    <section class="result-block">
      <div class="block-header">
        <h3>12-month forecast</h3>
        <p>Seasonally adjusted projection based on the shifted business month model.</p>
      </div>
      ${buildForecastChart(analysis.forecast)}
      ${buildForecastTable(analysis.forecast)}
    </section>

    <section class="result-block split-block">
      <div>
        <div class="block-header">
          <h3>Seasonality</h3>
          <p>Month-level summary statistics.</p>
        </div>
        ${buildSeasonalityTable(analysis.seasonality)}
      </div>
      <div>
        <div class="block-header">
          <h3>ANOVA</h3>
          <p>${escapeHtml(analysis.anova.interpretation)}</p>
        </div>
        <div class="anova-card">
          <div><span>F-statistic</span><strong>${formatPlain(analysis.anova.f_statistic)}</strong></div>
          <div><span>P-value</span><strong>${formatPlain(analysis.anova.p_value)}</strong></div>
          <div><span>Significant</span><strong>${formatBoolean(analysis.anova.significant)}</strong></div>
        </div>
        ${analysis.anova.note ? `<p class="helper-note">${escapeHtml(analysis.anova.note)}</p>` : ""}
      </div>
    </section>

    <section class="result-block">
      <div class="block-header">
        <h3>Monthly changes</h3>
        <p>Recent voucher periods with month-over-month and year-over-year deltas.</p>
      </div>
      ${buildChangeTable(analysis.monthly_changes)}
    </section>
  `;
}

function buildMetricCard(label: string, value: string): string {
  return `
    <article class="metric-card">
      <p>${escapeHtml(label)}</p>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

function buildForecastChart(points: ForecastPoint[]): string {
  if (!points.length) {
    return '<p class="helper-note">Not enough data was available to render a forecast.</p>';
  }

  const width = 900;
  const height = 300;
  const padding = 26;
  const values = points.flatMap((point) => [point.projected_returned, point.lower_bound, point.upper_bound]);
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const span = Math.max(maxValue - minValue, 1);

  const x = (index: number) => padding + index * ((width - padding * 2) / Math.max(points.length - 1, 1));
  const y = (value: number) => height - padding - ((value - minValue) / span) * (height - padding * 2);

  const projection = points.map((point, index) => `${x(index).toFixed(1)},${y(point.projected_returned).toFixed(1)}`).join(" ");
  const bandUpper = points.map((point, index) => `${x(index).toFixed(1)},${y(point.upper_bound).toFixed(1)}`);
  const bandLower = [...points]
    .reverse()
    .map((point, reverseIndex) => {
      const index = points.length - reverseIndex - 1;
      return `${x(index).toFixed(1)},${y(point.lower_bound).toFixed(1)}`;
    });
  const labels = points
    .map(
      (point, index) =>
        `<text x="${x(index).toFixed(1)}" y="${height - 6}" text-anchor="middle">${escapeHtml(point.date.slice(5, 7))}/${escapeHtml(point.date.slice(2, 4))}</text>`,
    )
    .join("");

  return `
    <div class="forecast-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Forecast projection">
        <rect width="${width}" height="${height}" rx="22" fill="#fffdf7"></rect>
        <polygon points="${[...bandUpper, ...bandLower].join(" ")}" fill="rgba(166, 61, 64, 0.18)"></polygon>
        <polyline points="${projection}" fill="none" stroke="#1d6b70" stroke-width="4" stroke-linecap="round"></polyline>
        ${labels}
      </svg>
    </div>
  `;
}

function buildForecastTable(points: ForecastPoint[]): string {
  if (!points.length) {
    return "";
  }

  const rows = points
    .map(
      (point) => `
        <tr>
          <td>${escapeHtml(point.date)}</td>
          <td>${escapeHtml(point.basis_month)}</td>
          <td>${formatCurrency(point.projected_returned)}</td>
          <td>${formatCurrency(point.lower_bound)}</td>
          <td>${formatCurrency(point.upper_bound)}</td>
        </tr>
      `,
    )
    .join("");

  return wrapTable(["Date", "Basis Month", "Projection", "Lower Bound", "Upper Bound"], rows);
}

function buildSeasonalityTable(rows: SeasonalRow[]): string {
  const body = rows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.month)}</td>
          <td>${row.observations}</td>
          <td>${formatCurrency(row.mean_returned)}</td>
          <td>${formatCurrency(row.median_returned)}</td>
          <td>${formatCurrency(row.min_returned)}</td>
          <td>${formatCurrency(row.max_returned)}</td>
        </tr>
      `,
    )
    .join("");

  return wrapTable(["Month", "Obs.", "Mean", "Median", "Min", "Max"], body);
}

function buildChangeTable(rows: ChangeRow[]): string {
  const recentRows = rows.slice(-18);
  const body = recentRows
    .map(
      (row) => `
        <tr>
          <td>${escapeHtml(row.voucher_date)}</td>
          <td>${formatCurrency(row.returned)}</td>
          <td>${formatPercent(row.mom_pct)}</td>
          <td>${formatPercent(row.yoy_pct)}</td>
        </tr>
      `,
    )
    .join("");

  return wrapTable(["Voucher Date", "Returned", "MoM", "YoY"], body);
}

function wrapTable(headers: string[], body: string): string {
  return `
    <div class="table-shell">
      <table>
        <thead>
          <tr>${headers.map((header) => `<th>${escapeHtml(header)}</th>`).join("")}</tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function formatCurrency(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function formatPercent(value: number | null): string {
  return value === null ? "N/A" : `${value.toFixed(2)}%`;
}

function formatPlain(value: number | null): string {
  return value === null ? "N/A" : value.toFixed(4);
}

function formatBoolean(value: boolean | null): string {
  if (value === null) {
    return "Unknown";
  }
  return value ? "Yes" : "No";
}

function escapeHtml(value: string): string {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
