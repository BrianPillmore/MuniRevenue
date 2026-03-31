/* ══════════════════════════════════════════════
   Export view -- Data export builder
   ══════════════════════════════════════════════ */

import { exportLedgerCsv, getCityLedger } from "../api";
import { renderCitySearch } from "../components/city-search";
import { navigateTo } from "../router";
import type { CityLedgerResponse, CityListItem, View } from "../types";
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
}

const state: ExportState = {
  copo: null,
  cityName: null,
  activeTaxType: "sales",
  startDate: "",
  endDate: "",
  preview: null,
  searchCleanup: null,
};

/* ── Preview rendering ── */

function renderPreview(): void {
  const container = document.querySelector<HTMLElement>("#export-preview");
  if (!container) return;

  if (!state.preview || !state.preview.records.length) {
    container.innerHTML =
      '<p class="body-copy" style="padding:16px;text-align:center;color:#5d6b75;">No records to preview. Select a city and adjust filters above.</p>';
    updateDownloadState();
    return;
  }

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
    <p class="body-copy" style="margin-bottom:8px;color:#5d6b75;">
      Showing first 10 of ${totalCount} records
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
    const ledger = await getCityLedger(
      state.copo,
      state.activeTaxType,
      state.startDate || undefined,
      state.endDate || undefined,
    );
    state.preview = ledger;
    renderPreview();
  } catch {
    if (container) {
      container.innerHTML =
        '<p class="body-copy" style="padding:16px;color:var(--brand)">Failed to load preview data.</p>';
    }
    updateDownloadState();
  }
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

function onDownload(): void {
  if (!state.copo) return;
  exportLedgerCsv(
    state.copo,
    state.activeTaxType,
    state.startDate || undefined,
    state.endDate || undefined,
  );
}

/* ── View implementation ── */

export const exportView: View = {
  render(container: HTMLElement, _params: Record<string, string>): void {
    container.className = "view-export";

    /* Reset state */
    state.copo = null;
    state.cityName = null;
    state.activeTaxType = "sales";
    state.startDate = "";
    state.endDate = "";
    state.preview = null;

    const taxTypes = ["sales", "use", "lodging"];
    const radioButtons = taxTypes
      .map((t) => {
        const label = t.charAt(0).toUpperCase() + t.slice(1);
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
        <p id="export-city-label" class="body-copy" style="color:#5d6b75;margin-bottom:0;"></p>
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
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>3. Date range (optional)</h3>
        </div>
        <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
          <label style="font-size:0.88rem;color:#5d6b75;">
            Start:
            <input
              type="date"
              id="export-start-date"
              style="margin-left:4px;padding:6px 10px;border:1px solid rgba(16,34,49,0.15);border-radius:6px;font-size:0.88rem;"
            />
          </label>
          <label style="font-size:0.88rem;color:#5d6b75;">
            End:
            <input
              type="date"
              id="export-end-date"
              style="margin-left:4px;padding:6px 10px;border:1px solid rgba(16,34,49,0.15);border-radius:6px;font-size:0.88rem;"
            />
          </label>
        </div>
      </div>

      <div class="panel" style="padding: 22px 30px;">
        <div class="block-header" style="margin-bottom:12px;">
          <h3>Preview</h3>
        </div>
        <div id="export-preview">
          <p class="body-copy" style="padding:16px;text-align:center;color:#5d6b75;">
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
            background:#1d6b70;color:#fff;border:none;border-radius:8px;
            cursor:pointer;opacity:0.5;
          "
        >
          Download CSV
        </button>
        <p class="body-copy" style="margin-top:8px;color:#5d6b75;font-size:0.82rem;">
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
  },
};
