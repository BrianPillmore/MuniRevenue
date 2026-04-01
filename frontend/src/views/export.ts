/* ══════════════════════════════════════════════
   Export view -- Data export builder
   ══════════════════════════════════════════════ */

import { exportLedgerCsv, getCityForecast, getCityLedger } from "../api";
import { renderCitySearch } from "../components/city-search";
import { ROUTES } from "../paths";
import { setPageMetadata } from "../seo";
import type {
  CityForecastPoint,
  CityLedgerResponse,
  CityListItem,
  ForecastResponse,
  LedgerRecord,
  View,
} from "../types";
import {
  escapeHtml,
  formatCurrency,
  wrapTable,
} from "../utils";

/* ── State ── */

interface ExportState {
  copo: string | null;
  cityName: string | null;
  activeTaxType: string;
  startDate: string;
  endDate: string;
  preview: CityLedgerResponse | null;
  searchCleanup: (() => void) | null;
  includeForecast: boolean;
}

const state: ExportState = {
  copo: null,
  cityName: null,
  activeTaxType: "sales",
  startDate: "",
  endDate: "",
  preview: null,
  searchCleanup: null,
  includeForecast: false,
};

/* ── Preview rendering ── */

function renderPreview(): void {
  const container = document.querySelector<HTMLElement>("#export-preview");
  if (!container) return;

  if (!state.preview || !state.preview.records.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:16px;text-align:center;color:#5c6578;">No records to preview. Select a city and adjust filters above.</p>';
    updateDownloadState();
    return;
  }

  const isAllTypes = state.activeTaxType === "all";

  /* Take first 10 rows for preview */
  const first10 = state.preview.records.slice(0, 10);
  const totalCount = state.preview.records.length;

  const rows = first10
    .map(
      (r) => `
        <tr>
          <td>${escapeHtml(r.voucher_date)}</td>
          <td>${escapeHtml(r.tax_type)}</td>
          <td style="text-align:right;">${formatCurrency(r.returned)}</td>
          <td style="text-align:right;">${formatCurrency(r.current_month_collection)}</td>
          <td style="text-align:right;">${formatCurrency(r.refunded)}</td>
          <td style="text-align:right;">${formatCurrency(r.apportioned)}</td>
        </tr>
      `,
    )
    .join("");

  container.innerHTML = `
    <p class="body-copy" style="margin-bottom:8px;color:#5c6578;">
      Showing first 10 of ${totalCount} records${isAllTypes ? " (all tax types combined)" : ""}
    </p>
    ${wrapTable(
      ["Voucher Date", "Tax Type", "Returned", "Collections", "Refunded", "Apportioned"],
      rows,
    )}
  `;

  updateDownloadState();
}

function updateDownloadState(): void {
  const btn = document.querySelector<HTMLButtonElement>("#export-download-btn");
  if (!btn) return;
  const hasData = state.copo !== null && state.preview !== null && state.preview.records.length > 0;
  btn.disabled = !hasData;
}

/* ── Data loading ── */

async function loadPreview(): Promise<void> {
  if (!state.copo) return;

  const container = document.querySelector<HTMLElement>("#export-preview");
  if (container) {
    container.innerHTML =
      '<p class="body-copy" style="padding:16px;text-align:center;">Loading preview...</p>';
  }

  try {
    let ledger: CityLedgerResponse;

    if (state.activeTaxType === "all") {
      /* Fetch all 3 tax types and merge */
      const [salesLedger, useLedger, lodgingLedger] = await Promise.all([
        getCityLedger(state.copo, "sales", state.startDate || undefined, state.endDate || undefined),
        getCityLedger(state.copo, "use", state.startDate || undefined, state.endDate || undefined),
        getCityLedger(state.copo, "lodging", state.startDate || undefined, state.endDate || undefined),
      ]);

      /* Merge all records and sort by date */
      const allRecords = [
        ...salesLedger.records,
        ...useLedger.records,
        ...lodgingLedger.records,
      ].sort((a, b) => new Date(a.voucher_date).getTime() - new Date(b.voucher_date).getTime());

      ledger = {
        copo: salesLedger.copo,
        tax_type: "all",
        records: allRecords,
        count: allRecords.length,
      };
    } else {
      ledger = await getCityLedger(
        state.copo,
        state.activeTaxType,
        state.startDate || undefined,
        state.endDate || undefined,
      );
    }

    state.preview = ledger;
    renderPreview();
  } catch {
    if (container) {
      container.innerHTML =
        '<p class="body-copy" style="padding:16px;color:var(--danger)">Failed to load preview data.</p>';
    }
    updateDownloadState();
  }
}

