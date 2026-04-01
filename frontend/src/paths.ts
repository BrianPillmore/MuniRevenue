/* ══════════════════════════════════════════════
   Route path helpers
   ══════════════════════════════════════════════ */

export const ROUTES = {
  overview: "/",
  overviewLegacy: "/overview",
  city: "/city",
  county: "/county",
  compare: "/compare",
  forecast: "/forecast",
  anomalies: "/anomalies",
  missedFilings: "/missed-filings",
  rankings: "/rankings",
  trends: "/trends",
  export: "/export",
  about: "/about",
  citiesDirectory: "/oklahoma-cities",
  countiesDirectory: "/oklahoma-counties",
  anomaliesInsight: "/insights/anomalies",
  missedFilingsInsight: "/insights/missed-filings",
} as const;

function trimTrailingSlash(value: string): string {
  if (value === "/") return value;
  return value.replace(/\/+$/, "") || "/";
}

export function normalizePathname(value: string): string {
  if (!value) return ROUTES.overview;

  const withoutQuery = value.split("?")[0]?.split("#")[0] ?? value;
  const withLeadingSlash = withoutQuery.startsWith("/")
    ? withoutQuery
    : `/${withoutQuery}`;

  return trimTrailingSlash(withLeadingSlash);
}

export function canonicalizePath(value: string): string {
  const normalized = normalizePathname(value);
  if (normalized === ROUTES.overviewLegacy) {
    return ROUTES.overview;
  }
  return normalized;
}

export function routeFromLegacyHash(hash: string): string | null {
  if (!hash || !hash.startsWith("#/")) return null;
  return canonicalizePath(hash.slice(1));
}

export function overviewPath(): string {
  return ROUTES.overview;
}

export function cityPath(copo?: string, tab?: string): string {
  if (!copo) return ROUTES.city;
  const base = `${ROUTES.city}/${encodeURIComponent(copo)}`;
  return tab ? `${base}/${encodeURIComponent(tab)}` : base;
}

export function forecastPath(copo?: string): string {
  if (!copo) return ROUTES.forecast;
  return `${ROUTES.forecast}/${encodeURIComponent(copo)}`;
}

export function countyPath(county?: string): string {
  if (!county) return ROUTES.county;
  return `${ROUTES.county}/${encodeURIComponent(county)}`;
}

export function isRouteActive(basePath: string, currentPath: string): boolean {
  const base = canonicalizePath(basePath);
  const current = canonicalizePath(currentPath);

  if (base === ROUTES.overview) {
    return current === ROUTES.overview;
  }

  return current === base || current.startsWith(`${base}/`);
}
