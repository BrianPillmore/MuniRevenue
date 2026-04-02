// @vitest-environment jsdom

import { describe, expect, it } from "vitest";

import { protectedRouteRedirectTarget } from "./router";

describe("protectedRouteRedirectTarget", () => {
  it("redirects protected routes to login with next preserved", () => {
    expect(protectedRouteRedirectTarget("/forecast/0955?tab=drivers", false)).toBe(
      "/login?next=%2Fforecast%2F0955%3Ftab%3Ddrivers",
    );
  });

  it("does not redirect public routes", () => {
    expect(protectedRouteRedirectTarget("/city/0955", false)).toBeNull();
  });

  it("does not redirect when already authenticated", () => {
    expect(protectedRouteRedirectTarget("/missed-filings", true)).toBeNull();
  });
});
