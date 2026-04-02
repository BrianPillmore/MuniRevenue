// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const getAuthSession = vi.fn();
const logoutAuth = vi.fn();
const navigateTo = vi.fn();

vi.mock("./api", () => ({
  getAuthSession,
  logoutAuth,
}));

vi.mock("./router", () => ({
  navigateTo,
}));

describe("auth helpers", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    window.history.replaceState({}, "", "/");
  });

  it("hydrates session state from the backend session endpoint", async () => {
    getAuthSession.mockResolvedValue({
      authenticated: true,
      user: {
        user_id: "user-1",
        email: "clerk@example.com",
        display_name: "Clerk",
        job_title: null,
        organization_name: null,
      },
    });

    const auth = await import("./auth");
    const session = await auth.refreshSession(true);

    expect(session.authenticated).toBe(true);
    expect(auth.getSessionState().user?.email).toBe("clerk@example.com");
  });

  it("reuses the bootstrapped session unless a forced refresh is requested", async () => {
    getAuthSession
      .mockResolvedValueOnce({
        authenticated: true,
        user: {
          user_id: "user-1",
          email: "clerk@example.com",
          display_name: "Clerk",
          job_title: null,
          organization_name: null,
        },
      })
      .mockResolvedValueOnce({
        authenticated: false,
        user: null,
      });

    const auth = await import("./auth");

    const first = await auth.refreshSession(true);
    const second = await auth.refreshSession();
    const third = await auth.refreshSession(true);

    expect(first.authenticated).toBe(true);
    expect(second.authenticated).toBe(true);
    expect(third.authenticated).toBe(false);
    expect(getAuthSession).toHaveBeenCalledTimes(2);
  });

  it("redirects anonymous users to login when a protected route is requested", async () => {
    getAuthSession.mockResolvedValue({
      authenticated: false,
      user: null,
    });

    const auth = await import("./auth");
    const { loginPath } = await import("./paths");
    const allowed = await auth.ensureSignedIn("/anomalies");

    expect(allowed).toBe(false);
    expect(window.location.pathname + window.location.search).toBe(loginPath("/anomalies"));
  });

  it("preserves query parameters in the requested next path", async () => {
    getAuthSession.mockResolvedValue({
      authenticated: false,
      user: null,
    });

    const auth = await import("./auth");
    await auth.ensureSignedIn("/forecast/0955?scope=naics");

    expect(new URLSearchParams(window.location.search).get("next")).toBe("/forecast/0955?scope=naics");
  });

  it("clears session state and routes to login on logout", async () => {
    getAuthSession.mockResolvedValue({
      authenticated: true,
      user: {
        user_id: "user-1",
        email: "clerk@example.com",
        display_name: "Clerk",
        job_title: null,
        organization_name: null,
      },
    });
    logoutAuth.mockResolvedValue({ ok: true, message: "Logged out" });

    const auth = await import("./auth");
    const { loginPath } = await import("./paths");

    await auth.refreshSession(true);
    await auth.logoutAndRedirect();

    expect(auth.getSessionState().authenticated).toBe(false);
    expect(window.location.pathname + window.location.search).toBe(loginPath());
  });

  it("falls back to an anonymous session when refresh fails", async () => {
    getAuthSession.mockRejectedValue(new Error("backend unavailable"));

    const auth = await import("./auth");
    const session = await auth.refreshSession(true);

    expect(session.authenticated).toBe(false);
    expect(auth.getSessionState().authenticated).toBe(false);
  });
});
