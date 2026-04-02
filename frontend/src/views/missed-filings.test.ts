// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const getMissedFilings = vi.fn();
const getSavedMissedFilings = vi.fn();
const saveMissedFilingFollowUp = vi.fn();
const showLoading = vi.fn();
const setPageMetadata = vi.fn();

vi.mock("../api", () => ({
  getMissedFilings,
  getSavedMissedFilings,
  saveMissedFilingFollowUp,
}));

vi.mock("../components/loading", () => ({
  showLoading,
}));

vi.mock("../seo", () => ({
  setPageMetadata,
}));

function flushPromises(): Promise<void> {
  return Promise.resolve().then(() => Promise.resolve()).then(() => Promise.resolve());
}

describe("missedFilingsView", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/missed-filings");

    getSavedMissedFilings.mockResolvedValue({ items: [] });
    getMissedFilings.mockResolvedValue({
      items: [
        {
          copo: "0955",
          city_name: "Norman",
          tax_type: "sales",
          anomaly_date: "2026-03-01",
          activity_code: "0114",
          activity_description: "Broilers and chickens",
          baseline_method: "hybrid",
          baseline_months_used: 12,
          prior_year_value: 8000,
          trailing_mean_3: 9000,
          trailing_mean_6: 8800,
          trailing_mean_12: 8600,
          trailing_median_12: 8700,
          exp_weighted_avg_12: 8900,
          expected_value: 9000,
          actual_value: 2000,
          missing_amount: 7000,
          missing_pct: 77.8,
          baseline_share_pct: 5.4,
          severity: "high",
          recommendation: "Investigate NAICS 0114 for a likely missed filing.",
        },
      ],
      count: 1,
      total: 1,
      limit: 100,
      offset: 0,
      has_more: false,
      refresh_info: {
        last_refresh_at: "2026-04-01T12:00:00Z",
        data_min_month: "2024-05-01",
        data_max_month: "2026-03-01",
        snapshot_row_count: 20754,
        refresh_duration_seconds: 390.4,
      },
    });
    saveMissedFilingFollowUp.mockResolvedValue({
      items: [
        {
          saved_missed_filing_id: "saved-1",
          copo: "0955",
          tax_type: "sales",
          anomaly_date: "2026-03-01",
          activity_code: "0114",
          baseline_method: "hybrid",
          expected_value: 9000,
          actual_value: 2000,
          missing_amount: 7000,
          missing_pct: 77.8,
          status: "saved",
          note: null,
          city_name: "Norman",
        },
      ],
    });
  });

  it("saves a missed-filing follow-up and marks the card as saved", async () => {
    const { missedFilingsView } = await import("./missed-filings");

    const container = document.createElement("div");
    document.body.appendChild(container);
    missedFilingsView.render(container, {});

    await flushPromises();
    await flushPromises();

    expect(getSavedMissedFilings).toHaveBeenCalledTimes(1);
    expect(getMissedFilings).toHaveBeenCalledTimes(1);

    const saveButton = container.querySelector<HTMLButtonElement>(".save-missed-filing-btn");
    if (!saveButton) {
      throw new Error("Expected missed-filing save button to render.");
    }

    saveButton.click();
    await flushPromises();

    expect(saveMissedFilingFollowUp).toHaveBeenCalledWith({
      copo: "0955",
      tax_type: "sales",
      anomaly_date: "2026-03-01",
      activity_code: "0114",
      baseline_method: "hybrid",
      expected_value: 9000,
      actual_value: 2000,
      missing_amount: 7000,
      missing_pct: 77.8,
      status: "saved",
    });

    const savedButton = container.querySelector<HTMLButtonElement>(".save-missed-filing-btn");
    if (!savedButton) {
      throw new Error("Expected missed-filing save button to remain rendered.");
    }

    expect(savedButton.disabled).toBe(true);
    expect(savedButton.textContent).toBe("Saved");
  });
});
