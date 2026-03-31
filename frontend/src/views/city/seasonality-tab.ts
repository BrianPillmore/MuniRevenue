/* ==================================================
   Seasonality sub-tab
   ================================================== */

import { getCityLedger, getCitySeasonality } from "../../api";
import { renderChartDownloadBar } from "../../components/chart-download";
import { showLoading } from "../../components/loading";
import Highcharts from "../../theme";
import type { CityDetailResponse, LedgerRecord, SeasonalityResponse } from "../../types";
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

/* ---- Module ---- */

export function createSeasonalityTab(): SubTab {
  let seasonChart: any = null;

  /* ---- Key insights ---- */

  function buildInsights(data: SeasonalityResponse): string {
    const validMonths = data.months.filter((m) => m.mean_returned !== null);
    if (validMonths.length < 2) return "";

    const sorted = [...validMonths].sort(
      (a, b) => (b.mean_returned ?? 0) - (a.mean_returned ?? 0),
    );
    const strongest = sorted[0];
    const weakest = sorted[sorted.length - 1];
    const range = (strongest.mean_returned ?? 0) - (weakest.mean_returned ?? 0);

    const values = validMonths.map((m) => m.mean_returned ?? 0);
    const mean = values.reduce((a, b) => a + b, 0) / values.length;
    const variance =
      values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length;
    const stdDev = Math.sqrt(variance);
    const cv = mean !== 0 ? (stdDev / mean) * 100 : 0;

    return `
      <div class="insights-box">
        <p class="body-copy" style="margin:0 0 6px;font-weight:600;">Key Insights</p>
        <ul class="body-copy" style="margin:0;padding-left:20px;">
          <li>Strongest month: <strong>${escapeHtml(strongest.month_name)}</strong> (${formatCurrency(strongest.mean_returned ?? 0)} avg).</li>
          <li>Weakest month: <strong>${escapeHtml(weakest.month_name)}</strong> (${formatCurrency(weakest.mean_returned ?? 0)} avg).</li>
          <li>Seasonal range: <strong>${formatCurrency(range)}</strong> between peak and trough.</li>
          <li>Volatility (CV): <strong>${cv.toFixed(1)}%</strong> -- ${cv < 15 ? "relatively stable" : cv < 30 ? "moderate seasonality" : "high seasonal variation"}.</li>
        </ul>
      </div>
    `;
  }

  /* ---- Heatmap table ---- */

  function buildHeatmap(records: LedgerRecord[]): string {
    if (!records.length) return "";

    const sorted = [...records].sort(
      (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
    );

    /* Group by year -> month */
    const yearMap = new Map<number, Map<number, number>>();
    let globalMin = Infinity;
    let globalMax = -Infinity;

    for (const r of sorted) {
      const d = new Date(r.voucher_date);
      const year = d.getFullYear();
      const month = d.getMonth() + 1; // 1-12
      if (!yearMap.has(year)) yearMap.set(year, new Map());
      yearMap.get(year)!.set(month, r.returned);
      if (r.returned < globalMin) globalMin = r.returned;
      if (r.returned > globalMax) globalMax = r.returned;
    }

    const years = Array.from(yearMap.keys()).sort((a, b) => a - b);
    const monthHeaders = [
      "Jan", "Feb", "Mar", "Apr", "May", "Jun",
      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    const range = globalMax - globalMin || 1;

    const headerRow = `<tr><th style="text-align:left;">Year</th>${monthHeaders.map((m) => `<th>${m}</th>`).join("")}</tr>`;

    const bodyRows = years
      .map((year) => {
        const monthData = yearMap.get(year)!;
        const cells = Array.from({ length: 12 }, (_, i) => {
          const month = i + 1;
          const val = monthData.get(month);
          if (val === undefined) {
            return '<td class="heatmap-table" style="text-align:center;font-size:0.78rem;padding:6px 8px;">--</td>';
          }
          const intensity = Math.min(0.5, Math.max(0.05, ((val - globalMin) / range) * 0.5));
          return `<td style="text-align:center;font-size:0.78rem;padding:6px 8px;background:rgba(43,122,158,${intensity.toFixed(2)});" title="${formatCurrency(val)}">${formatCompactCurrency(val)}</td>`;
        }).join("");
        return `<tr><td style="font-weight:600;font-size:0.82rem;">${year}</td>${cells}</tr>`;
      })
      .join("");

    return `
      <div class="block-header" style="margin:20px 0 10px;">
        <h4 style="font-family:Georgia,serif;font-size:1.05rem;">Revenue Heatmap</h4>
        <p class="body-copy">Cell intensity shows relative revenue. Hover for exact amounts.</p>
      </div>
      <div class="table-shell">
        <table class="heatmap-table">
          <thead>${headerRow}</thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>
    `;
  }

  /* ---- Statistical table ---- */

  function buildStatsTable(data: SeasonalityResponse): string {
    const rows = data.months
      .map(
        (m) => `
      <tr>
        <td>${escapeHtml(m.month_name)}</td>
        <td style="text-align:right;">${m.mean_returned !== null ? formatCurrency(m.mean_returned) : "N/A"}</td>
        <td style="text-align:right;">${m.median_returned !== null ? formatCurrency(m.median_returned) : "N/A"}</td>
        <td style="text-align:right;">${m.min_returned !== null ? formatCurrency(m.min_returned) : "N/A"}</td>
        <td style="text-align:right;">${m.max_returned !== null ? formatCurrency(m.max_returned) : "N/A"}</td>
        <td style="text-align:right;">${m.std_dev !== null ? formatCurrency(m.std_dev) : "N/A"}</td>
        <td style="text-align:right;">${formatNumber(m.observations)}</td>
      </tr>
    `,
      )
      .join("");

    return wrapTable(
      ["Month", "Mean", "Median", "Min", "Max", "Std Dev", "Observations"],
      rows,
    );
  }

  /* ---- Main render ---- */

  function renderContent(
    container: HTMLElement,
    seasonality: SeasonalityResponse,
    ledgerRecords: LedgerRecord[],
    detail: CityDetailResponse,
  ): void {
    if (!seasonality.months.length) {
      container.innerHTML =
        '<p class="body-copy" style="padding:20px;text-align:center;">No seasonality data available for this tax type.</p>';
      return;
    }

    const cityName = detail.name;
    const taxLabel =
      seasonality.tax_type.charAt(0).toUpperCase() + seasonality.tax_type.slice(1);

    const insightsHtml = buildInsights(seasonality);
    const heatmapHtml = buildHeatmap(ledgerRecords);
    const statsHtml = buildStatsTable(seasonality);

    container.innerHTML = `
      <div style="padding:22px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>${escapeHtml(cityName)} -- ${escapeHtml(taxLabel)} tax seasonality</h3>
          <p class="body-copy">Monthly averages across all reporting years, showing recurring revenue patterns.</p>
        </div>
        <div id="seasonality-chart-inner" class="chart-box" style="margin-bottom:20px;"></div>
        <div id="seasonality-chart-download"></div>
        ${insightsHtml}
        ${heatmapHtml}
        <div class="block-header" style="margin:20px 0 10px;">
          <h4 style="font-family:Georgia,serif;font-size:1.05rem;">Statistical Summary</h4>
        </div>
        ${statsHtml}
      </div>
    `;

    /* Render bar chart */
    const chartEl = container.querySelector<HTMLElement>("#seasonality-chart-inner");
    if (chartEl) {
      destroyChart();
      const categories = seasonality.months.map((m) => m.month_name);
      const values = seasonality.months.map((m) => m.mean_returned ?? 0);

      seasonChart = Highcharts.chart(chartEl, {
        chart: { type: "column", height: 380 },
        title: { text: `${cityName} -- Average monthly ${taxLabel.toLowerCase()} tax revenue` },
        subtitle: { text: "Mean returned by calendar month across all years" },
        xAxis: { categories, title: { text: null }, labels: { style: { fontSize: "0.78rem" } } },
        yAxis: {
          min: 0,
          title: { text: "Mean returned (USD)" },
          labels: {
            formatter: function (this: any): string {
              return formatCompactCurrency(this.value as number);
            },
          },
        },
        tooltip: {
          formatter: function (this: any): string {
            return `<b>${this.x as string}</b><br/>Mean: ${formatCurrency(this.y as number)}`;
          },
        },
        plotOptions: {
          column: {
            borderRadius: 4,
            dataLabels: {
              enabled: seasonality.months.length <= 12,
              formatter: function (this: any): string {
                return formatCompactCurrency(this.point.y as number);
              },
              style: {
                fontWeight: "normal",
                color: "#5c6578",
                fontSize: "0.72rem",
                textOutline: "none",
              },
            },
          },
        },
        legend: { enabled: false },
        series: [{ name: "Mean returned", data: values, color: "#1b3a5c" }],
      });

      /* Download bar */
      const dlEl = container.querySelector<HTMLElement>("#seasonality-chart-download");
      if (dlEl && seasonChart) {
        renderChartDownloadBar(
          dlEl,
          seasonChart,
          categories,
          [{ name: "Mean returned", data: values }],
          `${cityName}-${taxLabel}-seasonality`,
        );
      }
    }
  }

  function destroyChart(): void {
    if (seasonChart) {
      seasonChart.destroy();
      seasonChart = null;
    }
  }

  return {
    async load(container, copo, taxType, detail) {
      showLoading(container);

      try {
        const [seasonality, ledger] = await Promise.all([
          getCitySeasonality(copo, taxType),
          getCityLedger(copo, taxType),
        ]);
        renderContent(container, seasonality, ledger.records, detail);
      } catch {
        container.innerHTML =
          '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load seasonality data.</p>';
      }
    },

    destroy() {
      destroyChart();
    },
  };
}
