// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const refreshSession = vi.fn();

vi.mock("./auth", () => ({
  refreshSession,
}));

function makeView(label: string) {
  return {
    render(container: HTMLElement) {
      container.textContent = label;
    },
    destroy() {
      /* no-op */
    },
  };
}

describe("router protected flow", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/");
    window.scrollTo = vi.fn();
  });

  it("redirects direct navigation on a protected route to login", async () => {
    refreshSession.mockResolvedValue({
      authenticated: false,
      user: null,
    });
    window.history.replaceState({}, "", "/forecast/0955?tab=drivers");

    const { initRouter } = await import("./router");
    const { ROUTES, loginPath } = await import("./paths");

    const container = document.createElement("div");
    document.body.appendChild(container);

    initRouter(container, {
      [ROUTES.overview]: makeView("overview"),
      [ROUTES.login]: makeView("login"),
      [ROUTES.forecast]: makeView("forecast"),
      [`${ROUTES.forecast}/:copo`]: makeView("forecast"),
    });

    await Promise.resolve();
    await Promise.resolve();

    expect(window.location.pathname + window.location.search).toBe(
      loginPath("/forecast/0955?tab=drivers"),
    );
  });

  it("renders a protected route when the session is authenticated", async () => {
    refreshSession.mockResolvedValue({
      authenticated: true,
      user: {
        user_id: "user-1",
        email: "clerk@example.com",
        display_name: "Clerk",
        job_title: null,
        organization_name: null,
      },
    });
    window.history.replaceState({}, "", "/missed-filings");

    const { initRouter } = await import("./router");
    const { ROUTES } = await import("./paths");

    const container = document.createElement("div");
    document.body.appendChild(container);

    initRouter(container, {
      [ROUTES.overview]: makeView("overview"),
      [ROUTES.login]: makeView("login"),
      [ROUTES.missedFilings]: makeView("missed-filings"),
    });

    await Promise.resolve();
    await Promise.resolve();

    expect(window.location.pathname).toBe("/missed-filings");
    expect(container.textContent).toBe("missed-filings");
  });

  it("redirects direct navigation on the anomalies route to login", async () => {
    refreshSession.mockResolvedValue({
      authenticated: false,
      user: null,
    });
    window.history.replaceState({}, "", "/anomalies");

    const { initRouter } = await import("./router");
    const { ROUTES, loginPath } = await import("./paths");

    const container = document.createElement("div");
    document.body.appendChild(container);

    initRouter(container, {
      [ROUTES.overview]: makeView("overview"),
      [ROUTES.login]: makeView("login"),
      [ROUTES.anomalies]: makeView("anomalies"),
    });

    await Promise.resolve();
    await Promise.resolve();

    expect(window.location.pathname + window.location.search).toBe(
      loginPath("/anomalies"),
    );
  });
});
