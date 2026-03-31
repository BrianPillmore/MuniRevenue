/* ==================================================
   Industry View sub-tab
   ================================================== */

import { getCityNaicsTop, getIndustryTimeSeries } from "../../api";
import { renderChartDownloadBar } from "../../components/chart-download";
import { showLoading } from "../../components/loading";
import Highcharts from "../../theme";
import type { CityDetailResponse, TopNaicsRecord, TopNaicsResponse } from "../../types";
import {
  escapeHtml,
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
  wrapTable,
} from "../../utils";

export interface SubTab {
  load(container: HTMLElement, copo: string, taxType: string, detail: CityDetailResponse): Promise<void>;
  destroy(): void;
}

type ViewMode = "top10" | "sector" | "all";

/* ---- Module ---- */

export function createIndustryTab(): SubTab {
  let barChart: any = null;
  let expandCharts: any[] = [];
  let data: TopNaicsResponse | null = null;
  let viewMode: ViewMode = "top10";
  let expandedCode: string | null = null;
  let currentCopo = "";
  let currentTaxType = "";
  let currentDetail: CityDetailResponse | null = null;

  /* ---- Sector rollup helper ---- */

  interface SectorRollup {
    sector: string;
    avgTotal: number;
    totalAcrossMonths: number;
    codeCount: number;
  }

  function buildSectorRollups(records: TopNaicsRecord[]): SectorRollup[] {
    const map = new Map<string, SectorRollup>();
    for (const r of records) {
      const key = r.sector || "Unknown";
      const existing = map.get(key);
      if (existing) {
        existing.avgTotal += r.avg_sector_total;
        existing.totalAcrossMonths += r.total_across_months;
        existing.codeCount += 1;
      } else {
        map.set(key, {
          sector: key,
          avgTotal: r.avg_sector_total,
          totalAcrossMonths: r.total_across_months,
          codeCount: 1,
        });
      }
    }
    return Array.from(map.values()).sort((a, b) => b.avgTotal - a.avgTotal);
  }

  /* ---- Concentration metric ---- */

  function topNShare(records: TopNaicsRecord[], n: number): number {
    const total = records.reduce((s, r) => s + r.avg_sector_total, 0);
    if (total === 0) return 0;
    const topN = records
      .slice()
      .sort((a, b) => b.avg_sector_total - a.avg_sector_total)
      .slice(0, n);
    const topSum = topN.reduce((s, r) => s + r.avg_sector_total, 0);
    return (topSum / total) * 100;
  }

  /* ---- Build tables ---- */

  function buildDetailTable(records: TopNaicsRecord[], limit?: number): string {
    const display = limit ? records.slice(0, limit) : records;
    const rest = limit ? records.slice(limit) : [];

    const topRows = display
      .map(
        (r) => `
      <tr class="industry-row" data-code="${escapeHtml(r.activity_code)}" data-desc="${escapeHtml(r.activity_description || r.activity_code)}" style="cursor:pointer;">
        <td style="font-family:monospace;font-size:0.85rem;">${escapeHtml(r.activity_code)}</td>
        <td>${r.activity_description ? escapeHtml(r.activity_description) : ""}</td>
        <td>${escapeHtml(r.sector)}</td>
        <td style="text-align:right;">${formatCurrency(r.avg_sector_total)}</td>
        <td style="text-align:right;">${formatNumber(r.months_present)}</td>
        <td style="text-align:right;">${formatCurrency(r.total_across_months)}</td>
      </tr>
      <tr class="industry-expand-row" data-expand-code="${escapeHtml(r.activity_code)}" style="display:none;">
        <td colspan="6" style="padding:0 !important;">
          <div class="industry-expand-chart" id="expand-chart-${escapeHtml(r.activity_code)}"></div>
        </td>
      </tr>
    `,
      )
      .join("");

    let otherRows = "";
    if (rest.length > 0) {
      const otherAvg = rest.reduce((sum, r) => sum + r.avg_sector_total, 0);
      const otherMonths =
        rest.length > 0
          ? Math.round(rest.reduce((sum, r) => sum + r.months_present, 0) / rest.length)
          : 0;
      const otherTotal = rest.reduce((sum, r) => sum + r.total_across_months, 0);

      otherRows += `
        <tr data-expand="other" style="cursor:pointer;background:rgba(43,122,158,0.04);font-weight:600;">
          <td style="font-family:monospace;font-size:0.85rem;"><span class="other-chevron">\u25BC</span></td>
          <td colspan="2">Other (${rest.length} industries)</td>
          <td style="text-align:right;">${formatCurrency(otherAvg)}</td>
          <td style="text-align:right;">${formatNumber(otherMonths)} avg</td>
          <td style="text-align:right;">${formatCurrency(otherTotal)}</td>
        </tr>
      `;

      otherRows += rest
        .map(
          (r) => `
        <tr class="other-hidden-row industry-row" data-code="${escapeHtml(r.activity_code)}" data-desc="${escapeHtml(r.activity_description || r.activity_code)}" style="display:none;cursor:pointer;opacity:0.85;">
          <td style="font-family:monospace;font-size:0.85rem;padding-left:24px;">${escapeHtml(r.activity_code)}</td>
          <td>${r.activity_description ? escapeHtml(r.activity_description) : ""}</td>
          <td>${escapeHtml(r.sector)}</td>
          <td style="text-align:right;">${formatCurrency(r.avg_sector_total)}</td>
          <td style="text-align:right;">${formatNumber(r.months_present)}</td>
          <td style="text-align:right;">${formatCurrency(r.total_across_months)}</td>
        </tr>
        <tr class="other-hidden-row industry-expand-row" data-expand-code="${escapeHtml(r.activity_code)}" style="display:none;">
          <td colspan="6" style="padding:0 !important;">
            <div class="industry-expand-chart" id="expand-chart-${escapeHtml(r.activity_code)}"></div>
          </td>
        </tr>
      `,
        )
        .join("");
    }

    return wrapTable(
      ["NAICS Code", "Description", "Sector", "Avg. Monthly", "Months", "Total"],
      topRows + otherRows,
    );
  }

  function buildSectorTable(records: TopNaicsRecord[]): string {
    const rollups = buildSectorRollups(records);
    const rows = rollups
      .map(
        (r) => `
      <tr>
        <td style="font-weight:600;">${escapeHtml(r.sector)}</td>
        <td style="text-align:right;">${formatCurrency(r.avgTotal)}</td>
        <td style="text-align:right;">${formatCurrency(r.totalAcrossMonths)}</td>
        <td style="text-align:right;">${formatNumber(r.codeCount)}</td>
      </tr>
    `,
      )
      .join("");
    return wrapTable(["Sector", "Avg. Monthly (sum)", "Total across months", "NAICS Codes"], rows);
  }

  /* ---- Render industries chart ---- */

  function renderBarChart(container: HTMLElement, records: TopNaicsResponse): void {
    const chartEl = container.querySelector<HTMLElement>("#industries-chart-inner");
    if (!chartEl) return;
    destroyBarChart();
    const top10 = records.records.slice(0, 10).reverse();
    const categories = top10.map((r) =>
      r.activity_description
        ? r.activity_description.length > 35
          ? r.activity_description.slice(0, 32) + "..."
          : r.activity_description
        : r.activity_code,
    );
    const values = top10.map((r) => r.avg_sector_total);
    const cityName = currentDetail?.name ?? "City";
    barChart = Highcharts.chart(chartEl, {
      chart: { type: "bar", height: 380 },
      title: { text: `${cityName} -- Top industries by avg. monthly revenue` },
      subtitle: { text: "Top 10 NAICS sectors ranked by average monthly sector total" },
      xAxis: { categories, title: { text: undefined }, labels: { style: { fontSize: "0.78rem" } } },
      yAxis: {
        min: 0,
        title: { text: "Avg. monthly revenue (USD)" },
        labels: {
          formatter: function (this: any): string {
            return formatCompactCurrency(this.value as number);
          },
        },
      },
      tooltip: {
        formatter: function (this: any): string {
          return `<b>${this.point.category as string}</b><br/>Avg. monthly: ${formatCurrency(this.point.y as number)}`;
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
            style: { fontWeight: "normal", color: "#5c6578", fontSize: "0.78rem", textOutline: "none" },
          },
        },
      },
      legend: { enabled: false },
      series: [{ name: "Avg. monthly revenue", data: values, color: "#c8922a" }],
    });
  }

  /* ---- Inline expand for industry time series ---- */

  async function toggleExpand(
    container: HTMLElement,
    activityCode: string,
  ): Promise<void> {
    const expandRow = container.querySelector<HTMLElement>(
      `tr[data-expand-code="${activityCode}"]`,
    );
    if (!expandRow) return;

    /* If already expanded, collapse */
    if (expandedCode === activityCode) {
      expandRow.style.display = "none";
      destroyExpandCharts();
      expandedCode = null;
      return;
    }

    /* Collapse previous */
    if (expandedCode) {
      const prev = container.querySelector<HTMLElement>(
        `tr[data-expand-code="${expandedCode}"]`,
      );
      if (prev) prev.style.display = "none";
      destroyExpandCharts();
    }

    expandedCode = activityCode;
    expandRow.style.display = "";
    const chartDiv = expandRow.querySelector<HTMLElement>(`#expand-chart-${activityCode}`);
    if (!chartDiv) return;
    chartDiv.innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;padding:40px;gap:8px;"><div class="loading-spinner"></div><span style="color:var(--muted);font-size:0.85rem;">Loading...</span></div>';

    try {
      const ts = await getIndustryTimeSeries(currentCopo, activityCode, currentTaxType);
      if (!ts.records || !ts.records.length) {
        chartDiv.innerHTML = '<p class="body-copy" style="padding:16px;text-align:center;">No time series data.</p>';
        return;
      }
      const months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
      const cats = ts.records.map((r: any) => `${months[r.month]} ${String(r.year).slice(2)}`);
      const vals = ts.records.map((r: any) => r.sector_total);

      chartDiv.innerHTML = `<div id="expand-hc-${activityCode}" style="min-height:250px;"></div>`;
      const hcEl = chartDiv.querySelector<HTMLElement>(`#expand-hc-${activityCode}`);
      if (!hcEl) return;

      const c = Highcharts.chart(hcEl, {
        chart: { type: "column", height: 250 },
        title: { text: undefined },
        xAxis: {
          categories: cats,
          labels: { rotation: -45, style: { fontSize: "0.72rem" } },
          tickInterval: Math.max(1, Math.floor(cats.length / 12)),
        },
        yAxis: {
          title: { text: undefined },
          labels: {
            formatter: function (this: any): string {
              return formatCompactCurrency(this.value as number);
            },
          },
        },
        tooltip: {
          formatter: function (this: any): string {
            return `<b>${this.point.category as string}</b><br/>${formatCurrency(this.point.y as number)}`;
          },
        },
        plotOptions: { column: { borderRadius: 3, color: "#1b3a5c" } },
        legend: { enabled: false },
        series: [{ name: "Monthly Revenue", data: vals }],
      });
      expandCharts.push(c);
    } catch {
      chartDiv.innerHTML =
        '<p class="body-copy" style="padding:16px;text-align:center;color:var(--danger);">Failed to load time series.</p>';
    }
  }

  /* ---- Main render ---- */

  function renderContent(container: HTMLElement): void {
    if (!data || !data.records.length) {
      container.innerHTML =
        '<p class="body-copy" style="padding:20px;text-align:center;">No NAICS industry data available.</p>';
      return;
    }

    const concentration = topNShare(data.records, 5);

    const toggleHtml = `
      <div class="chart-ctrl-group" style="margin-bottom:14px;">
        <span class="chart-ctrl-label">View</span>
        <div class="chart-ctrl-pills">
          <button class="chart-ctrl-btn ind-view-btn${viewMode === "top10" ? " is-active" : ""}" data-mode="top10">Top 10 + Other</button>
          <button class="chart-ctrl-btn ind-view-btn${viewMode === "sector" ? " is-active" : ""}" data-mode="sector">Sector Rollup</button>
          <button class="chart-ctrl-btn ind-view-btn${viewMode === "all" ? " is-active" : ""}" data-mode="all">All</button>
        </div>
      </div>
    `;

    let tableHtml: string;
    switch (viewMode) {
      case "top10":
        tableHtml = buildDetailTable(data.records, 10);
        break;
      case "sector":
        tableHtml = buildSectorTable(data.records);
        break;
      case "all":
        tableHtml = buildDetailTable(data.records);
        break;
    }

    container.innerHTML = `
      <div style="padding:22px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>Top industries by average revenue</h3>
          <p class="body-copy">Ranked by average monthly sector total. Click any row to see its time series.</p>
        </div>
        <div id="industries-chart-inner" class="chart-box" style="margin-bottom:20px;"></div>
        <div id="industries-chart-download"></div>
        <div class="insights-box" style="margin-bottom:14px;">
          <p class="body-copy" style="margin:0;"><strong>Industry concentration:</strong> Top 5 industries account for <strong>${concentration.toFixed(1)}%</strong> of average monthly revenue.</p>
        </div>
        ${toggleHtml}
        ${tableHtml}
      </div>
    `;

    /* Render bar chart */
    renderBarChart(container, data);

    /* Download bar for chart */
    const dlEl = container.querySelector<HTMLElement>("#industries-chart-download");
    if (dlEl && barChart) {
      const top10 = data.records.slice(0, 10);
      const cats = top10.map((r) => r.activity_description || r.activity_code);
      const vals = top10.map((r) => r.avg_sector_total);
      renderChartDownloadBar(dlEl, barChart, cats, [{ name: "Avg Monthly", data: vals }], `${currentDetail?.name ?? "city"}-industries`);
    }

    /* View toggle handlers */
    container.querySelectorAll<HTMLButtonElement>(".ind-view-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.dataset.mode as ViewMode;
        if (mode && mode !== viewMode) {
          viewMode = mode;
          expandedCode = null;
          destroyExpandCharts();
          renderContent(container);
        }
      });
    });

    /* Row click handlers */
    container.querySelectorAll<HTMLElement>(".industry-row").forEach((row) => {
      row.addEventListener("click", () => {
        const code = row.dataset.code || "";
        if (code) toggleExpand(container, code);
      });
    });

    /* Other expand/collapse */
    const otherRow = container.querySelector<HTMLElement>("[data-expand='other']");
    let otherExpanded = false;
    if (otherRow) {
      otherRow.addEventListener("click", (e) => {
        e.stopPropagation();
        otherExpanded = !otherExpanded;
        const hiddenRows = container.querySelectorAll<HTMLElement>(".other-hidden-row");
        const chevron = otherRow.querySelector<HTMLElement>(".other-chevron");
        hiddenRows.forEach((row) => {
          row.style.display = otherExpanded ? "" : "none";
        });
        if (chevron) {
          chevron.textContent = otherExpanded ? "\u25B2" : "\u25BC";
        }

        /* Attach click handlers on newly visible rows */
        if (otherExpanded) {
          container.querySelectorAll<HTMLElement>(".other-hidden-row.industry-row").forEach((row) => {
            row.addEventListener("click", () => {
              const code = row.dataset.code || "";
              if (code) toggleExpand(container, code);
            });
          });
        }
      });
    }
  }

  /* ---- Cleanup ---- */

  function destroyBarChart(): void {
    if (barChart) {
      barChart.destroy();
      barChart = null;
    }
  }

  function destroyExpandCharts(): void {
    for (const c of expandCharts) {
      try {
        c.destroy();
      } catch {
        /* ignore */
      }
    }
    expandCharts = [];
  }

  return {
    async load(container, copo, taxType, detail) {
      currentCopo = copo;
      currentTaxType = taxType;
      currentDetail = detail;
      viewMode = "top10";
      expandedCode = null;
      showLoading(container);

      try {
        const result = await getCityNaicsTop(copo, taxType, 50);
        data = result;
        renderContent(container);
      } catch {
        container.innerHTML =
          '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load industry data.</p>';
      }
    },

    destroy() {
      destroyBarChart();
      destroyExpandCharts();
      data = null;
      expandedCode = null;
      currentDetail = null;
    },
  };
}
