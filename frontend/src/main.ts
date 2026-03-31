import "./styles.css";

import type {
  AnalysisResponse,
  ChangeRow,
  CityDetailResponse,
  CityLedgerResponse,
  CityListItem,
  CitySearchResponse,
  ForecastPoint,
  OverviewResponse,
  SeasonalRow,
  TaxTypeSummary,
} from "./types";

/* ── Highcharts global from CDN ── */
declare const Highcharts: any;

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Unable to find app root.");
}

/* ──────────────────────────────────────────────
   Highcharts theme — applied once at startup
   ────────────────────────────────────────────── */
function applyHighchartsTheme(): void {
  if (typeof Highcharts === "undefined") return;

  Highcharts.setOptions({
    colors: ["#1d6b70", "#a63d40", "#d4a843", "#2f6f74", "#c17f59"],
    chart: {
      backgroundColor: "transparent",
      style: { fontFamily: '"Trebuchet MS", "Lucida Sans Unicode", "Gill Sans", sans-serif' },
    },
    title: {
      style: {
        fontFamily: 'Georgia, "Times New Roman", serif',
        fontSize: "1.3rem",
        fontWeight: "bold",
        color: "#102231",
      },
    },
    subtitle: {
      style: { color: "#5d6b75", fontSize: "0.88rem" },
    },
    xAxis: {
      labels: { style: { color: "#5d6b75", fontSize: "0.78rem" } },
      lineColor: "rgba(16,34,49,0.12)",
      tickColor: "rgba(16,34,49,0.12)",
    },
    yAxis: {
      labels: { style: { color: "#5d6b75", fontSize: "0.78rem" } },
      gridLineColor: "rgba(16,34,49,0.08)",
      title: { style: { color: "#5d6b75" } },
    },
    legend: {
      itemStyle: { color: "#102231", fontWeight: "normal" },
    },
    tooltip: {
      backgroundColor: "rgba(255,252,246,0.96)",
      borderColor: "rgba(16,34,49,0.12)",
      style: { color: "#102231" },
    },
    credits: { enabled: false },
  });
}

applyHighchartsTheme();

/* ──────────────────────────────────────────────
   Render page shell
   ────────────────────────────────────────────── */

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
      <button class="tab" data-tab="dashboard">Dashboard</button>
      <button class="tab is-active" data-tab="analysis">Analysis</button>
      <button class="tab" data-tab="about">About</button>
    </nav>

    <main>
      <!-- ── Dashboard tab ── -->
      <section class="tab-panel" data-panel="dashboard">
        <div class="dashboard-layout">
          <div class="dashboard-sidebar panel">
            <div class="section-heading">
              <p class="eyebrow">Explore</p>
              <h2>City picker</h2>
            </div>
            <div class="city-picker">
              <input
                id="city-search"
                class="city-search-input"
                type="text"
                placeholder="Search cities or counties..."
                autocomplete="off"
                aria-label="Search cities"
              />
              <ul id="city-dropdown" class="city-dropdown" role="listbox" aria-label="City search results"></ul>
            </div>
            <div id="city-summary" class="city-summary"></div>
            <div id="tax-type-toggle" class="tax-type-toggle"></div>
          </div>

          <div class="dashboard-main">
            <div id="dashboard-overview" class="dashboard-overview">
              <div class="panel dashboard-overview-header">
                <div class="section-heading">
                  <p class="eyebrow">Oklahoma overview</p>
                  <h2>Top cities by sales tax revenue</h2>
                </div>
                <div id="overview-stats" class="overview-stats"></div>
              </div>
              <div class="panel chart-container">
                <div id="top-cities-chart" class="chart-box"></div>
              </div>
            </div>

            <div id="dashboard-detail" class="dashboard-detail" style="display:none;">
              <div class="panel chart-container">
                <div id="revenue-chart" class="chart-box"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ── Analysis tab ── -->
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

      <!-- ── About tab ── -->
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

