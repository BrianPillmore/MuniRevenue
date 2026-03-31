/* ══════════════════════════════════════════════
   Revenue Explorer view
   ══════════════════════════════════════════════ */

import {
  getCityDetail,
  getCityLedger,
  getCityNaicsTop,
  getCitySeasonality,
  getIndustryTimeSeries,
} from "../api";
import {
  renderChartControls,
  type DisplayMode,
  type SmoothingType,
} from "../components/chart-controls";
import { renderCitySearch } from "../components/city-search";
import { renderKpiCards } from "../components/kpi-card";
import { showLoading } from "../components/loading";
import { renderTaxToggle } from "../components/tax-toggle";
import { navigateTo } from "../router";
import Highcharts from "../theme";
import type {
  CityDetailResponse,
  CityLedgerResponse,
  CityListItem,
  SeasonalityResponse,
  TopNaicsResponse,
  View,
} from "../types";
import {
  computeSeasonalFactors,
  escapeHtml,
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
  formatPercent,
  linearTrendline,
  monthName,
  rollingAverage,
  seasonallyAdjust,
  toPercentChange,
  wrapTable,
} from "../utils";

/* ── State ── */

interface CityViewState {
  copo: string | null;
  detail: CityDetailResponse | null;
  activeTaxType: string;
  activeSubTab: string;
  revenueChart: any;
  seasonalityChart: any;
  industriesChart: any;
  searchCleanup: (() => void) | null;
  rawRevenueCategories: string[];
  rawRevenueValues: number[];
}

const state: CityViewState = {
  copo: null,
  detail: null,
  activeTaxType: "sales",
  activeSubTab: "revenue",
  revenueChart: null,
  seasonalityChart: null,
  industriesChart: null,
  searchCleanup: null,
  rawRevenueCategories: [],
  rawRevenueValues: [],
};

/* ── Chart controls state for revenue chart ── */

interface RevenueControlState {
  smoothing: SmoothingType;
  seasonal: boolean;
  trendline: boolean;
  yAxisZero: boolean;
  displayMode: DisplayMode;
}

const revenueCtrl: RevenueControlState = {
  smoothing: "none",
  seasonal: false,
  trendline: false,
  yAxisZero: false,
  displayMode: "amount",
};

/* ── Chart management ── */

function destroyCharts(): void {
  if (state.revenueChart) { state.revenueChart.destroy(); state.revenueChart = null; }
  if (state.seasonalityChart) { state.seasonalityChart.destroy(); state.seasonalityChart = null; }
  if (state.industriesChart) { state.industriesChart.destroy(); state.industriesChart = null; }
}

/* ── Sub-tab rendering ── */

function activateSubTab(tabName: string): void {
  state.activeSubTab = tabName;
  document.querySelectorAll<HTMLButtonElement>(".sub-tab-btn").forEach((btn) => {
    const isActive = btn.dataset.subtab === tabName;
    btn.classList.toggle("is-active", isActive);
    btn.setAttribute("aria-selected", String(isActive));
  });
  document.querySelectorAll<HTMLElement>(".sub-tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.subtab === tabName);
  });
}

/* ── Revenue tab ── */

async function loadRevenueTab(copo: string, taxType: string): Promise<void> {
  const container = document.querySelector<HTMLElement>("#subtab-revenue");
  if (!container) return;
  showLoading(container);
  try {
    const ledger = await getCityLedger(copo, taxType);
    renderRevenueChart(ledger, container);
  } catch {
    container.innerHTML = '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load ledger data.</p>';
  }
}

