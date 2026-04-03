// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const requestMagicLink = vi.fn();
const refreshSession = vi.fn();
const navigateTo = vi.fn();
const setPageMetadata = vi.fn();

vi.mock("../api", () => ({
  requestMagicLink,
}));

vi.mock("../auth", () => ({
  getSessionState: () => ({ authenticated: false, user: null }),
  refreshSession,
}));

vi.mock("../router", () => ({
  navigateTo,
}));

vi.mock("../seo", () => ({
  setPageMetadata,
}));

describe("loginView", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/login?next=%2Fforecast%2F0955");
    refreshSession.mockResolvedValue({ authenticated: false, user: null });
    requestMagicLink.mockResolvedValue({
      ok: true,
      message: "If that email is eligible, an email has been sent.",
    });
  });

  it("submits the email address and next path to the magic-link endpoint", async () => {
    const { loginView } = await import("./login");

    const container = document.createElement("div");
    document.body.appendChild(container);
    loginView.render(container, {});

    const emailInput = container.querySelector<HTMLInputElement>("#login-email");
    const form = container.querySelector<HTMLFormElement>("#login-form");
    const message = container.querySelector<HTMLElement>("#login-message");

    if (!emailInput || !form || !message) {
      throw new Error("Expected login form elements to exist.");
    }

    emailInput.value = "clerk@example.com";
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve();
    await Promise.resolve();

    expect(requestMagicLink).toHaveBeenCalledWith("clerk@example.com", "/forecast/0955");
    expect(message.textContent).toContain("eligible");
  });

  it("shows the verification completion message when redirected back from email verification", async () => {
    window.history.replaceState({}, "", "/login?verified=1&next=%2Faccount");
    const { loginView } = await import("./login");

    const container = document.createElement("div");
    document.body.appendChild(container);
    loginView.render(container, {});

    const message = container.querySelector<HTMLElement>("#login-message");
    expect(message?.textContent).toContain("Email verified");
  });
});