/* ── CSV generation helpers ── */

function escapeCsvField(value: string): string {
  if (value.includes(",") || value.includes('"') || value.includes("\n")) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}

function buildCsvContent(
  records: LedgerRecord[],
  forecastRecords: Array<{
    target_date: string;
    tax_type: string;
    projected_value: number;
    lower_bound: number;
    upper_bound: number;
  }>,
): string {
  const headers = [
    "voucher_date",
    "tax_type",
    "returned",
    "current_month_collection",
    "refunded",
    "suspended_monies",
    "apportioned",
    "revolving_fund",
    "interest_returned",
    "tax_rate",
    "mom_pct",
    "yoy_pct",
    "record_type",
  ];

  const lines: string[] = [headers.join(",")];

  /* Actual records */
  for (const r of records) {
    lines.push([
      escapeCsvField(r.voucher_date),
      escapeCsvField(r.tax_type),
      String(r.returned),
      String(r.current_month_collection),
      String(r.refunded),
      String(r.suspended_monies),
      String(r.apportioned),
      String(r.revolving_fund),
      String(r.interest_returned),
      String(r.tax_rate),
      r.mom_pct !== null ? String(r.mom_pct) : "",
      r.yoy_pct !== null ? String(r.yoy_pct) : "",
      "actual",
    ].join(","));
  }

  /* Forecast records */
  for (const f of forecastRecords) {
    lines.push([
      escapeCsvField(f.target_date),
      escapeCsvField(f.tax_type),
      String(f.projected_value),
      "", /* current_month_collection */
      "", /* refunded */
      "", /* suspended_monies */
      "", /* apportioned */
      "", /* revolving_fund */
      "", /* interest_returned */
      "", /* tax_rate */
      "", /* mom_pct */
      "", /* yoy_pct */
      "forecast",
    ].join(","));
  }

  return lines.join("\n");
}

function triggerCsvDownload(csv: string, filename: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}

/* ── Event handlers ── */

function onCitySelected(city: CityListItem): void {
  state.copo = city.copo;
  state.cityName = city.name;

  /* Update the selected city label */
  const label = document.querySelector<HTMLElement>("#export-city-label");
  if (label) {
    label.innerHTML = `Selected: <strong>${escapeHtml(city.name)}</strong> (${escapeHtml(city.copo)})`;
  }

  loadPreview();
}

function onTaxTypeChange(taxType: string): void {
  state.activeTaxType = taxType;

  /* Update radio button visuals */
  document.querySelectorAll<HTMLInputElement>('input[name="export-tax-type"]').forEach((radio) => {
    radio.checked = radio.value === taxType;
  });

  if (state.copo) loadPreview();
}

function onDateChange(): void {
  const startInput = document.querySelector<HTMLInputElement>("#export-start-date");
  const endInput = document.querySelector<HTMLInputElement>("#export-end-date");

  state.startDate = startInput?.value ?? "";
  state.endDate = endInput?.value ?? "";

  if (state.copo) loadPreview();
}

function onForecastToggle(): void {
  const checkbox = document.querySelector<HTMLInputElement>("#export-include-forecast");
  state.includeForecast = checkbox?.checked ?? false;
}

