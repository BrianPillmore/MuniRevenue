/* ==================================================
   Details sub-tab -- Data Details
   ================================================== */

import { getCityForecast, getCityLedger } from "../../api";
import { showLoading } from "../../components/loading";
import type { CityDetailResponse, LedgerRecord } from "../../types";
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

export function createDetailsTab(): SubTab {
  let currentCopo = "";
  let currentTaxType = "";
  let currentDetail: CityDetailResponse | null = null;
  let allRecords: LedgerRecord[] = [];

  /* ---- CSV download helpers ---- */

  function triggerDownload(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function downloadLedgerCsv(records: LedgerRecord[], filename: string): void {
    const header = [
      "voucher_date",
      "tax_type",
      "tax_rate",
      "current_month_collection",
      "refunded",
      "suspended_monies",
      "apportioned",
      "revolving_fund",
      "interest_returned",
      "returned",
      "mom_pct",
      "yoy_pct",
    ].join(",");

    const rows = records.map((r) =>
      [
        r.voucher_date,
        r.tax_type,
        r.tax_rate,
        r.current_month_collection,
        r.refunded,
        r.suspended_monies,
        r.apportioned,
        r.revolving_fund,
        r.interest_returned,
        r.returned,
        r.mom_pct ?? "",
        r.yoy_pct ?? "",
      ].join(","),
    );

    const csv = [header, ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    triggerDownload(blob, filename);
  }

  /* ---- Sort handler ---- */

  type SortDir = "asc" | "desc";

  interface SortState {
    col: string;
    dir: SortDir;
  }

  let sortState: SortState = { col: "voucher_date", dir: "desc" };

  function sortRecords(records: LedgerRecord[], col: string, dir: SortDir): LedgerRecord[] {
    const sorted = [...records];
    sorted.sort((a, b) => {
      let av: any = (a as any)[col];
      let bv: any = (b as any)[col];
      if (av === null || av === undefined) av = -Infinity;
      if (bv === null || bv === undefined) bv = -Infinity;
      if (typeof av === "string") {
        return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      return dir === "asc" ? av - bv : bv - av;
    });
    return sorted;
  }

  /* ---- Render table with full fields ---- */

  function buildLedgerTable(records: LedgerRecord[]): string {
    const sorted = sortRecords(records, sortState.col, sortState.dir);

    function sortIcon(col: string): string {
      if (sortState.col !== col) return "";
      return sortState.dir === "asc" ? " &#8593;" : " &#8595;";
    }

    const headers = [
      { key: "voucher_date", label: "Date" },
      { key: "tax_type", label: "Type" },
      { key: "tax_rate", label: "Rate" },
      { key: "current_month_collection", label: "Collection" },
      { key: "refunded", label: "Refunded" },
      { key: "suspended_monies", label: "Suspended" },
      { key: "apportioned", label: "Apportioned" },
      { key: "revolving_fund", label: "Revolving" },
      { key: "interest_returned", label: "Interest" },
      { key: "returned", label: "Returned" },
      { key: "mom_pct", label: "MoM %" },
      { key: "yoy_pct", label: "YoY %" },
    ];

    const headerHtml = headers
      .map(
        (h) =>
          `<th class="sortable-th" data-col="${h.key}" style="cursor:pointer;white-space:nowrap;">${h.label}${sortIcon(h.key)}</th>`,
      )
      .join("");

    const rows = sorted
      .map(
        (r) => `
      <tr>
        <td>${escapeHtml(r.voucher_date)}</td>
        <td>${escapeHtml(r.tax_type)}</td>
        <td style="text-align:right;">${r.tax_rate.toFixed(4)}</td>
        <td style="text-align:right;">${formatCurrency(r.current_month_collection)}</td>
        <td style="text-align:right;">${formatCurrency(r.refunded)}</td>
        <td style="text-align:right;">${formatCurrency(r.suspended_monies)}</td>
        <td style="text-align:right;">${formatCurrency(r.apportioned)}</td>
        <td style="text-align:right;">${formatCurrency(r.revolving_fund)}</td>
        <td style="text-align:right;">${formatCurrency(r.interest_returned)}</td>
        <td style="text-align:right;font-weight:600;">${formatCurrency(r.returned)}</td>
        <td style="text-align:right;">${r.mom_pct !== null ? r.mom_pct.toFixed(1) + "%" : "--"}</td>
        <td style="text-align:right;">${r.yoy_pct !== null ? r.yoy_pct.toFixed(1) + "%" : "--"}</td>
      </tr>
    `,
      )
      .join("");

    return `
      <div class="table-shell">
        <table>
          <thead><tr>${headerHtml}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  /* ---- Main render ---- */

  function renderContent(container: HTMLElement, records: LedgerRecord[]): void {
    const cityName = currentDetail?.name ?? "City";

    /* Summary stats */
    const total = records.reduce((s, r) => s + r.returned, 0);
    const avg = records.length > 0 ? total / records.length : 0;
    const sorted = [...records].sort(
      (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
    );
    const firstDate = sorted.length > 0 ? sorted[0].voucher_date : "N/A";
    const lastDate = sorted.length > 0 ? sorted[sorted.length - 1].voucher_date : "N/A";

    const summaryHtml = `
      <div class="dash-summary-grid" style="margin-bottom:16px;">
        <article class="dash-metric-card">
          <p>Total Records</p>
          <strong>${formatNumber(records.length)}</strong>
        </article>
        <article class="dash-metric-card">
          <p>Date Range</p>
          <strong style="font-size:0.95rem;">${escapeHtml(firstDate)} to ${escapeHtml(lastDate)}</strong>
        </article>
        <article class="dash-metric-card">
          <p>Sum Returned</p>
          <strong>${formatCompactCurrency(total)}</strong>
        </article>
        <article class="dash-metric-card">
          <p>Avg Returned</p>
          <strong>${formatCurrency(avg)}</strong>
        </article>
      </div>
    `;

    const tableHtml = buildLedgerTable(records);

    container.innerHTML = `
      <div style="padding:22px;">
        <div class="block-header" style="margin-bottom:14px;">
          <h3>${escapeHtml(cityName)} -- Data Details</h3>
          <p class="body-copy">Full ledger data with all fields. Click column headers to sort.</p>
        </div>
        ${summaryHtml}
        <div style="display:flex;gap:12px;align-items:center;margin-bottom:14px;flex-wrap:wrap;">
          <label class="body-copy" style="font-size:0.82rem;">From
            <input type="date" id="detail-date-start" value="${firstDate}" style="margin-left:4px;font-size:0.82rem;padding:3px 6px;border:1px solid var(--line);border-radius:6px;" />
          </label>
          <label class="body-copy" style="font-size:0.82rem;">To
            <input type="date" id="detail-date-end" value="${lastDate}" style="margin-left:4px;font-size:0.82rem;padding:3px 6px;border:1px solid var(--line);border-radius:6px;" />
          </label>
          <button id="detail-date-apply" class="chart-dl-btn" style="font-size:0.78rem;">Apply</button>
        </div>
        <div id="details-table-mount">${tableHtml}</div>
        <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;">
          <button class="chart-dl-btn" id="dl-csv">Download CSV</button>
          <button class="chart-dl-btn" id="dl-forecast">Download Forecast CSV</button>
          <button class="chart-dl-btn" id="dl-all-types">Download All Tax Types</button>
        </div>
      </div>
    `;

    /* Sort handlers */
    attachSortHandlers(container, records);

    /* Date range filter */
    const applyBtn = container.querySelector<HTMLButtonElement>("#detail-date-apply");
    if (applyBtn) {
      applyBtn.addEventListener("click", async () => {
        const startInput = container.querySelector<HTMLInputElement>("#detail-date-start");
        const endInput = container.querySelector<HTMLInputElement>("#detail-date-end");
        const start = startInput?.value || undefined;
        const end = endInput?.value || undefined;
        showLoading(container);
        try {
          const filtered = await getCityLedger(currentCopo, currentTaxType, start, end);
          allRecords = filtered.records;
          renderContent(container, allRecords);
        } catch {
          container.innerHTML =
            '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load filtered data.</p>';
        }
      });
    }

    /* Download CSV */
    const dlCsv = container.querySelector<HTMLButtonElement>("#dl-csv");
    if (dlCsv) {
      dlCsv.addEventListener("click", () => {
        downloadLedgerCsv(records, `${cityName}-${currentTaxType}-ledger.csv`);
      });
    }

    /* Download Forecast CSV */
    const dlForecast = container.querySelector<HTMLButtonElement>("#dl-forecast");
    if (dlForecast) {
      dlForecast.addEventListener("click", async () => {
        dlForecast.textContent = "Loading...";
        dlForecast.disabled = true;
        try {
          const forecast = await getCityForecast(currentCopo, currentTaxType);
          const header = [
            "target_date",
            "projected_value",
            "lower_bound",
            "upper_bound",
          ].join(",");
          const rows = forecast.forecasts.map((f) =>
            [f.target_date, f.projected_value, f.lower_bound, f.upper_bound].join(","),
          );
          const csv = [header, ...rows].join("\n");
          const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
          triggerDownload(blob, `${cityName}-${currentTaxType}-forecast.csv`);
        } catch {
          /* silently fail */
        } finally {
          dlForecast.textContent = "Download Forecast CSV";
          dlForecast.disabled = false;
        }
      });
    }

    /* Download All Tax Types */
    const dlAll = container.querySelector<HTMLButtonElement>("#dl-all-types");
    if (dlAll) {
      dlAll.addEventListener("click", async () => {
        dlAll.textContent = "Loading...";
        dlAll.disabled = true;
        try {
          const types = ["sales", "use", "lodging"];
          const results = await Promise.all(
            types.map((t) => getCityLedger(currentCopo, t).catch(() => null)),
          );
          const merged: LedgerRecord[] = [];
          for (const r of results) {
            if (r) merged.push(...r.records);
          }
          merged.sort(
            (a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime(),
          );
          downloadLedgerCsv(merged, `${cityName}-all-types-ledger.csv`);
        } catch {
          /* silently fail */
        } finally {
          dlAll.textContent = "Download All Tax Types";
          dlAll.disabled = false;
        }
      });
    }
  }

  /* ---- Sort handler attachment ---- */

  function attachSortHandlers(container: HTMLElement, records: LedgerRecord[]): void {
    container.querySelectorAll<HTMLElement>(".sortable-th").forEach((th) => {
      th.addEventListener("click", () => {
        const col = th.dataset.col;
        if (!col) return;
        if (sortState.col === col) {
          sortState.dir = sortState.dir === "asc" ? "desc" : "asc";
        } else {
          sortState.col = col;
          sortState.dir = "desc";
        }
        const mount = container.querySelector<HTMLElement>("#details-table-mount");
        if (mount) {
          mount.innerHTML = buildLedgerTable(records);
          attachSortHandlers(container, records);
        }
      });
    });
  }

  return {
    async load(container, copo, taxType, detail) {
      currentCopo = copo;
      currentTaxType = taxType;
      currentDetail = detail;
      sortState = { col: "voucher_date", dir: "desc" };
      showLoading(container);

      try {
        const ledger = await getCityLedger(copo, taxType);
        allRecords = ledger.records;
        renderContent(container, allRecords);
      } catch {
        container.innerHTML =
          '<p class="body-copy" style="padding:20px;color:var(--danger);">Failed to load detail data.</p>';
      }
    },

    destroy() {
      allRecords = [];
      currentDetail = null;
    },
  };
}
