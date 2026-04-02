// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const currentPath = vi.fn();
const getSessionState = vi.fn();
const refreshSession = vi.fn();
const logoutAndRedirect = vi.fn();

vi.mock("../router", () => ({
  currentPath,
}));

vi.mock("../auth", () => ({
  getSessionState,
  refreshSession,
  logoutAndRedirect,
}));

async function renderSidebar() {
  const { renderSidebar } = await import("./sidebar");
  const container = document.createElement("div");
  document.body.appendChild(container);
  renderSidebar(container);
  return { container };
}

describe("sidebar", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    document.body.innerHTML = "";
    currentPath.mockReturnValue("/");
    refreshSession.mockResolvedValue({
      authenticated: false,
      user: null,
    });
  });

  it("shows the login entry when no session is present", async () => {
    getSessionState.mockReturnValue({
      authenticated: false,
      user: null,
    });

    const { container } = await renderSidebar();

    expect(container.textContent).toContain("Account");
    expect(container.textContent).toContain("Login");
    expect(container.querySelector("[data-sidebar-logout]")).toBeNull();
  });

  it("rerenders to the signed-in state when the auth session changes", async () => {
    getSessionState
      .mockReturnValueOnce({
        authenticated: false,
        user: null,
      })
      .mockReturnValue({
        authenticated: true,
        user: {
          user_id: "user-1",
          email: "clerk@example.com",
          display_name: "Clerk Example",
          job_title: null,
          organization_name: null,
        },
      });

    const { container } = await renderSidebar();

    expect(container.textContent).toContain("Login");

    window.dispatchEvent(new CustomEvent("munirev:auth-changed"));

    expect(container.textContent).toContain("Signed in");
    expect(container.textContent).toContain("Clerk Example");
    expect(container.querySelector("[data-sidebar-logout]")).not.toBeNull();
    expect(container.querySelector("a[href='/account']")).not.toBeNull();
  });

  it("logs out from the signed-in sidebar state", async () => {
    getSessionState.mockReturnValue({
      authenticated: true,
      user: {
        user_id: "user-1",
        email: "clerk@example.com",
        display_name: "Clerk Example",
        job_title: null,
        organization_name: null,
      },
    });

    const { container } = await renderSidebar();
    const logoutButton = container.querySelector<HTMLButtonElement>("[data-sidebar-logout]");

    if (!logoutButton) {
      throw new Error("Expected a logout button for authenticated users.");
    }

    logoutButton.dispatchEvent(new Event("click", { bubbles: true, cancelable: true }));

    expect(logoutAndRedirect).toHaveBeenCalledTimes(1);
  });
});
