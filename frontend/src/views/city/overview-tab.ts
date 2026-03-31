/* ==================================================
   Overview sub-tab -- City Overview
   ================================================== */

import { getCityLedger } from "../../api";
import { showLoading } from "../../components/loading";
import Highcharts from "../../theme";
import type { CityDetailResponse, LedgerRecord } from "../../types";
import {
  escapeHtml,
  formatCompactCurrency,
  formatCurrency,
  formatNumber,
  trendArrow,
} from "../../utils";

export interface SubTab {
  load(container: HTMLElement, copo: string, taxType: string, detail: CityDetailResponse): Promise<void>;
  destroy(): void;
}

/* ---- State ---- */

let sparklineCharts: any[] = [];

/* ---- Helpers ---- */

function last12(records: LedgerRecord[]): LedgerRecord[] {
  const sorted = [...records].sort(
    (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );
  return sorted.slice(-12);
}

function last24Sorted(records: LedgerRecord[]): LedgerRecord[] {
  const sorted = [...records].sort(
    (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
  );
  return sorted.slice(-24);
}

/* ---- Module ---- */

export function createOverviewTab(): SubTab {
  return {
    async load(container, copo, taxType, detail) {
      showLoading(container);

      try {
        const ledger = await getCityLedger(copo, taxType);
        const records = ledger.records;

        if (!records.length) {
          container.innerHTML = '<p class="body-copy" style="padding:20px;text-align:center;">No ledger data available for this tax type.</p>';
          return;
        }

        const sorted = [...records].sort(
          (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
        );

        /* Compute KPI metrics */
        const t12 = last12(records);
        const t12Total = t12.reduce((s, r) => s + r.returned, 0);
        const t12Avg = t12.length > 0 ? t12Total / t12.length : 0;

        const latest = sorted[sorted.length - 1];
        const momPct = latest.mom_pct;
        const yoyPct = latest.yoy_pct;

        const allTimeTotal = sorted.reduce((s, r) => s + r.returned, 0);
        const firstDate = sorted[0].voucher_date;
        const lastDate = sorted[sorted.length - 1].voucher_date;

        const kpiCards = `
          <div class="dash-summary-grid">
            <article class="dash-metric-card">
              <p>Trailing 12-Mo Total</p>
              <strong>${escapeHtml(formatCurrency(t12Total))}</strong>
            </article>
            <article class="dash-metric-card">
              <p>Trailing 12-Mo Avg Monthly</p>
              <strong>${escapeHtml(formatCurrency(t12Avg))}</strong>
            </article>
            <article class="dash-metric-card">
              <p>Latest Month (${escapeHtml(latest.voucher_date)})</p>
              <strong>${escapeHtml(formatCurrency(latest.returned))}</strong>
              ${trendArrow(momPct)}
              <span class="dash-metric-subtitle">MoM</span>
            </article>
            <article class="dash-metric-card">
              <p>Year-over-Year</p>
              <strong>${yoyPct !== null ? (yoyPct >= 0 ? "+" : "") + yoyPct.toFixed(1) + "%" : "N/A"}</strong>
              ${trendArrow(yoyPct)}
              <span class="dash-metric-subtitle">YoY trend</span>
            </article>
            <article class="dash-metric-card">
              <p>All-Time Total Returned</p>
              <strong>${escapeHtml(formatCompactCurrency(allTimeTotal))}</strong>
            </article>
            <article class="dash-metric-card">
              <p>Records / Date Range</p>
              <strong>${formatNumber(sorted.length)}</strong>
              <span class="dash-metric-subtitle">${escapeHtml(firstDate)} to ${escapeHtml(lastDate)}</span>
            </article>
          </div>
        `;

        /* Sparkline grid -- one per tax type that has data */
        const types = detail.tax_type_summaries
          .filter((t) => t.record_count > 0)
          .map((t) => t.tax_type);

        const sparklineSlots = types
          .map(
            (t) => `
            <div class="sparkline-card">
              <p class="eyebrow" style="margin-bottom:4px;">${escapeHtml(t.charAt(0).toUpperCase() + t.slice(1))} Tax</p>
              <div id="sparkline-${escapeHtml(t)}" style="height:80px;"></div>
            </div>
          `,
          )
          .join("");

        container.innerHTML = `
          <div style="padding:22px;">
            <div class="block-header" style="margin-bottom:14px;">
              <h3>City Overview</h3>
              <p class="body-copy">Key metrics for the active tax type, plus mini sparklines for all available types.</p>
            </div>
            ${kpiCards}
            <div class="sparkline-grid" style="margin-top:20px;">
              ${sparklineSlots}
            </div>
          </div>
        `;

        /* Render sparklines */
        destroySparklines();
        for (const t of types) {
          try {
            const data =
              t === taxType ? ledger : await getCityLedger(copo, t);
            const s = last24Sorted(data.records);
            const vals = s.map((r) => r.returned);
            const el = container.querySelector<HTMLElement>(`#sparkline-${t}`);
            if (el && vals.length > 0) {
              const c = Highcharts.chart(el, {
                chart: { type: "line", height: 80, margin: [2, 0, 2, 0], backgroundColor: "transparent" },
                title: { text: undefined },
                xAxis: { visible: false },
                yAxis: { visible: false },
                legend: { enabled: false },
                tooltip: { enabled: false },
                plotOptions: {
                  line: {
                    marker: { enabled: false },
                    lineWidth: 2,
                    color: "#1b3a5c",
                    enableMouseTracking: false,
                  },
                },
                series: [{ name: t, data: vals }],
              });
              sparklineCharts.push(c);
            }
          } catch {
            /* Sparkline failure is non-critical */
          }
        }
      } catch {
        container.innerHTML =
          '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load overview data.</p>';
      }
    },

    destroy() {
      destroySparklines();
    },
  };
}

function destroySparklines(): void {
  for (const c of sparklineCharts) {
    try {
      c.destroy();
    } catch {
      /* ignore */
    }
  }
  sparklineCharts = [];
}
