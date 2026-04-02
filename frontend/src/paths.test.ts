import { describe, expect, it } from "vitest";

import { canonicalizePath, loginPath } from "./paths";

describe("paths", () => {
  it("builds a login path with a protected next target", () => {
    expect(loginPath("/forecast/0955")).toBe("/login?next=%2Fforecast%2F0955");
  });

  it("preserves query parameters on the next target", () => {
    expect(loginPath("/forecast/0955?scope=naics")).toBe("/login?next=%2Fforecast%2F0955%3Fscope%3Dnaics");
  });

  it("canonicalizes the legacy overview path", () => {
    expect(canonicalizePath("/overview")).toBe("/");
  });
});