/* ──────────────────────────────────────────────
   Existing upload / analysis DOM references
   ────────────────────────────────────────────── */

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

/* ──────────────────────────────────────────────
   Existing upload / analysis event handlers
   ────────────────────────────────────────────── */

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

/* ──────────────────────────────────────────────
   Tab navigation (updated to include dashboard)
   ────────────────────────────────────────────── */

let dashboardInitialized = false;

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.panel === target));

    if (target === "dashboard" && !dashboardInitialized) {
      dashboardInitialized = true;
      initDashboard();
    }
  });
});

/* ──────────────────────────────────────────────
   Existing helper functions
   ────────────────────────────────────────────── */

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

function formatCompactCurrency(value: number): string {
  if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(1)}B`;
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return formatCurrency(value);
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}

/* ══════════════════════════════════════════════
   DASHBOARD MODULE
   ══════════════════════════════════════════════ */

const dashboardState = {
  selectedCity: null as CityListItem | null,
  selectedCopo: null as number | null,
  activeTaxType: "sales" as string,
  cityDetail: null as CityDetailResponse | null,
  searchTimeout: null as ReturnType<typeof setTimeout> | null,
  revenueChartInstance: null as any,
  topCitiesChartInstance: null as any,
};

/* ── Dashboard API helpers ── */

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

async function searchCities(query: string): Promise<CityListItem[]> {
  const params = new URLSearchParams({ search: query, type: "city", limit: "50" });
  const data = await fetchJson<CitySearchResponse>(`${API_BASE}/api/cities?${params}`);
  return data.items;
}

async function fetchCityDetail(copo: number): Promise<CityDetailResponse> {
  return fetchJson<CityDetailResponse>(`${API_BASE}/api/cities/${copo}`);
}

async function fetchCityLedger(copo: number, taxType: string): Promise<CityLedgerResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  return fetchJson<CityLedgerResponse>(`${API_BASE}/api/cities/${copo}/ledger?${params}`);
}

async function fetchOverview(): Promise<OverviewResponse> {
  return fetchJson<OverviewResponse>(`${API_BASE}/api/stats/overview`);
}

/* ── Dashboard initialization ── */

async function initDashboard(): Promise<void> {
  setupCitySearch();
  await loadOverview();
}

/* ── City search / picker ── */

function setupCitySearch(): void {
  const searchInput = document.querySelector<HTMLInputElement>("#city-search");
  const dropdown = document.querySelector<HTMLUListElement>("#city-dropdown");

  if (!searchInput || !dropdown) return;

  searchInput.addEventListener("input", () => {
    const query = searchInput.value.trim();

    if (dashboardState.searchTimeout) {
      clearTimeout(dashboardState.searchTimeout);
    }

    if (query.length < 2) {
      dropdown.innerHTML = "";
      dropdown.classList.remove("is-open");
      return;
    }

    dashboardState.searchTimeout = setTimeout(async () => {
      try {
        const cities = await searchCities(query);
        renderCityDropdown(cities, dropdown);
      } catch {
        dropdown.innerHTML = '<li class="city-dropdown-empty">Search failed. Try again.</li>';
        dropdown.classList.add("is-open");
      }
    }, 250);
  });

  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      dropdown.innerHTML = "";
      dropdown.classList.remove("is-open");
    }

    if (event.key === "ArrowDown" && dropdown.classList.contains("is-open")) {
      event.preventDefault();
      const firstOption = dropdown.querySelector<HTMLLIElement>("[role='option']");
      firstOption?.focus();
    }
  });

  /* Close dropdown on outside click */
  document.addEventListener("click", (event) => {
    const target = event.target as HTMLElement;
    if (!target.closest(".city-picker")) {
      dropdown.innerHTML = "";
      dropdown.classList.remove("is-open");
    }
  });
}

function renderCityDropdown(cities: CityListItem[], dropdown: HTMLUListElement): void {
  if (!cities.length) {
    dropdown.innerHTML = '<li class="city-dropdown-empty">No cities found.</li>';
    dropdown.classList.add("is-open");
    return;
  }

  dropdown.innerHTML = cities
    .map(
      (city) => `
        <li class="city-dropdown-item" role="option" tabindex="0"
            data-copo="${city.copo}" data-name="${escapeHtml(city.name)}">
          <span class="city-dropdown-name">${escapeHtml(city.name)}</span>
          <span class="city-dropdown-meta">${escapeHtml(city.county_name)} County${city.has_ledger_data ? "" : " (no data)"}</span>
        </li>
      `,
    )
    .join("");

  dropdown.classList.add("is-open");

  /* Attach click and keyboard handlers to each option */
  dropdown.querySelectorAll<HTMLLIElement>(".city-dropdown-item").forEach((item) => {
    const handler = () => {
      const copo = Number(item.dataset.copo);
      const name = item.dataset.name ?? "";
      const city = cities.find((c) => c.copo === copo) ?? null;

      const searchInput = document.querySelector<HTMLInputElement>("#city-search");
      if (searchInput) searchInput.value = name;

      dropdown.innerHTML = "";
      dropdown.classList.remove("is-open");

      if (city) selectCity(city);
    };

    item.addEventListener("click", handler);
    item.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handler();
      }
      if (event.key === "ArrowDown") {
        event.preventDefault();
        (item.nextElementSibling as HTMLElement)?.focus();
      }
      if (event.key === "ArrowUp") {
        event.preventDefault();
        const prev = item.previousElementSibling as HTMLElement;
        if (prev) {
          prev.focus();
        } else {
          document.querySelector<HTMLInputElement>("#city-search")?.focus();
        }
      }
    });
  });
}

/* ── City selection ── */

async function selectCity(city: CityListItem): Promise<void> {
  dashboardState.selectedCity = city;
  dashboardState.selectedCopo = city.copo;
  dashboardState.activeTaxType = "sales";

  const summaryEl = document.querySelector<HTMLDivElement>("#city-summary");
  const toggleEl = document.querySelector<HTMLDivElement>("#tax-type-toggle");
  const overviewEl = document.querySelector<HTMLDivElement>("#dashboard-overview");
  const detailEl = document.querySelector<HTMLDivElement>("#dashboard-detail");

  if (summaryEl) summaryEl.innerHTML = '<p class="body-copy">Loading city data...</p>';

  try {
    const detail = await fetchCityDetail(city.copo);
    dashboardState.cityDetail = detail;

    renderCitySummary(detail, summaryEl);
    renderTaxTypeToggle(detail.tax_type_summaries, toggleEl);

    /* Switch from overview to detail view */
    if (overviewEl) overviewEl.style.display = "none";
    if (detailEl) detailEl.style.display = "block";

    await loadLedgerChart(city.copo, dashboardState.activeTaxType);
  } catch {
    if (summaryEl) summaryEl.innerHTML = '<p class="body-copy" style="color:var(--brand)">Failed to load city data.</p>';
  }
}

function renderCitySummary(detail: CityDetailResponse, container: HTMLDivElement | null): void {
  if (!container) return;

  const salesSummary = detail.tax_type_summaries.find((t) => t.tax_type === "sales");
  const useSummary = detail.tax_type_summaries.find((t) => t.tax_type === "use");
  const lodgingSummary = detail.tax_type_summaries.find((t) => t.tax_type === "lodging");

  const cards: string[] = [];

  if (salesSummary) {
    cards.push(buildDashMetricCard("Sales tax total", formatCompactCurrency(salesSummary.total_returned)));
  }
  if (useSummary) {
    cards.push(buildDashMetricCard("Use tax total", formatCompactCurrency(useSummary.total_returned)));
  }
  if (lodgingSummary) {
    cards.push(buildDashMetricCard("Lodging tax total", formatCompactCurrency(lodgingSummary.total_returned)));
  }

  const totalRecords = detail.tax_type_summaries.reduce((sum, t) => sum + t.record_count, 0);
  cards.push(buildDashMetricCard("Records", formatNumber(totalRecords)));

  const dates = detail.tax_type_summaries.flatMap((t) => [t.earliest_date, t.latest_date]).filter(Boolean).sort();
  if (dates.length) {
    cards.push(buildDashMetricCard("Date range", `${dates[0]} to ${dates[dates.length - 1]}`));
  }

  container.innerHTML = `
    <div class="section-heading" style="margin-top:18px;">
      <p class="eyebrow">${escapeHtml(detail.jurisdiction_type)} / ${escapeHtml(detail.county_name)} County</p>
      <h2 style="font-size:1.3rem;">${escapeHtml(detail.name)}</h2>
    </div>
    <div class="dash-summary-grid">${cards.join("")}</div>
  `;
}

function buildDashMetricCard(label: string, value: string): string {
  return `
    <article class="dash-metric-card">
      <p>${escapeHtml(label)}</p>
      <strong>${escapeHtml(value)}</strong>
    </article>
  `;
}

/* ── Tax type toggle ── */

function renderTaxTypeToggle(summaries: TaxTypeSummary[], container: HTMLDivElement | null): void {
  if (!container) return;

  const availableTypes = summaries.map((s) => s.tax_type);

  if (availableTypes.length <= 1) {
    container.innerHTML = "";
    return;
  }

  const buttons = availableTypes
    .map((type) => {
      const isActive = type === dashboardState.activeTaxType;
      return `<button class="tax-toggle-btn${isActive ? " is-active" : ""}" data-tax-type="${escapeHtml(type)}">${escapeHtml(type.charAt(0).toUpperCase() + type.slice(1))}</button>`;
    })
    .join("");

  container.innerHTML = `
    <div class="tax-toggle-row">${buttons}</div>
  `;

  container.querySelectorAll<HTMLButtonElement>(".tax-toggle-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const taxType = btn.dataset.taxType;
      if (!taxType || taxType === dashboardState.activeTaxType) return;

      dashboardState.activeTaxType = taxType;
      container.querySelectorAll(".tax-toggle-btn").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");

      if (dashboardState.selectedCopo) {
        await loadLedgerChart(dashboardState.selectedCopo, taxType);
      }
    });
  });
}

/* ── Overview (top cities bar chart) ── */

async function loadOverview(): Promise<void> {
  const statsEl = document.querySelector<HTMLDivElement>("#overview-stats");
  const chartEl = document.querySelector<HTMLDivElement>("#top-cities-chart");

  try {
    const overview = await fetchOverview();
    renderOverviewStats(overview, statsEl);
    renderTopCitiesChart(overview, chartEl);
  } catch {
    if (statsEl) statsEl.innerHTML = '<p class="body-copy" style="color:var(--brand)">Failed to load overview data.</p>';
  }
}

function renderOverviewStats(overview: OverviewResponse, container: HTMLDivElement | null): void {
  if (!container) return;

  container.innerHTML = `
    <div class="dash-summary-grid">
      ${buildDashMetricCard("Jurisdictions", formatNumber(overview.jurisdictions_with_data))}
      ${buildDashMetricCard("Ledger records", formatNumber(overview.total_ledger_records))}
      ${buildDashMetricCard("NAICS records", formatNumber(overview.total_naics_records))}
      ${buildDashMetricCard("Date range", `${overview.earliest_ledger_date} to ${overview.latest_ledger_date}`)}
    </div>
  `;
}

function renderTopCitiesChart(overview: OverviewResponse, container: HTMLDivElement | null): void {
  if (!container || typeof Highcharts === "undefined") return;

  const topCities = overview.top_cities_by_sales.slice(0, 10).reverse();
  const categories = topCities.map((city) => city.name);
  const values = topCities.map((city) => city.total_sales_returned);

  if (dashboardState.topCitiesChartInstance) {
    dashboardState.topCitiesChartInstance.destroy();
  }

  dashboardState.topCitiesChartInstance = Highcharts.chart(container, {
    chart: {
      type: "bar",
      height: 420,
    },
    title: {
      text: "Top 10 cities by total sales tax returned",
    },
    subtitle: {
      text: "All-time cumulative sales tax distributions from the Oklahoma Tax Commission",
    },
    xAxis: {
      categories: categories,
      title: { text: null },
      labels: {
        style: { fontSize: "0.84rem" },
      },
    },
    yAxis: {
      min: 0,
      title: { text: "Total returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return formatCompactCurrency(this.value as number);
        },
      },
    },
    tooltip: {
      formatter: function (this: any): string {
        return `<b>${this.point.category as string}</b><br/>Total: ${formatCurrency(this.point.y as number)}`;
      },
    },
    plotOptions: {
      bar: {
        borderRadius: 4,
        dataLabels: {
          enabled: true,
          formatter: function (this: any): string {
            return formatCompactCurrency(this.point.y as number);
          },
          style: {
            fontWeight: "normal",
            color: "#5d6b75",
            fontSize: "0.78rem",
            textOutline: "none",
          },
        },
      },
    },
    legend: { enabled: false },
    series: [
      {
        name: "Sales tax returned",
        data: values,
        color: "#a63d40",
      },
    ],
  });
}

/* ── Revenue time series chart ── */

async function loadLedgerChart(copo: number, taxType: string): Promise<void> {
  const chartEl = document.querySelector<HTMLDivElement>("#revenue-chart");
  if (!chartEl) return;

  chartEl.innerHTML = '<p class="body-copy" style="padding:20px;text-align:center;">Loading chart data...</p>';

  try {
    const ledger = await fetchCityLedger(copo, taxType);
    renderRevenueChart(ledger, chartEl);
  } catch {
    chartEl.innerHTML = '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load ledger data.</p>';
  }
}

function renderRevenueChart(ledger: CityLedgerResponse, container: HTMLDivElement): void {
  if (typeof Highcharts === "undefined") return;

  if (!ledger.records.length) {
    container.innerHTML = '<p class="body-copy" style="padding:20px;text-align:center;">No records found for this tax type.</p>';
    return;
  }

  /* Clear any loading message */
  container.innerHTML = "";

  const sortedRecords = [...ledger.records].sort(
    (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );

  const categories = sortedRecords.map((r) => r.voucher_date);
  const values = sortedRecords.map((r) => r.returned);

  const cityName = dashboardState.cityDetail?.name ?? `COPO ${ledger.copo}`;
  const taxLabel = ledger.tax_type.charAt(0).toUpperCase() + ledger.tax_type.slice(1);

  if (dashboardState.revenueChartInstance) {
    dashboardState.revenueChartInstance.destroy();
  }

  dashboardState.revenueChartInstance = Highcharts.chart(container, {
    chart: {
      type: "line",
      height: 420,
      zooming: { type: "x" },
    },
    title: {
      text: `${cityName} -- ${taxLabel} tax revenue`,
    },
    subtitle: {
      text: `${sortedRecords.length} monthly records from the Oklahoma Tax Commission`,
    },
    xAxis: {
      categories: categories,
      tickInterval: Math.max(1, Math.floor(categories.length / 12)),
      labels: {
        rotation: -45,
        style: { fontSize: "0.72rem" },
      },
      title: { text: "Voucher date" },
    },
    yAxis: {
      title: { text: "Returned (USD)" },
      labels: {
        formatter: function (this: any): string {
          return formatCompactCurrency(this.value as number);
        },
      },
    },
    tooltip: {
      formatter: function (this: any): string {
        return `<b>${this.x as string}</b><br/>Returned: ${formatCurrency(this.y as number)}`;
      },
    },
    plotOptions: {
      line: {
        marker: {
          enabled: sortedRecords.length <= 60,
          radius: 3,
        },
        lineWidth: 2.5,
      },
    },
    legend: { enabled: false },
    series: [
      {
        name: `${taxLabel} tax returned`,
        data: values,
        color: "#1d6b70",
      },
    ],
  });
}
