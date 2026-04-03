// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const deleteSavedAnomaly = vi.fn();
const deleteSavedMissedFiling = vi.fn();
const getAccountInterests = vi.fn();
const getAccountProfile = vi.fn();
const getForecastPreferences = vi.fn();
const getSavedAnomalies = vi.fn();
const getSavedMissedFilings = vi.fn();
const searchCities = vi.fn();
const searchNaicsCodes = vi.fn();
const updateAccountInterests = vi.fn();
const updateAccountProfile = vi.fn();
const updateForecastPreferences = vi.fn();
const updateSavedAnomaly = vi.fn();
const updateSavedMissedFiling = vi.fn();
const ensureSignedIn = vi.fn();
const setPageMetadata = vi.fn();

vi.mock("../api", () => ({
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
}));

vi.mock("../auth", () => ({
  ensureSignedIn,
}));

vi.mock("../seo", () => ({
  setPageMetadata,
}));

const initialProfile = {
  user_id: "user-1",
  email: "clerk@example.com",
  display_name: "Clerk Example",
  job_title: "Finance Director",
  organization_name: "City of Example",
  marketing_opt_in: true,
};

const updatedProfile = {
  ...initialProfile,
  display_name: "Updated Clerk",
  marketing_opt_in: false,
};

const initialPreferences = {
  default_city_copo: "0955",
  default_county_name: "Oklahoma",
  default_tax_type: "sales",
  forecast_model: "ensemble",
  forecast_horizon_months: 12,
  forecast_lookback_months: 24,
  forecast_confidence_level: 0.85,
  forecast_indicator_profile: "balanced",
  forecast_scope: "naics",
  forecast_activity_code: "722511",
};

const updatedPreferences = {
  ...initialPreferences,
  default_city_copo: "5521",
};

const baseInterests = {
  items: [
    {
      interest_id: "interest-city-1",
      interest_type: "city",
      copo: "0955",
      county_name: null,
      label: "Norman",
    },
    {
      interest_id: "interest-county-1",
      interest_type: "county",
      copo: null,
      county_name: "Oklahoma",
      label: "Oklahoma",
    },
  ],
};

const savedAnomalies = {
  items: [
    {
      saved_anomaly_id: "anomaly-1",
      copo: "0955",
      tax_type: "sales",
      anomaly_date: "2026-02-01",
      anomaly_type: "drop",
      activity_code: "722511",
      status: "saved",
      note: "Call clerk",
      city_name: "Norman",
    },
  ],
};

const savedMissedFilings = {
  items: [
    {
      saved_missed_filing_id: "missed-1",
      copo: "0955",
      tax_type: "sales",
      anomaly_date: "2026-02-01",
      activity_code: "722511",
      baseline_method: "hybrid",
      expected_value: 125000,
      actual_value: 100000,
      missing_amount: 25000,
      missing_pct: 20,
      status: "saved",
      note: "Investigate restaurant group",
      city_name: "Norman",
    },
  ],
};

function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function renderAccountView() {
  const { accountView } = await import("./account");
  const container = document.createElement("div");
  document.body.appendChild(container);
  accountView.render(container, {});
  await flush();
  return { accountView, container };
}

