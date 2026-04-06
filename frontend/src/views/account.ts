import {
    deleteSavedAnomaly,
    deleteSavedMissedFiling,
    getAccountInterests,
    getAccountProfile,
    getForecastPreferences,
    getSavedAnomalies,
    getSavedMissedFilings,
    searchCities,
    searchNaicsCodes,
    updateAccountInterests,
    updateAccountProfile,
    updateForecastPreferences,
    updateSavedAnomaly,
    updateSavedMissedFiling,
} from "../api";
import { ensureSignedIn } from "../auth";
import { accountPath } from "../paths";
import { setPageMetadata } from "../seo";
import type {
    AccountProfile,
    CityListItem,
    ForecastPreferences,
    JurisdictionInterest,
    NaicsCodeLookupItem,
    SavedAnomaly,
    SavedMissedFiling,
    View,
} from "../types";
import { escapeHtml, formatCurrency } from "../utils";

interface AccountState {
  profile: AccountProfile | null;
  preferences: ForecastPreferences | null;
  interests: JurisdictionInterest[];
  anomalies: SavedAnomaly[];
  missedFilings: SavedMissedFiling[];
  cityOptions: CityListItem[];
  countyOptions: CityListItem[];
  naicsOptions: NaicsCodeLookupItem[];
}

const state: AccountState = {
  profile: null,
  preferences: null,
  interests: [],
  anomalies: [],
  missedFilings: [],
  cityOptions: [],
  countyOptions: [],
  naicsOptions: [],
};

const FORECAST_MODEL_OPTIONS = [
  { value: "auto", label: "Auto" },
  { value: "baseline", label: "Baseline" },
  { value: "sarima", label: "SARIMA" },
  { value: "prophet", label: "Prophet" },
  { value: "ensemble", label: "Ensemble" },
];

const TAX_TYPE_OPTIONS = [
  { value: "sales", label: "Sales tax" },
  { value: "use", label: "Use tax" },
  { value: "lodging", label: "Lodging tax" },
];

const HORIZON_OPTIONS = [6, 12, 18, 24];
const LOOKBACK_OPTIONS = [24, 36, 48];
const CONFIDENCE_OPTIONS = [0.8, 0.85, 0.9, 0.95, 0.99];
const DRIVER_PROFILE_OPTIONS = [
  { value: "off", label: "Off" },
  { value: "labor", label: "Labor" },
  { value: "retail_housing", label: "Retail + Housing" },
  { value: "balanced", label: "Balanced" },
];
const SCOPE_OPTIONS = [
  { value: "municipal", label: "Municipal total" },
  { value: "naics", label: "6-digit NAICS" },
];

