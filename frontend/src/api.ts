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
  JurisdictionInterestsResponse,
  MagicLinkRequestResponse,
  MissedFilingsResponse,
  NaicsResponse,
  NaicsSectorsResponse,
  OverviewResponse,
  AccountProfile,
  RankingsResponse,
  AuthSessionResponse,
  ForecastPreferences,
  SavedAnomaliesResponse,
  SavedMissedFilingsResponse,
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

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: "include",
    ...init,
  });
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

async function sendJson<T>(
  url: string,
  method: string,
  body?: unknown,
): Promise<T> {
  return fetchJson<T>(url, {
    method,
    headers: {
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
  options: {
    severity?: string;
    anomalyType?: string;
    taxType?: string;
    startDate?: string;
    endDate?: string;
    limit?: number;
  } = {},
): Promise<AnomaliesResponse> {
  const params = new URLSearchParams();
  if (options.severity) params.set("severity", options.severity);
  if (options.anomalyType) params.set("anomaly_type", options.anomalyType);
  if (options.taxType) params.set("tax_type", options.taxType);
  if (options.startDate) params.set("start_date", options.startDate);
  if (options.endDate) params.set("end_date", options.endDate);
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  return fetchJson<AnomaliesResponse>(
    `${API_BASE}/api/stats/anomalies?${params}`,
  );
}

export async function getMissedFilings(
  options: {
    severity?: string;
    taxType?: string;
    cityQuery?: string;
    naicsQuery?: string;
    runRateMethod?: string;
    sortBy?: string;
    startDate?: string;
    endDate?: string;
    minExpectedValue?: number;
    minMissingAmount?: number;
    minMissingPct?: number;
    minBaselineSharePct?: number;
    highMissingAmount?: number;
    highMissingPct?: number;
    criticalMissingAmount?: number;
    criticalMissingPct?: number;
    limit?: number;
    offset?: number;
  } = {},
): Promise<MissedFilingsResponse> {
  const params = new URLSearchParams();
  if (options.severity) params.set("severity", options.severity);
  if (options.taxType) params.set("tax_type", options.taxType);
  if (options.cityQuery) params.set("city_query", options.cityQuery);
  if (options.naicsQuery) params.set("naics_query", options.naicsQuery);
  if (options.runRateMethod) params.set("run_rate_method", options.runRateMethod);
  if (options.sortBy) params.set("sort_by", options.sortBy);
  if (options.startDate) params.set("start_date", options.startDate);
  if (options.endDate) params.set("end_date", options.endDate);
  if (options.minExpectedValue !== undefined) {
    params.set("min_expected_value", String(options.minExpectedValue));
  }
  if (options.minMissingAmount !== undefined) {
    params.set("min_missing_amount", String(options.minMissingAmount));
  }
  if (options.minMissingPct !== undefined) {
    params.set("min_missing_pct", String(options.minMissingPct));
  }
  if (options.minBaselineSharePct !== undefined) {
    params.set("min_baseline_share_pct", String(options.minBaselineSharePct));
  }
  if (options.highMissingAmount !== undefined) {
    params.set("high_missing_amount", String(options.highMissingAmount));
  }
  if (options.highMissingPct !== undefined) {
    params.set("high_missing_pct", String(options.highMissingPct));
  }
  if (options.criticalMissingAmount !== undefined) {
    params.set("critical_missing_amount", String(options.criticalMissingAmount));
  }
  if (options.criticalMissingPct !== undefined) {
    params.set("critical_missing_pct", String(options.criticalMissingPct));
  }
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  return fetchJson<MissedFilingsResponse>(
    `${API_BASE}/api/stats/missed-filings?${params}`,
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

/* ── Auth / account endpoints ── */

export async function requestMagicLink(
  email: string,
  nextPath?: string,
): Promise<MagicLinkRequestResponse> {
  return sendJson<MagicLinkRequestResponse>(`${API_BASE}/api/auth/magic-link/request`, "POST", {
    email,
    next: nextPath,
    next_path: nextPath,
  });
}

export async function getAuthSession(): Promise<AuthSessionResponse> {
  return fetchJson<AuthSessionResponse>(`${API_BASE}/api/auth/session`);
}

export async function logoutAuth(): Promise<MagicLinkRequestResponse> {
  return sendJson<MagicLinkRequestResponse>(`${API_BASE}/api/auth/logout`, "POST");
}

export async function getAccountProfile(): Promise<AccountProfile> {
  return fetchJson<AccountProfile>(`${API_BASE}/api/account/profile`);
}

export async function updateAccountProfile(payload: {
  display_name?: string | null;
  job_title?: string | null;
  organization_name?: string | null;
  marketing_opt_in?: boolean;
}): Promise<AccountProfile> {
  return sendJson<AccountProfile>(`${API_BASE}/api/account/profile`, "PUT", payload);
}

export async function getAccountInterests(): Promise<JurisdictionInterestsResponse> {
  return fetchJson<JurisdictionInterestsResponse>(`${API_BASE}/api/account/interests`);
}

export async function updateAccountInterests(payload: {
  items: Array<{
    interest_type: string;
    copo?: string | null;
    county_name?: string | null;
    label?: string | null;
  }>;
}): Promise<JurisdictionInterestsResponse> {
  return sendJson<JurisdictionInterestsResponse>(`${API_BASE}/api/account/interests`, "PUT", payload);
}

export async function getForecastPreferences(): Promise<ForecastPreferences> {
  return fetchJson<ForecastPreferences>(`${API_BASE}/api/account/forecast-preferences`);
}

export async function updateForecastPreferences(payload: ForecastPreferences): Promise<ForecastPreferences> {
  return sendJson<ForecastPreferences>(`${API_BASE}/api/account/forecast-preferences`, "PUT", payload);
}

export async function getSavedAnomalies(): Promise<SavedAnomaliesResponse> {
  return fetchJson<SavedAnomaliesResponse>(`${API_BASE}/api/account/saved-anomalies`);
}

export async function saveAnomalyFollowUp(payload: {
  copo: string;
  tax_type: string;
  anomaly_date: string;
  anomaly_type: string;
  activity_code?: string | null;
  status?: string;
  note?: string | null;
}): Promise<SavedAnomaliesResponse> {
  return sendJson<SavedAnomaliesResponse>(`${API_BASE}/api/account/saved-anomalies`, "POST", payload);
}

export async function updateSavedAnomaly(
  savedAnomalyId: string,
  payload: { status?: string; note?: string | null },
): Promise<SavedAnomaliesResponse> {
  return sendJson<SavedAnomaliesResponse>(`${API_BASE}/api/account/saved-anomalies/${encodeURIComponent(savedAnomalyId)}`, "PATCH", payload);
}

export async function deleteSavedAnomaly(savedAnomalyId: string): Promise<SavedAnomaliesResponse> {
  return fetchJson<SavedAnomaliesResponse>(`${API_BASE}/api/account/saved-anomalies/${encodeURIComponent(savedAnomalyId)}`, {
    method: "DELETE",
    credentials: "include",
  });
}

export async function getSavedMissedFilings(): Promise<SavedMissedFilingsResponse> {
  return fetchJson<SavedMissedFilingsResponse>(`${API_BASE}/api/account/saved-missed-filings`);
}

export async function saveMissedFilingFollowUp(payload: {
  copo: string;
  tax_type: string;
  anomaly_date: string;
  activity_code: string;
  baseline_method: string;
  expected_value?: number;
  actual_value?: number;
  missing_amount?: number;
  missing_pct?: number;
  status?: string;
  note?: string | null;
}): Promise<SavedMissedFilingsResponse> {
  return sendJson<SavedMissedFilingsResponse>(`${API_BASE}/api/account/saved-missed-filings`, "POST", payload);
}

export async function updateSavedMissedFiling(
  savedMissedFilingId: string,
  payload: { status?: string; note?: string | null },
): Promise<SavedMissedFilingsResponse> {
  return sendJson<SavedMissedFilingsResponse>(`${API_BASE}/api/account/saved-missed-filings/${encodeURIComponent(savedMissedFilingId)}`, "PATCH", payload);
}

export async function deleteSavedMissedFiling(savedMissedFilingId: string): Promise<SavedMissedFilingsResponse> {
  return fetchJson<SavedMissedFilingsResponse>(`${API_BASE}/api/account/saved-missed-filings/${encodeURIComponent(savedMissedFilingId)}`, {
    method: "DELETE",
    credentials: "include",
  });
}