describe("accountView", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    ensureSignedIn.mockResolvedValue(true);
    getAccountProfile.mockResolvedValue(initialProfile);
    getForecastPreferences.mockResolvedValue(initialPreferences);
    getAccountInterests.mockResolvedValue(baseInterests);
    getSavedAnomalies.mockResolvedValue(savedAnomalies);
    getSavedMissedFilings.mockResolvedValue(savedMissedFilings);
    searchCities.mockImplementation(async (query: string, type?: string, _limit?: number, offset?: number) => {
      if (type === "county") {
        return {
          items: [
            { copo: "9100", name: "Canadian", jurisdiction_type: "county", county_name: null, population: 0, has_ledger_data: true, latest_voucher_date: null, total_sales_returned: null },
            { copo: "9150", name: "Oklahoma", jurisdiction_type: "county", county_name: null, population: 0, has_ledger_data: true, latest_voucher_date: null, total_sales_returned: null },
          ],
          total: 2,
          limit: 500,
          offset: offset ?? 0,
        };
      }
      return {
        items: offset && offset > 0
          ? []
          : [
              { copo: "0955", name: "Norman", jurisdiction_type: "city", county_name: "Cleveland", population: 128026, has_ledger_data: true, latest_voucher_date: null, total_sales_returned: null },
              { copo: "5521", name: "Yukon", jurisdiction_type: "city", county_name: "Canadian", population: 0, has_ledger_data: true, latest_voucher_date: null, total_sales_returned: null },
            ],
        total: 2,
        limit: 500,
        offset: offset ?? 0,
      };
    });
    searchNaicsCodes.mockResolvedValue({
      items: [
        { activity_code: "722511", description: "Full-Service Restaurants", sector: "72", sector_description: "Accommodation and Food Services" },
      ],
      total: 1,
      limit: 500,
      offset: 0,
    });
    updateAccountProfile.mockResolvedValue(updatedProfile);
    updateAccountInterests.mockResolvedValue(baseInterests);
    updateForecastPreferences.mockResolvedValue(updatedPreferences);
    updateSavedAnomaly.mockResolvedValue(savedAnomalies);
    deleteSavedAnomaly.mockResolvedValue(savedAnomalies);
    updateSavedMissedFiling.mockResolvedValue(savedMissedFilings);
    deleteSavedMissedFiling.mockResolvedValue(savedMissedFilings);
  });

  it("renders the account profile, forecast defaults, and saved follow-up sections", async () => {
    const { container } = await renderAccountView();

    expect(setPageMetadata).toHaveBeenCalledWith({
      title: "Your Account",
      description: "Manage your MuniRevenue profile, forecast defaults, and saved follow-ups.",
      path: "/account",
    });
    expect(container.textContent).toContain("Signed in as clerk@example.com.");
    expect(container.textContent).toContain("Connected jurisdictions");
    expect(container.textContent).toContain("Default forecast settings");
    expect(container.textContent).toContain("Call clerk");
    expect(container.textContent).toContain("Investigate restaurant group");

    expect((container.querySelector<HTMLInputElement>("input[name='display_name']")?.value)).toBe("Clerk Example");
    expect((container.querySelector<HTMLInputElement>("input[name='city_interest_codes']")?.value)).toBe("0955");
    expect((container.querySelector<HTMLInputElement>("input[name='county_interest_names']")?.value)).toBe("Oklahoma");
    expect((container.querySelector<HTMLInputElement>("input[name='default_city_copo_lookup']")?.value)).toContain("0955");
  });

  it("submits profile updates and refreshes the rendered data", async () => {
    getAccountProfile
      .mockResolvedValueOnce(initialProfile)
      .mockResolvedValueOnce(updatedProfile);

    const { container } = await renderAccountView();

    const form = container.querySelector<HTMLFormElement>("#account-profile-form");
    const displayName = container.querySelector<HTMLInputElement>("input[name='display_name']");
    const jobTitle = container.querySelector<HTMLInputElement>("input[name='job_title']");
    const organization = container.querySelector<HTMLInputElement>("input[name='organization_name']");
    const marketingOptIn = container.querySelector<HTMLInputElement>("input[name='marketing_opt_in']");

    if (!form || !displayName || !jobTitle || !organization || !marketingOptIn) {
      throw new Error("Expected account profile form fields to exist.");
    }

    displayName.value = "Updated Clerk";
    jobTitle.value = "Deputy Finance Director";
    organization.value = "City of Updated Example";
    marketingOptIn.checked = false;

    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flush();

    expect(updateAccountProfile).toHaveBeenCalledWith({
      display_name: "Updated Clerk",
      job_title: "Deputy Finance Director",
      organization_name: "City of Updated Example",
      marketing_opt_in: false,
    });
    expect(getAccountProfile).toHaveBeenCalledTimes(2);
    expect(container.querySelector<HTMLInputElement>("input[name='display_name']")?.value).toBe("Updated Clerk");
  });

  it("submits jurisdiction interests as city and county entries", async () => {
    const { container } = await renderAccountView();
    const form = container.querySelector<HTMLFormElement>("#account-interests-form");
    const cityCodes = container.querySelector<HTMLInputElement>("input[name='city_interest_codes']");
    const counties = container.querySelector<HTMLInputElement>("input[name='county_interest_names']");

    if (!form || !cityCodes || !counties) {
      throw new Error("Expected account interests form fields to exist.");
    }

    cityCodes.value = "0955, 5521";
    counties.value = "Canadian, Oklahoma";

    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flush();

    expect(updateAccountInterests).toHaveBeenCalledWith({
      items: [
        { interest_type: "city", copo: "0955" },
        { interest_type: "city", copo: "5521" },
        { interest_type: "county", county_name: "Canadian" },
        { interest_type: "county", county_name: "Oklahoma" },
      ],
    });
    expect(getAccountInterests).toHaveBeenCalledTimes(2);
  });

  it("normalizes forecast preference inputs before saving", async () => {
    const { container } = await renderAccountView();
    const form = container.querySelector<HTMLFormElement>("#forecast-preferences-form");
    const city = container.querySelector<HTMLInputElement>("input[name='default_city_copo_lookup']");
    const county = container.querySelector<HTMLInputElement>("input[name='default_county_name']");
    const taxType = container.querySelector<HTMLSelectElement>("select[name='default_tax_type']");
    const model = container.querySelector<HTMLSelectElement>("select[name='forecast_model']");
    const horizon = container.querySelector<HTMLSelectElement>("select[name='forecast_horizon_months']");
    const lookback = container.querySelector<HTMLSelectElement>("select[name='forecast_lookback_months']");
    const confidence = container.querySelector<HTMLSelectElement>("select[name='forecast_confidence_level']");
    const indicatorProfile = container.querySelector<HTMLSelectElement>("select[name='forecast_indicator_profile']");
    const scope = container.querySelector<HTMLSelectElement>("select[name='forecast_scope']");
    const activity = container.querySelector<HTMLInputElement>("input[name='forecast_activity_code_lookup']");

    if (
      !form ||
      !city ||
      !county ||
      !taxType ||
      !model ||
      !horizon ||
      !lookback ||
      !confidence ||
      !indicatorProfile ||
      !scope ||
      !activity
    ) {
      throw new Error("Expected forecast preference form fields to exist.");
    }

    city.value = "Yukon (5521) - Canadian County";
    county.value = "";
    taxType.value = "lodging";
    model.value = "ensemble";
    horizon.value = "18";
    lookback.value = "24";
    confidence.value = "0.9";
    indicatorProfile.value = "balanced";
    scope.value = "naics";
    activity.value = "722511 - Full-Service Restaurants";

    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await flush();

    expect(updateForecastPreferences).toHaveBeenCalledWith({
      default_city_copo: "5521",
      default_county_name: null,
      default_tax_type: "lodging",
      forecast_model: "ensemble",
      forecast_horizon_months: 18,
      forecast_lookback_months: 24,
      forecast_confidence_level: 0.9,
      forecast_indicator_profile: "balanced",
      forecast_scope: "municipal",
      forecast_activity_code: null,
    });
  });

  it("updates and removes saved follow-up records", async () => {
    const { container } = await renderAccountView();
    const anomalyStatus = container.querySelector<HTMLButtonElement>(".saved-anomaly-status[data-status='resolved']");
    const anomalyNote = container.querySelector<HTMLTextAreaElement>(".saved-anomaly-note");

    if (!anomalyStatus || !anomalyNote) {
      throw new Error("Expected saved follow-up controls to exist.");
    }

    anomalyNote.value = "Escalated to finance director";
    anomalyStatus.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));
    await flush();
    expect(updateSavedAnomaly).toHaveBeenCalledWith("anomaly-1", {
      status: "resolved",
      note: "Escalated to finance director",
    });

    const anomalyDelete = container.querySelector<HTMLButtonElement>(".saved-anomaly-delete");
    if (!anomalyDelete) {
      throw new Error("Expected the anomaly delete control to exist after refresh.");
    }
    anomalyDelete.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));
    await flush();
    expect(deleteSavedAnomaly).toHaveBeenCalledWith("anomaly-1");

    const missedStatus = container.querySelector<HTMLButtonElement>(".saved-missed-filing-status[data-status='investigating']");
    const missedNote = container.querySelector<HTMLTextAreaElement>(".saved-missed-filing-note");
    if (!missedStatus || !missedNote) {
      throw new Error("Expected missed-filing controls to exist after refresh.");
    }
    missedNote.value = "Assign to city clerk";
    missedStatus.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));
    await flush();
    expect(updateSavedMissedFiling).toHaveBeenCalledWith("missed-1", {
      status: "investigating",
      note: "Assign to city clerk",
    });

    const missedDelete = container.querySelector<HTMLButtonElement>(".saved-missed-filing-delete");
    if (!missedDelete) {
      throw new Error("Expected the missed-filing delete control to exist after refresh.");
    }
    missedDelete.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));
    await flush();
    expect(deleteSavedMissedFiling).toHaveBeenCalledWith("missed-1");
  });
});
