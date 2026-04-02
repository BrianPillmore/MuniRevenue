// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const getAnomalies = vi.fn();
const getAnomalyDecomposition = vi.fn();
const getSavedAnomalies = vi.fn();
const saveAnomalyFollowUp = vi.fn();
const showLoading = vi.fn();
const setPageMetadata = vi.fn();
const chartDestroy = vi.fn();
const chart = vi.fn(() => ({ destroy: chartDestroy }));

vi.mock("../api", () => ({
  getAnomalies,
  getAnomalyDecomposition,
  getSavedAnomalies,
  saveAnomalyFollowUp,
}));

vi.mock("../components/loading", () => ({
  showLoading,
}));

vi.mock("../seo", () => ({
  setPageMetadata,
}));

vi.mock("../theme", () => ({
  default: {
    chart,
  },
}));

function flushPromises(): Promise<void> {
  return Promise.resolve().then(() => Promise.resolve()).then(() => Promise.resolve());
}

describe("anomaliesView", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/anomalies");

    getSavedAnomalies.mockResolvedValue({ items: [] });
    getAnomalies.mockResolvedValue({
      items: [
        {
          copo: "0955",
          city_name: "Norman",
          tax_type: "sales",
          anomaly_date: "2026-03-01",
          anomaly_type: "yoy_drop",
          severity: "high",
          description: "Sales revenue fell sharply versus the prior year.",
          expected_value: 10000,
          actual_value: 4000,
          deviation_pct: -60,
        },
      ],
      count: 1,
    });
    getAnomalyDecomposition.mockResolvedValue({
      industries: [],
      total_change_pct: 0,
    });
    saveAnomalyFollowUp.mockResolvedValue({
      items: [
        {
          saved_anomaly_id: "saved-1",
          copo: "0955",
          tax_type: "sales",
          anomaly_date: "2026-03-01",
          anomaly_type: "yoy_drop",
          activity_code: null,
          status: "saved",
          note: null,
          city_name: "Norman",
        },
      ],
    });
  });

  it("saves an anomaly follow-up and marks the card as saved", async () => {
    const { anomaliesView } = await import("./anomalies");

    const container = document.createElement("div");
    document.body.appendChild(container);
    anomaliesView.render(container, {});

    await flushPromises();
    await flushPromises();

    expect(getSavedAnomalies).toHaveBeenCalledTimes(1);
    expect(getAnomalies).toHaveBeenCalledTimes(1);

    const saveButton = container.querySelector<HTMLButtonElement>(".save-anomaly-btn");
    if (!saveButton) {
      throw new Error("Expected anomaly save button to render.");
    }

    saveButton.click();
    await flushPromises();

    expect(saveAnomalyFollowUp).toHaveBeenCalledWith({
      copo: "0955",
      tax_type: "sales",
      anomaly_date: "2026-03-01",
      anomaly_type: "yoy_drop",
      status: "saved",
    });

    const savedButton = container.querySelector<HTMLButtonElement>(".save-anomaly-btn");
    if (!savedButton) {
      throw new Error("Expected anomaly save button to remain rendered.");
    }

    expect(savedButton.disabled).toBe(true);
    expect(savedButton.textContent).toBe("Saved");
  });
});