function nullableText(value: FormDataEntryValue | null): string | null {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

function nullableNumber(value: FormDataEntryValue | null): number | null {
  const parsed = Number(String(value ?? "").trim());
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function cityInterestCsv(): string {
  return state.interests
    .filter((item) => item.interest_type === "city" && item.copo)
    .map((item) => item.copo)
    .join(", ");
}

function countyInterestCsv(): string {
  return state.interests
    .filter((item) => item.interest_type === "county" && item.county_name)
    .map((item) => item.county_name)
    .join(", ");
}

function optionMarkup(value: string | number, label: string, selectedValue: string | number | null | undefined): string {
  const selected = String(selectedValue ?? "") === String(value) ? "selected" : "";
  return `<option value="${escapeHtml(String(value))}" ${selected}>${escapeHtml(label)}</option>`;
}

function numericOptionsWithSelected(defaultValues: number[], selectedValue: number | null | undefined): number[] {
  const values = [...defaultValues];
  if (typeof selectedValue === "number" && Number.isFinite(selectedValue)) {
    const normalized = Number(selectedValue.toFixed(2));
    if (!values.some((value) => Math.abs(value - normalized) < 0.0001)) {
      values.push(normalized);
    }
  }
  return [...values].sort((a, b) => a - b);
}

function cityLookupLabel(copo: string | null | undefined): string {
  if (!copo) return "";
  const city = state.cityOptions.find((item) => item.copo === copo);
  if (!city) return copo;
  const countySuffix = city.county_name ? ` - ${city.county_name} County` : "";
  return `${city.name} (${city.copo})${countySuffix}`;
}

function naicsLookupLabel(activityCode: string | null | undefined): string {
  if (!activityCode) return "";
  const naics = state.naicsOptions.find((item) => item.activity_code === activityCode);
  if (!naics) return activityCode;
  return `${naics.activity_code} - ${naics.description}`;
}

function parseCopoLookup(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const exactCode = normalized.match(/^(\d{4})$/);
  if (exactCode) return exactCode[1];
  const labeledCode = normalized.match(/\((\d{4})\)/);
  return labeledCode ? labeledCode[1] : null;
}

function parseNaicsLookup(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const exactCode = normalized.match(/^(\d{2,6})$/);
  if (exactCode) return exactCode[1];
  const labeledCode = normalized.match(/^(\d{2,6})\s*[-–]/);
  return labeledCode ? labeledCode[1] : null;
}

async function loadAllJurisdictionOptions(type: "city" | "county"): Promise<CityListItem[]> {
  const items: CityListItem[] = [];
  let offset = 0;
  const limit = 500;
  while (true) {
    const response = await searchCities("", type, limit, offset);
    items.push(...response.items);
    offset += response.items.length;
    if (items.length >= response.total || response.items.length === 0) {
      return items;
    }
  }
}

async function loadAllNaicsOptions(): Promise<NaicsCodeLookupItem[]> {
  const items: NaicsCodeLookupItem[] = [];
  let offset = 0;
  const limit = 500;
  while (true) {
    const response = await searchNaicsCodes("", limit, offset);
    items.push(...response.items);
    offset += response.items.length;
    if (items.length >= response.total || response.items.length === 0) {
      return items;
    }
  }
}

function renderAccount(container: HTMLElement): void {
  const profile = state.profile;
  const preferences = state.preferences ?? {};
  const confidenceOptions = numericOptionsWithSelected(
    CONFIDENCE_OPTIONS,
    typeof preferences.forecast_confidence_level === "number" ? preferences.forecast_confidence_level : null,
  );

  if (!profile) {
    container.innerHTML = `
      <div class="panel" style="padding:24px;">
        <p class="body-copy">Unable to load your account right now.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="panel" style="padding:30px;">
      <div class="section-heading">
        <p class="eyebrow">Account</p>
        <h2>Your profile</h2>
      </div>
      <p class="body-copy" style="margin-bottom:18px;">
        Signed in as <strong>${escapeHtml(profile.email)}</strong>.
      </p>

      <form id="account-profile-form" style="display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));">
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Display name</span>
          <input name="display_name" value="${escapeHtml(profile.display_name ?? "")}"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Job title</span>
          <input name="job_title" value="${escapeHtml(profile.job_title ?? "")}"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Organization</span>
          <input name="organization_name" value="${escapeHtml(profile.organization_name ?? "")}"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
        </label>
        <label style="display:flex;align-items:center;gap:8px;margin-top:24px;">
          <input name="marketing_opt_in" type="checkbox" ${profile.marketing_opt_in ? "checked" : ""} />
          <span class="body-copy" style="font-size:0.85rem;">Email me product updates</span>
        </label>
        <label style="display:flex;align-items:center;gap:8px;">
          <input name="monthly_reports_opt_in" type="checkbox" ${profile.monthly_reports_opt_in ? "checked" : ""} />
          <span class="body-copy" style="font-size:0.85rem;">Send me monthly revenue reports for my connected jurisdictions</span>
        </label>
        <div style="grid-column:1 / -1;display:flex;gap:12px;align-items:center;">
          <button type="submit" class="button" style="min-height:40px;padding:0 16px;">Save profile</button>
          <span id="account-profile-message" class="body-copy" style="font-size:0.82rem;color:#5c6578;"></span>
        </div>
      </form>
    </div>

    <div class="panel" style="padding:30px;margin-top:20px;">
      <div class="block-header" style="margin-bottom:12px;">
        <p class="eyebrow">Interests</p>
        <h3>Connected jurisdictions</h3>
        <p class="body-copy" style="margin-top:4px;font-size:0.85rem;color:#5c6578;">Cities and counties you follow. Monthly revenue reports are emailed for connected cities when new data is published.</p>
      </div>
      <form id="account-interests-form" style="display:grid;gap:14px;">
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">City COPO codes</span>
          <input name="city_interest_codes" value="${escapeHtml(cityInterestCsv())}" placeholder="0955, 5521"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">County names</span>
          <input name="county_interest_names" value="${escapeHtml(countyInterestCsv())}" placeholder="Canadian, Oklahoma"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
        </label>
        <div style="display:flex;gap:12px;align-items:center;">
          <button type="submit" class="button button-ghost" style="min-height:40px;padding:0 16px;">Save interests</button>
          <span id="account-interests-message" class="body-copy" style="font-size:0.82rem;color:#5c6578;"></span>
        </div>
      </form>
    </div>

    <div class="panel" style="padding:30px;margin-top:20px;">
      <div class="block-header" style="margin-bottom:12px;">
        <p class="eyebrow">Forecasts</p>
        <h3>Default forecast settings</h3>
      </div>
      <form id="forecast-preferences-form" style="display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));">
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Default city</span>
          <input name="default_city_copo_lookup" list="forecast-city-options" value="${escapeHtml(cityLookupLabel(preferences.default_city_copo))}"
            placeholder="Search city name or code"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
          <datalist id="forecast-city-options">
            ${state.cityOptions.map((item) => `<option value="${escapeHtml(cityLookupLabel(item.copo))}"></option>`).join("")}
          </datalist>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Default county</span>
          <input name="default_county_name" list="forecast-county-options" value="${escapeHtml(preferences.default_county_name ?? "")}"
            placeholder="Search county"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
          <datalist id="forecast-county-options">
            ${state.countyOptions.map((item) => `<option value="${escapeHtml(item.name)}"></option>`).join("")}
          </datalist>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Tax type</span>
          <select name="default_tax_type" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${TAX_TYPE_OPTIONS.map((item) => optionMarkup(item.value, item.label, preferences.default_tax_type ?? "sales")).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Forecast model</span>
          <select name="forecast_model" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${FORECAST_MODEL_OPTIONS.map((item) => optionMarkup(item.value, item.label, preferences.forecast_model ?? "auto")).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Horizon months</span>
          <select name="forecast_horizon_months" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${HORIZON_OPTIONS.map((value) => optionMarkup(value, `${value} months`, preferences.forecast_horizon_months ?? 12)).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Lookback months</span>
          <select name="forecast_lookback_months" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${LOOKBACK_OPTIONS.map((value) => optionMarkup(value, `${value} months`, preferences.forecast_lookback_months ?? 36)).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Confidence</span>
          <select name="forecast_confidence_level" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${confidenceOptions.map((value) => optionMarkup(value, `${Math.round(value * 100)}%`, preferences.forecast_confidence_level ?? 0.95)).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Driver profile</span>
          <select name="forecast_indicator_profile" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${DRIVER_PROFILE_OPTIONS.map((item) => optionMarkup(item.value, item.label, preferences.forecast_indicator_profile ?? "balanced")).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Scope</span>
          <select name="forecast_scope" style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;background:#fff;">
            ${SCOPE_OPTIONS.map((item) => optionMarkup(item.value, item.label, preferences.forecast_scope ?? "municipal")).join("")}
          </select>
        </label>
        <label style="display:grid;gap:6px;">
          <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Activity code</span>
          <input name="forecast_activity_code_lookup" list="forecast-activity-options" value="${escapeHtml(naicsLookupLabel(preferences.forecast_activity_code))}"
            placeholder="Search 6-digit NAICS"
            style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.92rem;" />
          <datalist id="forecast-activity-options">
            ${state.naicsOptions.map((item) => `<option value="${escapeHtml(naicsLookupLabel(item.activity_code))}"></option>`).join("")}
          </datalist>
        </label>
        <div style="grid-column:1 / -1;display:flex;gap:12px;align-items:center;">
          <button type="submit" class="button button-ghost" style="min-height:40px;padding:0 16px;">Save defaults</button>
          <span id="forecast-preferences-message" class="body-copy" style="font-size:0.82rem;color:#5c6578;"></span>
        </div>
      </form>
    </div>

    <div class="panel" style="padding:30px;margin-top:20px;">
      <div class="block-header" style="margin-bottom:12px;">
        <p class="eyebrow">Anomalies</p>
        <h3>Saved follow-ups</h3>
      </div>
      <div id="account-saved-anomalies">
        ${state.anomalies.length
          ? state.anomalies.map((item) => `
            <article class="panel" style="padding:16px 18px;margin-bottom:10px;border:1px solid var(--line);">
              <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                <strong>${escapeHtml(item.city_name ?? item.copo)}</strong>
                <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">${escapeHtml(item.anomaly_type)} · ${escapeHtml(item.anomaly_date)}</span>
                <span class="body-copy" style="font-size:0.82rem;color:#5c6578;margin-left:auto;">${escapeHtml(item.status)}</span>
              </div>
              <label style="display:grid;gap:6px;margin:12px 0;">
                <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Note</span>
                <textarea class="saved-anomaly-note" data-id="${item.saved_anomaly_id}" rows="2"
                  style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.9rem;resize:vertical;">${escapeHtml(item.note ?? "")}</textarea>
              </label>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                <button class="button button-ghost saved-anomaly-status" data-id="${item.saved_anomaly_id}" data-status="investigating" style="min-height:34px;padding:0 12px;">Mark investigating</button>
                <button class="button button-ghost saved-anomaly-status" data-id="${item.saved_anomaly_id}" data-status="resolved" style="min-height:34px;padding:0 12px;">Mark resolved</button>
                <button class="button button-ghost saved-anomaly-note-save" data-id="${item.saved_anomaly_id}" style="min-height:34px;padding:0 12px;">Save note</button>
                <button class="button button-ghost saved-anomaly-delete" data-id="${item.saved_anomaly_id}" style="min-height:34px;padding:0 12px;">Remove</button>
              </div>
            </article>
          `).join("")
          : '<p class="body-copy">No saved anomaly follow-ups yet.</p>'}
      </div>
    </div>

    <div class="panel" style="padding:30px;margin-top:20px;">
      <div class="block-header" style="margin-bottom:12px;">
        <p class="eyebrow">Missed Filings</p>
        <h3>Saved follow-ups</h3>
      </div>
      <div id="account-saved-missed-filings">
        ${state.missedFilings.length
          ? state.missedFilings.map((item) => `
            <article class="panel" style="padding:16px 18px;margin-bottom:10px;border:1px solid var(--line);">
              <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
                <strong>${escapeHtml(item.city_name ?? item.copo)}</strong>
                <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">NAICS ${escapeHtml(item.activity_code)} · ${escapeHtml(item.anomaly_date)}</span>
                <span class="body-copy" style="font-size:0.82rem;color:#5c6578;margin-left:auto;">${escapeHtml(item.status)}</span>
              </div>
              <p class="body-copy" style="margin:8px 0 12px;">
                Gap ${item.missing_amount === null ? "N/A" : formatCurrency(item.missing_amount)}
              </p>
              <label style="display:grid;gap:6px;margin:12px 0;">
                <span class="body-copy" style="font-size:0.82rem;color:#5c6578;">Note</span>
                <textarea class="saved-missed-filing-note" data-id="${item.saved_missed_filing_id}" rows="2"
                  style="padding:10px 12px;border:1px solid var(--line);border-radius:10px;font-size:0.9rem;resize:vertical;">${escapeHtml(item.note ?? "")}</textarea>
              </label>
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                <button class="button button-ghost saved-missed-filing-status" data-id="${item.saved_missed_filing_id}" data-status="investigating" style="min-height:34px;padding:0 12px;">Mark investigating</button>
                <button class="button button-ghost saved-missed-filing-status" data-id="${item.saved_missed_filing_id}" data-status="resolved" style="min-height:34px;padding:0 12px;">Mark resolved</button>
                <button class="button button-ghost saved-missed-filing-note-save" data-id="${item.saved_missed_filing_id}" style="min-height:34px;padding:0 12px;">Save note</button>
                <button class="button button-ghost saved-missed-filing-delete" data-id="${item.saved_missed_filing_id}" style="min-height:34px;padding:0 12px;">Remove</button>
              </div>
            </article>
          `).join("")
          : '<p class="body-copy">No saved missed-filing follow-ups yet.</p>'}
      </div>
    </div>
  `;

  const profileForm = container.querySelector<HTMLFormElement>("#account-profile-form");
  profileForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(profileForm);
    const profileMessage = container.querySelector<HTMLElement>("#account-profile-message");
    await updateAccountProfile({
      display_name: nullableText(formData.get("display_name")),
      job_title: nullableText(formData.get("job_title")),
      organization_name: nullableText(formData.get("organization_name")),
      marketing_opt_in: formData.get("marketing_opt_in") === "on",
      monthly_reports_opt_in: formData.get("monthly_reports_opt_in") === "on",
    });
    if (profileMessage) profileMessage.textContent = "Profile saved.";
    await loadAccount(container, true);
  });

  const interestsForm = container.querySelector<HTMLFormElement>("#account-interests-form");
  interestsForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(interestsForm);
    const cityCodes = String(formData.get("city_interest_codes") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    const counties = String(formData.get("county_interest_names") || "")
      .split(",")
      .map((value) => value.trim())
      .filter(Boolean);
    await updateAccountInterests({
      items: [
        ...cityCodes.map((copo) => ({ interest_type: "city", copo })),
        ...counties.map((county_name) => ({ interest_type: "county", county_name })),
      ],
    });
    const interestsMessage = container.querySelector<HTMLElement>("#account-interests-message");
    if (interestsMessage) interestsMessage.textContent = "Interests saved.";
    await loadAccount(container, true);
  });

  const preferencesForm = container.querySelector<HTMLFormElement>("#forecast-preferences-form");
  const taxTypeSelect = preferencesForm?.querySelector<HTMLSelectElement>("select[name='default_tax_type']");
  const scopeSelect = preferencesForm?.querySelector<HTMLSelectElement>("select[name='forecast_scope']");
  const activityLookup = preferencesForm?.querySelector<HTMLInputElement>("input[name='forecast_activity_code_lookup']");
  const syncForecastPreferenceControls = (): void => {
    if (!taxTypeSelect || !scopeSelect || !activityLookup) return;
    const lodgingMode = taxTypeSelect.value === "lodging";
    if (lodgingMode) {
      scopeSelect.value = "municipal";
    }
    scopeSelect.disabled = lodgingMode;
    activityLookup.disabled = lodgingMode || scopeSelect.value !== "naics";
  };
  taxTypeSelect?.addEventListener("change", syncForecastPreferenceControls);
  scopeSelect?.addEventListener("change", syncForecastPreferenceControls);
  syncForecastPreferenceControls();
  preferencesForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(preferencesForm);
    const normalizedTaxType = nullableText(formData.get("default_tax_type"));
    const requestedScope = nullableText(formData.get("forecast_scope"));
    const normalizedScope = normalizedTaxType === "lodging" ? "municipal" : requestedScope;
    await updateForecastPreferences({
      default_city_copo: parseCopoLookup(String(formData.get("default_city_copo_lookup") ?? "")),
      default_county_name: nullableText(formData.get("default_county_name")),
      default_tax_type: normalizedTaxType,
      forecast_model: nullableText(formData.get("forecast_model")),
      forecast_horizon_months: nullableNumber(formData.get("forecast_horizon_months")),
      forecast_lookback_months: nullableNumber(formData.get("forecast_lookback_months")),
      forecast_confidence_level: nullableNumber(formData.get("forecast_confidence_level")),
      forecast_indicator_profile: nullableText(formData.get("forecast_indicator_profile")),
      forecast_scope: normalizedScope,
      forecast_activity_code:
        normalizedScope === "naics"
          ? parseNaicsLookup(String(formData.get("forecast_activity_code_lookup") ?? ""))
          : null,
    });
    const preferencesMessage = container.querySelector<HTMLElement>("#forecast-preferences-message");
    if (preferencesMessage) preferencesMessage.textContent = "Forecast defaults saved.";
    await loadAccount(container, true);
  });

  container.querySelectorAll<HTMLButtonElement>(".saved-anomaly-status").forEach((button) => {
    button.addEventListener("click", async () => {
      const note = container.querySelector<HTMLTextAreaElement>(`.saved-anomaly-note[data-id="${button.dataset.id || ""}"]`)?.value.trim() || null;
      await updateSavedAnomaly(button.dataset.id || "", {
        status: button.dataset.status || "saved",
        note,
      });
      await loadAccount(container, true);
    });
  });
  container.querySelectorAll<HTMLButtonElement>(".saved-anomaly-note-save").forEach((button) => {
    button.addEventListener("click", async () => {
      const note = container.querySelector<HTMLTextAreaElement>(`.saved-anomaly-note[data-id="${button.dataset.id || ""}"]`)?.value.trim() || null;
      await updateSavedAnomaly(button.dataset.id || "", { note });
      await loadAccount(container, true);
    });
  });
  container.querySelectorAll<HTMLButtonElement>(".saved-anomaly-delete").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteSavedAnomaly(button.dataset.id || "");
      await loadAccount(container, true);
    });
  });
  container.querySelectorAll<HTMLButtonElement>(".saved-missed-filing-status").forEach((button) => {
    button.addEventListener("click", async () => {
      const note = container.querySelector<HTMLTextAreaElement>(`.saved-missed-filing-note[data-id="${button.dataset.id || ""}"]`)?.value.trim() || null;
      await updateSavedMissedFiling(button.dataset.id || "", {
        status: button.dataset.status || "saved",
        note,
      });
      await loadAccount(container, true);
    });
  });
  container.querySelectorAll<HTMLButtonElement>(".saved-missed-filing-note-save").forEach((button) => {
    button.addEventListener("click", async () => {
      const note = container.querySelector<HTMLTextAreaElement>(`.saved-missed-filing-note[data-id="${button.dataset.id || ""}"]`)?.value.trim() || null;
      await updateSavedMissedFiling(button.dataset.id || "", { note });
      await loadAccount(container, true);
    });
  });
  container.querySelectorAll<HTMLButtonElement>(".saved-missed-filing-delete").forEach((button) => {
    button.addEventListener("click", async () => {
      await deleteSavedMissedFiling(button.dataset.id || "");
      await loadAccount(container, true);
    });
  });
}