async function onDownload(): Promise<void> {
  if (!state.copo || !state.preview) return;

  const btn = document.querySelector<HTMLButtonElement>("#export-download-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Preparing download...";
  }

  try {
    const isAll = state.activeTaxType === "all";
    const taxTypes = isAll ? ["sales", "use", "lodging"] : [state.activeTaxType];

    /* If "Include forecast" is not checked and it is a single tax type, use the
       server-side CSV export for a simpler/faster path */
    if (!state.includeForecast && !isAll) {
      exportLedgerCsv(
        state.copo,
        state.activeTaxType,
        state.startDate || undefined,
        state.endDate || undefined,
      );
      return;
    }

    /* Build CSV client-side for "All" types or forecast inclusion */
    let allRecords: LedgerRecord[] = [];

    if (isAll) {
      /* state.preview already has merged records from loadPreview() */
      allRecords = state.preview.records;
    } else {
      allRecords = state.preview.records;
    }

    /* Fetch forecast data if enabled */
    let forecastRows: Array<{
      target_date: string;
      tax_type: string;
      projected_value: number;
      lower_bound: number;
      upper_bound: number;
    }> = [];

    if (state.includeForecast) {
      const forecastPromises = taxTypes.map(async (tt) => {
        try {
          const forecast = await getCityForecast(state.copo!, tt);
          return forecast.forecasts.map((f) => ({
            target_date: f.target_date,
            tax_type: tt,
            projected_value: f.projected_value,
            lower_bound: f.lower_bound,
            upper_bound: f.upper_bound,
          }));
        } catch {
          return [];
        }
      });

      const results = await Promise.all(forecastPromises);
      forecastRows = results.flat().sort(
        (a, b) => new Date(a.target_date).getTime() - new Date(b.target_date).getTime(),
      );
    }

    const csv = buildCsvContent(allRecords, forecastRows);
    const taxSuffix = isAll ? "all" : state.activeTaxType;
    const forecastSuffix = state.includeForecast ? "-with-forecast" : "";
    const filename = `ledger-${state.copo}-${taxSuffix}${forecastSuffix}.csv`;
    triggerCsvDownload(csv, filename);
  } catch {
    /* Silently fail -- the button will re-enable below */
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Download CSV";
    }
    updateDownloadState();
  }
}

/* ── View implementation ── */