function renderRevenueChart(ledger: CityLedgerResponse, container: HTMLElement): void {
  if (!ledger.records.length) {
    container.innerHTML = '<p class="body-copy" style="padding:20px;text-align:center;">No records found for this tax type.</p>';
    return;
  }
  container.innerHTML = '<div id="revenue-chart-inner" class="chart-box"></div><div id="revenue-chart-controls"></div>';
  const sortedRecords = [...ledger.records].sort((a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime());
  const categories = sortedRecords.map((r) => r.voucher_date);
  const values = sortedRecords.map((r) => r.returned);
  state.rawRevenueCategories = categories;
  state.rawRevenueValues = values;
  revenueCtrl.smoothing = "none";
  revenueCtrl.seasonal = false;
  revenueCtrl.trendline = false;
  revenueCtrl.yAxisZero = false;
  revenueCtrl.displayMode = "amount";
  buildRevenueHighchart(categories, values);
  const controlsEl = container.querySelector<HTMLElement>("#revenue-chart-controls");
  if (controlsEl) {
    renderChartControls(controlsEl, {
      onSmoothingChange: (type) => { revenueCtrl.smoothing = type; updateRevenueChart(); },
      onSeasonalToggle: (adjusted) => { revenueCtrl.seasonal = adjusted; updateRevenueChart(); },
      onTrendlineToggle: (show) => { revenueCtrl.trendline = show; updateRevenueChart(); },
      onYAxisZeroToggle: (fromZero) => { revenueCtrl.yAxisZero = fromZero; updateRevenueChart(); },
      onDisplayModeChange: (mode) => { revenueCtrl.displayMode = mode; updateRevenueChart(); },
    });
  }
}

function computeDisplayValues(): (number | null)[] {
  let values: number[] = [...state.rawRevenueValues];
  const dates = state.rawRevenueCategories;

  /* Seasonal adjustment first */
  if (revenueCtrl.seasonal) {
    const factors = computeSeasonalFactors(dates, values);
    values = seasonallyAdjust(dates, values, factors);
  }

  /* Smoothing */
  let displayValues: (number | null)[];
  switch (revenueCtrl.smoothing) {
    case "3mo": displayValues = rollingAverage(values, 3); break;
    case "6mo": displayValues = rollingAverage(values, 6); break;
    case "ttm": displayValues = rollingAverage(values, 12); break;
    default: displayValues = values;
  }

  /* Percent change transformation */
  if (revenueCtrl.displayMode === "pct_change") {
    const nonNullValues = displayValues.map((v) => v ?? 0);
    displayValues = toPercentChange(nonNullValues);
  }

  return displayValues;
}

function updateRevenueChart(): void {
  if (!state.revenueChart) return;
  const displayValues = computeDisplayValues();
  const isPctMode = revenueCtrl.displayMode === "pct_change";

  state.revenueChart.series[0].setData(displayValues, false);

  /* Handle trendline series */
  const existingTrendline = state.revenueChart.series.find((s: any) => s.name === "Trendline");
  if (revenueCtrl.trendline) {
    const nonNull = displayValues.filter((v): v is number => v !== null);
    if (nonNull.length >= 2) {
      const trend = linearTrendline(nonNull);
      let trendIdx = 0;
      const trendData = displayValues.map((v) => { if (v === null) return null; return trend[trendIdx++] ?? null; });
      if (existingTrendline) { existingTrendline.setData(trendData, false); }
      else { state.revenueChart.addSeries({ name: "Trendline", data: trendData, color: "#999", lineWidth: 1.5, dashStyle: "ShortDash", marker: { enabled: false }, enableMouseTracking: false, zIndex: 1 }, false); }
    }
  } else if (existingTrendline) { existingTrendline.remove(false); }

  /* Update Y-axis labels and title based on display mode */
  state.revenueChart.yAxis[0].update({
    min: revenueCtrl.yAxisZero ? 0 : undefined,
    title: { text: isPctMode ? "Month-over-month change (%)" : "Returned (USD)" },
    labels: {
      formatter: function (this: any): string {
        return isPctMode
          ? formatPercent(this.value as number)
          : formatCompactCurrency(this.value as number);
      },
    },
  }, false);

  /* Update tooltip format */
  // @ts-ignore -- Highcharts update accepts tooltip options
  state.revenueChart.update({
    tooltip: {
      formatter: function (this: any): string {
        if (isPctMode) {
          const val = this.y as number;
          const sign = val >= 0 ? "+" : "";
          return `<b>${this.x as string}</b><br/>MoM: ${sign}${val.toFixed(1)}%`;
        }
        return `<b>${this.x as string}</b><br/>Returned: ${formatCurrency(this.y as number)}`;
      },
    },
  }, false);

  state.revenueChart.redraw();
}

function buildRevenueHighchart(categories: string[], values: (number | null)[]): void {
  const chartEl = document.querySelector<HTMLElement>("#revenue-chart-inner");
  if (!chartEl) return;
  const cityName = state.detail?.name ?? `COPO ${state.copo}`;
  const taxLabel = state.activeTaxType.charAt(0).toUpperCase() + state.activeTaxType.slice(1);
  if (state.revenueChart) { state.revenueChart.destroy(); state.revenueChart = null; }
  state.revenueChart = Highcharts.chart(chartEl, {
    chart: { type: "line", height: 420, zooming: { type: "x" } },
    title: { text: `${cityName} -- ${taxLabel} tax revenue` },
    subtitle: { text: `${categories.length} monthly records from the Oklahoma Tax Commission` },
    xAxis: { categories, tickInterval: Math.max(1, Math.floor(categories.length / 12)), labels: { rotation: -45, style: { fontSize: "0.72rem" } }, title: { text: "Voucher date" } },
    yAxis: { title: { text: "Returned (USD)" }, labels: { formatter: function (this: any): string { return formatCompactCurrency(this.value as number); } } },
    tooltip: { formatter: function (this: any): string { return `<b>${this.x as string}</b><br/>Returned: ${formatCurrency(this.y as number)}`; } },
    plotOptions: { line: { marker: { enabled: categories.length <= 60, radius: 3 }, lineWidth: 2.5 } },
    legend: { enabled: false },
    series: [{ name: `${taxLabel} tax returned`, data: values, color: "#1d6b70" }],
  });
}

/* ── Industries tab ── */

async function loadIndustriesTab(copo: string, taxType: string): Promise<void> {
  const container = document.querySelector<HTMLElement>("#subtab-industries");
  if (!container) return;
  showLoading(container);
  try {
    const data = await getCityNaicsTop(copo, taxType, 15);
    renderIndustriesContent(data, container);
  } catch {
    container.innerHTML = '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load industry data.</p>';
  }
}

function renderIndustriesContent(data: TopNaicsResponse, container: HTMLElement): void {
  if (!data.records.length) { container.innerHTML = '<p class="body-copy" style="padding:20px;text-align:center;">No NAICS industry data available.</p>'; return; }
  const rows = data.records.map((r) => `
    <tr class="industry-row" data-code="${escapeHtml(r.activity_code)}" data-desc="${escapeHtml(r.activity_description || r.activity_code)}" style="cursor:pointer;">
      <td style="font-family:monospace;font-size:0.85rem;">${escapeHtml(r.activity_code)}</td>
      <td>${escapeHtml(r.sector)}</td>
      <td>${r.activity_description ? escapeHtml(r.activity_description) : ""}</td>
      <td style="text-align:right;">${formatCurrency(r.avg_sector_total)}</td>
      <td style="text-align:right;">${formatNumber(r.months_present)}</td>
    </tr>
  `).join("");
  container.innerHTML = `
    <div class="block-header" style="margin-bottom: 12px;"><h3>Top industries by average revenue</h3><p class="body-copy">Ranked by average monthly sector total. Click any row to see its time series.</p></div>
    <div id="industries-chart-inner" class="chart-box" style="margin-bottom: 20px;"></div>
    ${wrapTable(["NAICS Code", "Sector", "Description", "Avg. Monthly", "Months"], rows)}
    <div id="industry-modal" style="display:none;"></div>
  `;
  container.querySelectorAll<HTMLElement>(".industry-row").forEach((row) => {
    row.addEventListener("click", () => { showIndustryModal(row.dataset.code || "", row.dataset.desc || row.dataset.code || ""); });
  });
  renderIndustriesChart(data);
}

function renderIndustriesChart(data: TopNaicsResponse): void {
  const chartEl = document.querySelector<HTMLElement>("#industries-chart-inner");
  if (!chartEl) return;
  if (state.industriesChart) { state.industriesChart.destroy(); state.industriesChart = null; }
  const top10 = data.records.slice(0, 10).reverse();
  const categories = top10.map((r) => r.activity_description ? (r.activity_description.length > 35 ? r.activity_description.slice(0, 32) + "..." : r.activity_description) : r.activity_code);
  const values = top10.map((r) => r.avg_sector_total);
  const cityName = state.detail?.name ?? "City";
  state.industriesChart = Highcharts.chart(chartEl, {
    chart: { type: "bar", height: 380 },
    title: { text: `${cityName} -- Top industries by avg. monthly revenue` },
    subtitle: { text: "Top 10 NAICS sectors ranked by average monthly sector total" },
    xAxis: { categories, title: { text: null }, labels: { style: { fontSize: "0.78rem" } } },
    yAxis: { min: 0, title: { text: "Avg. monthly revenue (USD)" }, labels: { formatter: function (this: any): string { return formatCompactCurrency(this.value as number); } } },
    tooltip: { formatter: function (this: any): string { return `<b>${this.point.category as string}</b><br/>Avg. monthly: ${formatCurrency(this.point.y as number)}`; } },
    plotOptions: { bar: { borderRadius: 4, dataLabels: { enabled: true, formatter: function (this: any): string { return formatCompactCurrency(this.point.y as number); }, style: { fontWeight: "normal", color: "#5d6b75", fontSize: "0.78rem", textOutline: "none" } } } },
    legend: { enabled: false },
    series: [{ name: "Avg. monthly revenue", data: values, color: "#a63d40" }],
  });
}

/* ── Industry time series modal ── */

let modalChart: any = null;

async function showIndustryModal(activityCode: string, description: string): Promise<void> {
  const modal = document.getElementById("industry-modal");
  if (!modal || !state.copo) return;
  modal.style.display = "block";
  modal.innerHTML = `
    <div style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.4);z-index:500;display:flex;align-items:center;justify-content:center;" id="modal-overlay">
      <div style="background:#fffdf8;border-radius:24px;padding:28px;max-width:800px;width:90%;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(16,34,49,0.2);">
        <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:16px;">
          <div><p class="eyebrow">NAICS ${escapeHtml(activityCode)}</p><h3 style="margin:4px 0 0;font-family:Georgia,serif;font-size:1.3rem;">${escapeHtml(description)}</h3></div>
          <button id="modal-close" style="background:none;border:1px solid rgba(16,34,49,0.14);border-radius:12px;padding:8px 14px;cursor:pointer;font-size:0.9rem;">Close</button>
        </div>
        <div id="modal-chart-container" style="min-height:350px;">
          <div style="display:flex;align-items:center;justify-content:center;padding:60px;gap:12px;"><div class="loading-spinner"></div><span style="color:var(--muted);font-size:0.9rem;">Loading time series...</span></div>
        </div>
      </div>
    </div>
  `;
  document.getElementById("modal-close")?.addEventListener("click", closeIndustryModal);
  document.getElementById("modal-overlay")?.addEventListener("click", (e) => { if ((e.target as HTMLElement).id === "modal-overlay") closeIndustryModal(); });

  try {
    const data = await getIndustryTimeSeries(state.copo, activityCode, state.activeTaxType);
    const chartEl = document.querySelector<HTMLElement>("#modal-chart-container");
    if (!chartEl || !data.records.length) { if (chartEl) chartEl.innerHTML = '<p class="body-copy" style="text-align:center;padding:40px;">No time series data available.</p>'; return; }
    const months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const categories = data.records.map((r: any) => `${months[r.month]} ${String(r.year).slice(2)}`);
    const values = data.records.map((r: any) => r.sector_total);
    const t12Avg = values.length >= 12 ? values.slice(-12).reduce((a: number, b: number) => a + b, 0) / 12 : values.reduce((a: number, b: number) => a + b, 0) / values.length;
    const t12Total = values.length >= 12 ? values.slice(-12).reduce((a: number, b: number) => a + b, 0) : values.reduce((a: number, b: number) => a + b, 0);
    chartEl.innerHTML = `
      <div id="modal-chart" style="min-height:300px;"></div>
      <div style="display:flex;gap:16px;margin-top:12px;">
        <div class="dash-metric-card" style="flex:1;"><p>Trailing 12-Mo Avg</p><strong>${formatCurrency(t12Avg)}</strong></div>
        <div class="dash-metric-card" style="flex:1;"><p>Trailing 12-Mo Total</p><strong>${formatCurrency(t12Total)}</strong></div>
        <div class="dash-metric-card" style="flex:1;"><p>Data Points</p><strong>${formatNumber(values.length)}</strong></div>
      </div>
    `;
    if (modalChart) { modalChart.destroy(); modalChart = null; }
    const modalChartEl = document.querySelector<HTMLElement>("#modal-chart");
    if (!modalChartEl) return;
    // Highcharts types lack chart(element, options) overload; cast to bypass
    modalChart = (Highcharts as any).chart(modalChartEl, {
      chart: { type: "column", height: 300 },
      title: { text: null },
      xAxis: { categories, labels: { rotation: -45, style: { fontSize: "0.72rem" } }, tickInterval: Math.max(1, Math.floor(categories.length / 12)) },
      yAxis: { title: { text: null }, labels: { formatter: function (this: any): string { return formatCompactCurrency(this.value as number); } } },
      tooltip: { formatter: function (this: any): string { return `<b>${this.point.category as string}</b><br/>${formatCurrency(this.point.y as number)}`; } },
      plotOptions: { column: { borderRadius: 3, color: "#1d6b70" } },
      legend: { enabled: false },
      series: [{ name: "Monthly Revenue", data: values }],
    });
  } catch {
    const chartEl = document.querySelector<HTMLElement>("#modal-chart-container");
    if (chartEl) chartEl.innerHTML = '<p class="body-copy" style="text-align:center;padding:40px;color:var(--brand);">Failed to load time series.</p>';
  }
}

function closeIndustryModal(): void {
  if (modalChart) { modalChart.destroy(); modalChart = null; }
  const modal = document.getElementById("industry-modal");
  if (modal) { modal.style.display = "none"; modal.innerHTML = ""; }
}

/* ── Seasonality tab ── */

async function loadSeasonalityTab(copo: string, taxType: string): Promise<void> {
  const container = document.querySelector<HTMLElement>("#subtab-seasonality");
  if (!container) return;
  showLoading(container);
  try { const data = await getCitySeasonality(copo, taxType); renderSeasonalityContent(data, container); }
  catch { container.innerHTML = '<p class="body-copy" style="padding:20px;color:var(--brand)">Failed to load seasonality data.</p>'; }
}

function renderSeasonalityContent(data: SeasonalityResponse, container: HTMLElement): void {
  if (!data.months.length) { container.innerHTML = '<p class="body-copy" style="padding:20px;text-align:center;">No seasonality data available for this tax type.</p>'; return; }
  const rows = data.months.map((m) => `<tr><td>${escapeHtml(m.month_name)}</td><td>${m.mean_returned !== null ? formatCurrency(m.mean_returned) : "N/A"}</td><td>${m.median_returned !== null ? formatCurrency(m.median_returned) : "N/A"}</td><td>${m.min_returned !== null ? formatCurrency(m.min_returned) : "N/A"}</td><td>${m.max_returned !== null ? formatCurrency(m.max_returned) : "N/A"}</td><td>${m.std_dev !== null ? formatCurrency(m.std_dev) : "N/A"}</td><td>${formatNumber(m.observations)}</td></tr>`).join("");
  const cityName = state.detail?.name ?? "City";
  const taxLabel = data.tax_type.charAt(0).toUpperCase() + data.tax_type.slice(1);
  container.innerHTML = `
    <div class="block-header" style="margin-bottom: 12px;"><h3>${escapeHtml(cityName)} -- ${escapeHtml(taxLabel)} tax seasonality</h3><p class="body-copy">Monthly averages across all reporting years, showing recurring revenue patterns.</p></div>
    <div id="seasonality-chart-inner" class="chart-box" style="margin-bottom: 20px;"></div>
    ${wrapTable(["Month", "Mean", "Median", "Min", "Max", "Std Dev", "Observations"], rows)}
  `;
  renderSeasonalityChart(data);
}

function renderSeasonalityChart(data: SeasonalityResponse): void {
  const chartEl = document.querySelector<HTMLElement>("#seasonality-chart-inner");
  if (!chartEl) return;
  if (state.seasonalityChart) { state.seasonalityChart.destroy(); state.seasonalityChart = null; }
  const categories = data.months.map((m) => m.month_name);
  const values = data.months.map((m) => m.mean_returned ?? 0);
  const cityName = state.detail?.name ?? "City";
  const taxLabel = data.tax_type.charAt(0).toUpperCase() + data.tax_type.slice(1);
  state.seasonalityChart = Highcharts.chart(chartEl, {
    chart: { type: "column", height: 380 },
    title: { text: `${cityName} -- Average monthly ${taxLabel.toLowerCase()} tax revenue` },
    subtitle: { text: "Mean returned by calendar month across all years" },
    xAxis: { categories, title: { text: null }, labels: { style: { fontSize: "0.78rem" } } },
    yAxis: { min: 0, title: { text: "Mean returned (USD)" }, labels: { formatter: function (this: any): string { return formatCompactCurrency(this.value as number); } } },
    tooltip: { formatter: function (this: any): string { return `<b>${this.x as string}</b><br/>Mean: ${formatCurrency(this.y as number)}`; } },
    plotOptions: { column: { borderRadius: 4, dataLabels: { enabled: data.months.length <= 12, formatter: function (this: any): string { return formatCompactCurrency(this.point.y as number); }, style: { fontWeight: "normal", color: "#5d6b75", fontSize: "0.72rem", textOutline: "none" } } } },
    legend: { enabled: false },
    series: [{ name: "Mean returned", data: values, color: "#1d6b70" }],
  });
}

/* ── Details tab ── */

function renderDetailsTab(detail: CityDetailResponse): void {
  const container = document.querySelector<HTMLElement>("#subtab-details");
  if (!container) return;
  const rows = detail.tax_type_summaries.map((t) => `<tr><td>${escapeHtml(t.tax_type.charAt(0).toUpperCase() + t.tax_type.slice(1))}</td><td>${formatNumber(t.record_count)}</td><td>${t.earliest_date ?? "N/A"}</td><td>${t.latest_date ?? "N/A"}</td><td>${t.total_returned !== null ? formatCurrency(t.total_returned) : "N/A"}</td></tr>`).join("");
  container.innerHTML = `
    <div class="block-header" style="margin-bottom: 12px;"><p class="eyebrow">${escapeHtml(detail.jurisdiction_type)} / ${detail.county_name ? escapeHtml(detail.county_name) + " County" : "Unknown County"}</p><h3>${escapeHtml(detail.name)}</h3>${detail.population ? `<p class="body-copy">Population: ${formatNumber(detail.population)}</p>` : ""}</div>
    ${wrapTable(["Tax type", "Records", "Earliest", "Latest", "Total returned"], rows)}
    <p class="body-copy" style="margin-top: 14px;">NAICS industry records: ${formatNumber(detail.naics_record_count)}</p>
  `;
}

/* ── City selection handler ── */

async function onCitySelected(city: CityListItem): Promise<void> { navigateTo(`#/city/${city.copo}`); }

async function loadCity(copo: string): Promise<void> {
  state.copo = copo; state.activeTaxType = "sales"; state.activeSubTab = "revenue";
  const kpiContainer = document.querySelector<HTMLElement>("#city-kpis");
  const toggleContainer = document.querySelector<HTMLElement>("#city-tax-toggle");
  const contentArea = document.querySelector<HTMLElement>("#city-content");
  if (kpiContainer) showLoading(kpiContainer);
  if (contentArea) contentArea.style.display = "none";
  try {
    const detail = await getCityDetail(copo);
    state.detail = detail;
    if (kpiContainer) {
      const cards: { label: string; value: string }[] = [];
      const salesSummary = detail.tax_type_summaries.find((t) => t.tax_type === "sales");
      const useSummary = detail.tax_type_summaries.find((t) => t.tax_type === "use");
      const lodgingSummary = detail.tax_type_summaries.find((t) => t.tax_type === "lodging");
      if (salesSummary && salesSummary.total_returned !== null) cards.push({ label: "Sales tax total", value: formatCompactCurrency(salesSummary.total_returned) });
      if (useSummary && useSummary.total_returned !== null) cards.push({ label: "Use tax total", value: formatCompactCurrency(useSummary.total_returned) });
      if (lodgingSummary && lodgingSummary.total_returned !== null) cards.push({ label: "Lodging tax total", value: formatCompactCurrency(lodgingSummary.total_returned) });
      const totalRecords = detail.tax_type_summaries.reduce((sum, t) => sum + t.record_count, 0);
      cards.push({ label: "Records", value: formatNumber(totalRecords) });
      const dates = detail.tax_type_summaries.flatMap((t) => [t.earliest_date, t.latest_date]).filter(Boolean).sort();
      if (dates.length) cards.push({ label: "Date range", value: `${dates[0]} to ${dates[dates.length - 1]}` });
      kpiContainer.innerHTML = `<div class="section-heading" style="margin-bottom:14px;"><p class="eyebrow">${escapeHtml(detail.jurisdiction_type)} / ${detail.county_name ? escapeHtml(detail.county_name) + " County" : ""}</p><h2 style="font-size:1.3rem;">${escapeHtml(detail.name)}</h2></div>`;
      const grid = document.createElement("div");
      kpiContainer.appendChild(grid);
      renderKpiCards(grid, cards);
    }
    if (toggleContainer) { const types = detail.tax_type_summaries.map((s) => s.tax_type); renderTaxToggle(toggleContainer, types, state.activeTaxType, onTaxTypeChange); }
    if (contentArea) contentArea.style.display = "block";
    renderSubTabContent();
  } catch {
    if (kpiContainer) kpiContainer.innerHTML = '<p class="body-copy" style="color:var(--brand)">Failed to load city data. Check that the COPO code is valid.</p>';
  }
}

function onTaxTypeChange(taxType: string): void { state.activeTaxType = taxType; renderSubTabContent(); }

function renderSubTabContent(): void {
  if (!state.copo) return;
  switch (state.activeSubTab) {
    case "revenue": loadRevenueTab(state.copo, state.activeTaxType); break;
    case "industries": loadIndustriesTab(state.copo, state.activeTaxType); break;
    case "seasonality": loadSeasonalityTab(state.copo, state.activeTaxType); break;
    case "details": if (state.detail) renderDetailsTab(state.detail); break;
  }
}

/* ── View implementation ── */

export const cityView: View = {
  render(container: HTMLElement, params: Record<string, string>): void {
    container.className = "view-city";
    container.innerHTML = `
      <div class="city-explorer-layout">
        <div class="panel city-explorer-search"><div class="section-heading"><p class="eyebrow">Explore</p><h2>Revenue Explorer</h2></div><div id="city-search-mount"></div></div>
        <div id="city-kpis"></div>
        <div id="city-tax-toggle"></div>
        <div id="city-content" style="display: none;">
          <div class="sub-tabs" role="tablist" aria-label="City data sections">
            <button class="sub-tab-btn is-active" data-subtab="revenue" role="tab" aria-selected="true">Revenue</button>
            <button class="sub-tab-btn" data-subtab="industries" role="tab" aria-selected="false">Industries</button>
            <button class="sub-tab-btn" data-subtab="seasonality" role="tab" aria-selected="false">Seasonality</button>
            <button class="sub-tab-btn" data-subtab="details" role="tab" aria-selected="false">Details</button>
          </div>
          <div class="panel chart-container sub-tab-panel is-active" data-subtab="revenue" id="subtab-revenue" role="tabpanel"></div>
          <div class="panel sub-tab-panel" data-subtab="industries" id="subtab-industries" role="tabpanel" style="padding:22px;"></div>
          <div class="panel sub-tab-panel" data-subtab="seasonality" id="subtab-seasonality" role="tabpanel" style="padding:22px;"></div>
          <div class="panel sub-tab-panel" data-subtab="details" id="subtab-details" role="tabpanel" style="padding:22px;"></div>
        </div>
      </div>
    `;
    const searchMount = container.querySelector<HTMLElement>("#city-search-mount")!;
    state.searchCleanup = renderCitySearch(searchMount, { onSelect: onCitySelected, placeholder: "Search cities or counties..." });
    container.querySelectorAll<HTMLButtonElement>(".sub-tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => { const tab = btn.dataset.subtab; if (tab && tab !== state.activeSubTab) { destroyCharts(); activateSubTab(tab); renderSubTabContent(); } });
    });
    if (params.copo) loadCity(params.copo);
  },

  destroy(): void {
    destroyCharts();
    if (state.searchCleanup) { state.searchCleanup(); state.searchCleanup = null; }
    state.copo = null; state.detail = null; state.activeTaxType = "sales"; state.activeSubTab = "revenue";
    state.rawRevenueCategories = []; state.rawRevenueValues = [];
  },
};
