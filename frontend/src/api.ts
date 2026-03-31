/* ══════════════════════════════════════════════
   Centralized API client
   ══════════════════════════════════════════════ */

import type {
  AnomaliesResponse,
  CityDetailResponse,
  CityLedgerResponse,
  CitySearchResponse,
  CountySummaryResponse,
  ForecastComparisonResponse,
  ForecastDriversResponse,
  ForecastQueryOptions,
  ForecastResponse,
  IndustryTimeSeriesResponse,
  NaicsResponse,
  NaicsSectorsResponse,
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

export async function getIndustryTimeSeries(
  copo: string,
  activityCode: string,
  taxType: string,
): Promise<IndustryTimeSeriesResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  return fetchJson<IndustryTimeSeriesResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/naics/timeseries/${encodeURIComponent(activityCode)}?${params}`,
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
  options: ForecastQueryOptions = {},
): Promise<ForecastResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (options.model) params.set("model", options.model);
  if (options.horizonMonths !== undefined) {
    params.set("horizon_months", String(options.horizonMonths));
  }
  if (options.lookbackMonths !== undefined) {
    params.set("lookback_months", String(options.lookbackMonths));
  }
  if (options.confidenceLevel !== undefined) {
    params.set("confidence_level", String(options.confidenceLevel));
  }
  if (options.indicatorProfile) {
    params.set("indicator_profile", options.indicatorProfile);
  }
  if (options.activityCode) {
    params.set("activity_code", options.activityCode);
  }
  return fetchJson<ForecastResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/forecast?${params}`,
  );
}

export async function getCityForecastComparison(
  copo: string,
  taxType: string,
  options: ForecastQueryOptions = {},
): Promise<ForecastComparisonResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (options.model) params.set("model", options.model);
  if (options.horizonMonths !== undefined) {
    params.set("horizon_months", String(options.horizonMonths));
  }
  if (options.lookbackMonths !== undefined) {
    params.set("lookback_months", String(options.lookbackMonths));
  }
  if (options.confidenceLevel !== undefined) {
    params.set("confidence_level", String(options.confidenceLevel));
  }
  if (options.indicatorProfile) {
    params.set("indicator_profile", options.indicatorProfile);
  }
  if (options.activityCode) {
    params.set("activity_code", options.activityCode);
  }
  return fetchJson<ForecastComparisonResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/forecast/compare?${params}`,
  );
}

export async function getCityForecastDrivers(
  copo: string,
  taxType: string,
  options: ForecastQueryOptions = {},
): Promise<ForecastDriversResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (options.model) params.set("model", options.model);
  if (options.horizonMonths !== undefined) {
    params.set("horizon_months", String(options.horizonMonths));
  }
  if (options.lookbackMonths !== undefined) {
    params.set("lookback_months", String(options.lookbackMonths));
  }
  if (options.confidenceLevel !== undefined) {
    params.set("confidence_level", String(options.confidenceLevel));
  }
  if (options.indicatorProfile) {
    params.set("indicator_profile", options.indicatorProfile);
  }
  if (options.activityCode) {
    params.set("activity_code", options.activityCode);
  }
  return fetchJson<ForecastDriversResponse>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/forecast/drivers?${params}`,
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
    `${API_BASE}/api/counties/${encodeURIComponent(county)}/summary?${params}`,
  );
}

export async function getAnomalies(
  severity?: string,
  anomalyType?: string,
  taxType?: string,
  limit?: number,
): Promise<AnomaliesResponse> {
  const params = new URLSearchParams();
  if (severity) params.set("severity", severity);
  if (anomalyType) params.set("anomaly_type", anomalyType);
  if (taxType) params.set("tax_type", taxType);
  if (limit !== undefined) params.set("limit", String(limit));
  return fetchJson<AnomaliesResponse>(
    `${API_BASE}/api/stats/anomalies?${params}`,
  );
}

export async function getAnomalyDecomposition(
  copo: string,
  anomalyDate: string,
  taxType: string,
  comparison?: string,
): Promise<any> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (comparison) params.set("comparison", comparison);
  return fetchJson<any>(
    `${API_BASE}/api/cities/${encodeURIComponent(copo)}/anomalies/${encodeURIComponent(anomalyDate)}/decompose?${params}`,
  );
}

export async function getNaicsSectors(
  taxType: string,
  limit?: number,
): Promise<NaicsSectorsResponse> {
  const params = new URLSearchParams({ tax_type: taxType });
  if (limit !== undefined) params.set("limit", String(limit));
  return fetchJson<NaicsSectorsResponse>(
    `${API_BASE}/api/stats/naics-sectors?${params}`,
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