export const exportView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    setPageMetadata({
      title: "Municipal Revenue Data Export",
      description:
        "Build custom exports of Oklahoma municipal revenue records and forecast data by city, tax type, and date range.",
      path: ROUTES.export,
      robots: "noindex,follow",
    });
    container.className = "view-export";

    /* Reset state */
    state.copo = null;
    state.cityName = null;
    state.activeTaxType = "sales";
    state.startDate = "";
    state.endDate = "";
    state.preview = null;
    state.includeForecast = false;

    const taxTypes = ["sales", "use", "lodging", "all"];
    const radioButtons = taxTypes
      .map((t) => {
        const label = t === "all" ? "All (combined)" : t.charAt(0).toUpperCase() + t.slice(1);
        const checked = t === "sales" ? "checked" : "";
        return `
          <label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-size:0.92rem;">
            <input type="radio" name="export-tax-type" value="${t}" ${checked} />
            ${label}
          </label>
        `;
      })
      .join("");

    container.innerHTML = `
      <div class="panel" style="padding: 30px 30px 14px;">
        <div class="section-heading">
          <p class="eyebrow">Tools</p>
          <h2>Data Export</h2>
        </div>
        <p class="body-copy" style="margin-bottom:16px;">
          Build a custom data export by selecting a city, tax type, and date range. Preview the data below before downloading.
        </p>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>1. Select a city</h3>
        </div>
        <div id="export-search-mount" style="max-width:400px;margin-bottom:8px;"></div>
        <p id="export-city-label" class="body-copy" style="color:#5c6578;margin-bottom:0;"></p>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>2. Tax type</h3>
        </div>
        <div
          class="export-tax-radios"
          role="radiogroup"
          aria-label="Tax type"
          style="display:flex;gap:20px;flex-wrap:wrap;"
        >
          ${radioButtons}
        </div>
        <p class="body-copy" style="margin-top:8px;color:#5c6578;font-size:0.82rem;">
          Select "All (combined)" to export sales, use, and lodging data in one CSV with a tax_type column.
        </p>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>3. Date range (optional)</h3>
        </div>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          <label style="font-size:0.88rem;color:#5c6578;">
            Start:
            <input
              type="date"
              id="export-start-date"
              style="margin-left:4px;padding:6px 10px;border:1px solid rgba(26,31,43,0.12);border-radius:6px;font-size:0.88rem;"
            />
          </label>
          <label style="font-size:0.88rem;color:#5c6578;">
            End:
            <input
              type="date"
              id="export-end-date"
              style="margin-left:4px;padding:6px 10px;border:1px solid rgba(26,31,43,0.12);border-radius:6px;font-size:0.88rem;"
            />
          </label>
        </div>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>4. Options</h3>
        </div>
        <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-size:0.92rem;">
          <input type="checkbox" id="export-include-forecast" />
          <span>Include 12-month forecast</span>
        </label>
        <p class="body-copy" style="margin-top:6px;color:#5c6578;font-size:0.82rem;">
          Appends projected revenue rows to the CSV. Each row is marked as "forecast" vs "actual" in the record_type column.
        </p>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>Preview</h3>
        </div>
        <div id="export-preview">
          <p class="body-copy" style="padding:16px;text-align:center;color:#5c6578;">
            Select a city above to preview data.
          </p>
        </div>
      </div>

      <div class="panel" style="padding: 22px 30px;text-align:center;">
        <button
          id="export-download-btn"
          class="btn btn-primary"
          disabled
          style="
            padding:10px 28px;font-size:0.95rem;
            background:#1b3a5c;color:#fff;border:none;border-radius:8px;
            cursor:pointer;opacity:0.5;
          "
        >
          Download CSV
        </button>
        <p class="body-copy" style="margin-top:8px;color:#5c6578;font-size:0.82rem;">
          Exports all records matching the selected filters as a CSV file.
        </p>
      </div>
    `;

    /* City search */
    const searchMount = container.querySelector<HTMLElement>("#export-search-mount")!;
    state.searchCleanup = renderCitySearch(searchMount, {
      onSelect: onCitySelected,
      placeholder: "Search for a city to export...",
    });

    /* Tax type radio handlers */
    container.querySelectorAll<HTMLInputElement>('input[name="export-tax-type"]').forEach((radio) => {
      radio.addEventListener("change", () => {
        if (radio.checked) onTaxTypeChange(radio.value);
      });
    });

    /* Forecast checkbox handler */
    const forecastCheckbox = document.querySelector<HTMLInputElement>("#export-include-forecast");
    if (forecastCheckbox) {
      forecastCheckbox.addEventListener("change", onForecastToggle);
    }

    /* Date change handlers (debounced) */
    let dateTimeout: ReturnType<typeof setTimeout> | null = null;
    const handleDateChange = () => {
      if (dateTimeout) clearTimeout(dateTimeout);
      dateTimeout = setTimeout(onDateChange, 400);
    };

    document.querySelector<HTMLInputElement>("#export-start-date")
      ?.addEventListener("change", handleDateChange);
    document.querySelector<HTMLInputElement>("#export-end-date")
      ?.addEventListener("change", handleDateChange);

    /* Download button */
    const downloadBtn = document.querySelector<HTMLButtonElement>("#export-download-btn");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", onDownload);

      /* Style the button when enabled/disabled */
      const observer = new MutationObserver(() => {
        downloadBtn.style.opacity = downloadBtn.disabled ? "0.5" : "1";
      });
      observer.observe(downloadBtn, { attributes: true, attributeFilter: ["disabled"] });
    }
  },

  destroy(): void {
    if (state.searchCleanup) {
      state.searchCleanup();
      state.searchCleanup = null;
    }
    state.copo = null;
    state.cityName = null;
    state.activeTaxType = "sales";
    state.startDate = "";
    state.endDate = "";
    state.preview = null;
    state.includeForecast = false;
  },
};