async function loadAccount(container: HTMLElement, rerender = false): Promise<void> {
  if (!(await ensureSignedIn(window.location.pathname + window.location.search))) {
    return;
  }
  if (!rerender) {
    container.innerHTML = `
      <div class="panel" style="padding:24px;">
        <p class="body-copy">Loading account…</p>
      </div>
    `;
  }
  try {
    const [profile, preferences, interests, anomalies, missedFilings, cityOptions, countyOptions, naicsOptions] = await Promise.all([
      getAccountProfile(),
      getForecastPreferences(),
      getAccountInterests(),
      getSavedAnomalies(),
      getSavedMissedFilings(),
      state.cityOptions.length ? Promise.resolve(state.cityOptions) : loadAllJurisdictionOptions("city"),
      state.countyOptions.length ? Promise.resolve(state.countyOptions) : loadAllJurisdictionOptions("county"),
      state.naicsOptions.length ? Promise.resolve(state.naicsOptions) : loadAllNaicsOptions(),
    ]);
    state.profile = profile;
    state.preferences = preferences;
    state.interests = interests.items;
    state.anomalies = anomalies.items;
    state.missedFilings = missedFilings.items;
    state.cityOptions = cityOptions;
    state.countyOptions = countyOptions;
    state.naicsOptions = naicsOptions;
    renderAccount(container);
  } catch (error) {
    container.innerHTML = `
      <div class="panel" style="padding:24px;">
        <p class="body-copy" style="color:var(--danger);">
          ${escapeHtml(error instanceof Error ? error.message : "Unable to load your account.")}
        </p>
      </div>
    `;
  }
}

export const accountView: View = {
  render(container: HTMLElement): void {
    setPageMetadata({
      title: "Your Account",
      description: "Manage your MuniRevenue profile, forecast defaults, and saved follow-ups.",
      path: accountPath(),
    });
    container.className = "view-account";
    void loadAccount(container);
  },

  destroy(): void {
    state.profile = null;
    state.preferences = null;
    state.interests = [];
    state.anomalies = [];
    state.missedFilings = [];
    state.cityOptions = [];
    state.countyOptions = [];
    state.naicsOptions = [];
  },
};
