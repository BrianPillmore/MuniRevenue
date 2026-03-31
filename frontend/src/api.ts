/* ══════════════════════════════════════════════
   Centralized API client
   ══════════════════════════════════════════════ */

import type {
  CityDetailResponse,
  CityLedgerResponse,
  CitySearchResponse,
  CountySummaryResponse,
  ForecastResponse,
  NaicsResponse,
  OverviewResponse,
  RankingsResponse,
  SeasonalityResponse,
  StatewideTrendResponse,
  TopNaicsResponse,
} from "./types";

/**
 * API base URL.
 *
 * In production the frontend is served by the same origin as the API,
 * so an empty string works (all fetches go to the same host).
 * During development Vite's proxy rewrites /api/* to the backend.
 */
const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";

/* ── Generic fetch helper ── */

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: string }).detail
        : `API request failed: ${response.status}`;
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

/* ── City endpoints ── */

export async function searchCities(
  query: string,
  type?: string,
  limit?: number,
): Promise<CitySearchResponse> {
  const params = new URLSearchParams({ search: query });
  if (type) params.set("type", type);
  if (limit !== undefined) params.set("limit", String(limit));
  return fetchJson<CitySearchResponse>(
    `${API_BASE}/api/cities?${params}`,
  );
}

export async function getCityDetail(
  copo: string,
): Promise<CityDetailResponse> {
  return fetchJson<CityDetailResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}`,
  );
}

export async function getCityLedger(
  copo: string,
  taxType: string,
  start?: string,
  end?: string,
): Promise<CityLedgerResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return fetchJson<CityLedgerResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/ledger?${params}`,
  );
}

export async function getCityNaics(
  copo: string,
  taxType: string,
  year?: number,
  month?: number,
): Promise<NaicsResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (year !== undefined) params.set("year", String(year));
  if (month !== undefined) params.set("month", String(month));
  return fetchJson<NaicsResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/naics?${params}`,
  );
}

export async function getCityNaicsTop(
  copo: string,
  taxType: string,
  limit?: number,
): Promise<TopNaicsResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (limit !== undefined) params.set("limit", String(limit));
  return fetchJson<TopNaicsResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/naics/top?${params}`,
  );
}

export async function getCitySeasonality(
  copo: string,
  taxType: string,
): Promise<SeasonalityResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  return fetchJson<SeasonalityResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/seasonality?${params}`,
  );
}

export async function getCityForecast(
  copo: string,
  taxType: string,
): Promise<ForecastResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  return fetchJson<ForecastResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/forecast?${params}`,
  );
}

/* ── Statewide / analytics endpoints ── */

export async function getOverview(): Promise<OverviewResponse> {
  return fetchJson<OverviewResponse>(`${API_BASE}/api/stats/overview`);
}

export async function getStatewideTrend(
  taxType: string,
  start?: string,
  end?: string,
): Promise<StatewideTrendResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  return fetchJson<StatewideTrendResponse>(
    `${API_BASE}/api/stats/statewide-trend?${params}`,
  );
}

export async function getRankings(
  taxType: string,
  metric: string,
  limit?: number,
  offset?: number,
): Promise<RankingsResponse> {
  const params = new URLSearchParams({ tax_type: taxType, metric });
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  return fetchJson<RankingsResponse>(
    `${API_BASE}/api/stats/rankings?${params}`,
  );
}

export async function getCountySummary(
  county: string,
  taxType: string,
): Promise<CountySummaryResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  return fetchJson<CountySummaryResponse>(
    `${API_BASE}/api/stats/county/${encodeURIComponent(county)}?${params}`,
  );
}

/**
 * Trigger a CSV download of ledger data for a city.
 * Creates a temporary anchor element and clicks it.
 */
export function exportLedgerCsv(
  copo: string,
  taxType: string,
  start?: string,
  end?: string,
): void {
  const params = new URLSearchParams({ tax_type: taxType });
  if (start) params.set("start", start);
  if (end) params.set("end", end);
  const url = `${API_BASE}/api/cities/${encodeURIComponent(copo)}/ledger/export?${params}`;
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `ledger-${copo}-${taxType}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
}
