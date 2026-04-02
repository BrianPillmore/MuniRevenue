/* ══════════════════════════════════════════════
   MuniRev TypeScript interfaces
   ══════════════════════════════════════════════ */

/* ── Legacy analysis types (file upload) ── */

export interface SummaryMetrics {
  records: number;
  first_date: string;
  last_date: string;
  average_returned: number;
  latest_returned: number;
  latest_mom_pct: number | null;
  latest_yoy_pct: number | null;
}

export interface ChangeRow {
  voucher_date: string;
  returned: number;
  mom_pct: number | null;
  yoy_pct: number | null;
}

export interface SeasonalRow {
  month: string;
  observations: number;
  mean_returned: number;
  median_returned: number;
  min_returned: number;
  max_returned: number;
}

export interface AnovaResult {
  f_statistic: number | null;
  p_value: number | null;
  significant: boolean | null;
  interpretation: string;
  note?: string | null;
}

export interface ForecastPoint {
  date: string;
  projected_returned: number;
  lower_bound: number;
  upper_bound: number;
  basis_month: string;
}

export interface AnalysisResponse {
  summary: SummaryMetrics;
  monthly_changes: ChangeRow[];
  seasonality: SeasonalRow[];
  anova: AnovaResult;
  forecast: ForecastPoint[];
  highlights: string[];
}

/* ── Dashboard API types ── */

export interface CityListItem {
  copo: string;
  name: string;
  jurisdiction_type: string;
  county_name: string | null;
  population: number | null;
  has_ledger_data: boolean;
  latest_voucher_date: string | null;
  total_sales_returned: number | null;
}

export interface CitySearchResponse {
  items: CityListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface TaxTypeSummary {
  tax_type: string;
  record_count: number;
  earliest_date: string | null;
  latest_date: string | null;
  total_returned: number | null;
}

export interface CityDetailResponse {
  copo: string;
  name: string;
  jurisdiction_type: string;
  county_name: string | null;
  population: number | null;
  tax_type_summaries: TaxTypeSummary[];
  naics_record_count: number;
  naics_earliest_year_month: number | null;
  naics_latest_year_month: number | null;
}

export interface LedgerRecord {
  voucher_date: string;
  tax_type: string;
  tax_rate: number;
  current_month_collection: number;
  refunded: number;
  suspended_monies: number;
  apportioned: number;
  revolving_fund: number;
  interest_returned: number;
  returned: number;
  mom_pct: number | null;
  yoy_pct: number | null;
}

export interface CityLedgerResponse {
  copo: string;
  tax_type: string;
  records: LedgerRecord[];
  count: number;
}

export interface NaicsRecord {
  activity_code: string;
  activity_description: string | null;
  sector: string;
  tax_rate: number;
  sector_total: number;
  year_to_date: number;
  pct_of_total: number | null;
}

export interface NaicsResponse {
  copo: string;
  tax_type: string;
  year: number;
  month: number;
  records: NaicsRecord[];
  count: number;
  total_revenue: number | null;
}

export interface TopNaicsRecord {
  activity_code: string;
  activity_description: string | null;
  sector: string;
  avg_sector_total: number;
  months_present: number;
  total_across_months: number;
}

export interface TopNaicsResponse {
  copo: string;
  tax_type: string;
  records: TopNaicsRecord[];
  count: number;
}

export interface IndustryTimeSeriesPoint {
  year: number;
  month: number;
  sector_total: number;
}

export interface IndustryTimeSeriesResponse {
  copo: string;
  activity_code: string;
  activity_description: string | null;
  tax_type: string;
  records: IndustryTimeSeriesPoint[];
  count: number;
}

export interface TopCityBySales {
  copo: string;
  name: string;
  total_sales_returned: number;
}

export interface OverviewResponse {
  jurisdictions_with_data: number;
  total_ledger_records: number;
  total_naics_records: number;
  earliest_ledger_date: string | null;
  latest_ledger_date: string | null;
  earliest_naics_year_month: number | null;
  latest_naics_year_month: number | null;
  top_cities_by_sales: TopCityBySales[];
}

/* ── Statewide analytics types ── */

export interface StatewideTrendRecord {
  voucher_date: string;
  total_returned: number;
  jurisdiction_count: number;
  mom_pct: number | null;
  yoy_pct: number | null;
}

export interface StatewideTrendResponse {
  tax_type: string;
  records: StatewideTrendRecord[];
  count: number;
}

export interface RankingItem {
  rank: number;
  copo: string;
  name: string;
  county_name: string | null;
  jurisdiction_type: string;
  population: number | null;
  metric_value: number | null;
}

export interface RankingsResponse {
  tax_type: string;
  metric: string;
  items: RankingItem[];
  total: number;
  limit: number;
  offset: number;
}

/* ── County summary types ── */

export interface CountyCitySummary {
  copo: string;
  name: string;
  total_returned: number | null;
  latest_returned: number | null;
}

export interface CountyMonthlyTotal {
  voucher_date: string;
  total_returned: number;
  city_count: number;
}

export interface CountySummaryResponse {
  county_name: string;
  city_count: number;
  cities: CountyCitySummary[];
  monthly_totals: CountyMonthlyTotal[];
}

/* ── Seasonality types ── */

export interface SeasonalityRecord {
  month: number;
  month_name: string;
  observations: number;
  mean_returned: number | null;
  median_returned: number | null;
  min_returned: number | null;
  max_returned: number | null;
  std_dev: number | null;
}

export interface SeasonalityResponse {
  copo: string;
  tax_type: string;
  months: SeasonalityRecord[];
}

/* ── Forecast types ── */

export interface CityForecastPoint {
  target_date: string;
  projected_value: number;
  lower_bound: number;
  upper_bound: number;
}

export interface ForecastBacktestSummary {
  mape: number | null;
  smape: number | null;
  mae: number | null;
  rmse: number | null;
  coverage: number | null;
  fold_count: number;
  holdout_description: string | null;
}

export interface ForecastModelComparison {
  model: string;
  status: string;
  selected: boolean;
  reason: string;
  uses_indicators: boolean;
  parameters: Record<string, unknown>;
  forecast_points: CityForecastPoint[];
  backtest: ForecastBacktestSummary;
  indicator_effects: Array<Record<string, unknown>>;
}

export interface ForecastExplainability {
  selected_model_reason: string;
  model_comparison_summary: string;
  trend_summary: string;
  seasonality_summary: string;
  holiday_summary: string;
  indicator_summary: string;
  industry_mix_summary: string;
  indicator_drivers: Array<Record<string, unknown>>;
  top_industry_drivers: Array<Record<string, unknown>>;
  activity_description: string | null;
  data_quality_flags: string[];
  caveats: string[];
  confidence_summary: string;
}

export interface ForecastDataQuality {
  observation_count: number;
  expected_months: number;
  minimum_history_required: number;
  latest_observation: string | null;
  stale_months: number | null;
  missing_month_count: number;
  missing_months: string[];
  has_unresolved_gaps: boolean;
  is_sparse_history: boolean;
  advanced_models_allowed: boolean;
  warnings: string[];
  series_scope: string | null;
  series_start: string | null;
  series_end: string | null;
  activity_code: string | null;
  activity_description: string | null;
  recent_revenue_share_pct?: number | null;
}

export interface ForecastResponse {
  copo: string;
  tax_type: string;
  model: string;
  forecasts: CityForecastPoint[];
  selected_model: string;
  requested_model: string;
  eligible_models: string[];
  forecast_points: CityForecastPoint[];
  backtest_summary: ForecastBacktestSummary;
  model_comparison: ForecastModelComparison[];
  explainability: ForecastExplainability;
  data_quality: ForecastDataQuality;
  series_scope: string;
  activity_code: string | null;
  activity_description: string | null;
  horizon_months: number;
  lookback_months: number | null;
  confidence_level: number;
  indicator_profile: string;
  run_id?: number | null;
}

export interface ForecastComparisonResponse {
  copo: string;
  tax_type: string;
  selected_model: string;
  requested_model: string;
  eligible_models: string[];
  model_comparison: ForecastModelComparison[];
  data_quality: ForecastDataQuality;
  series_scope: string;
  activity_code: string | null;
  activity_description: string | null;
}

export interface ForecastDriversResponse {
  copo: string;
  tax_type: string;
  selected_model: string;
  requested_model: string;
  explainability: ForecastExplainability;
  data_quality: ForecastDataQuality;
  backtest_summary: ForecastBacktestSummary;
  series_scope: string;
  activity_code: string | null;
  activity_description: string | null;
}

export interface ForecastQueryOptions {
  model?: string;
  horizonMonths?: number;
  lookbackMonths?: number | "all";
  confidenceLevel?: number;
  indicatorProfile?: string;
  activityCode?: string | null;
}

/* ── Anomaly types ── */

export interface AnomalyItem {
  copo: string;
  city_name: string;
  tax_type: string;
  anomaly_date: string;
  anomaly_type: string;
  severity: string;
  expected_value: number | null;
  actual_value: number | null;
  deviation_pct: number;
  description: string;
}

export interface AnomaliesResponse {
  items: AnomalyItem[];
  count: number;
}

export interface MissedFilingItem {
  copo: string;
  city_name: string;
  tax_type: string;
  anomaly_date: string;
  activity_code: string;
  activity_description: string;
  baseline_method: string;
  baseline_months_used: number;
  prior_year_value: number | null;
  trailing_mean_3: number | null;
  trailing_mean_6: number | null;
  trailing_mean_12: number | null;
  trailing_median_12: number | null;
  exp_weighted_avg_12: number | null;
  expected_value: number;
  actual_value: number;
  missing_amount: number;
  missing_pct: number;
  baseline_share_pct: number;
  severity: string;
  recommendation: string;
}

export interface MissedFilingsRefreshInfo {
  last_refresh_at: string | null;
  data_min_month: string | null;
  data_max_month: string | null;
  snapshot_row_count: number;
  refresh_duration_seconds: number | null;
}

export interface MissedFilingsResponse {
  items: MissedFilingItem[];
  count: number;
  total: number;
  limit: number | null;
  offset: number;
  has_more: boolean;
  refresh_info: MissedFilingsRefreshInfo;
}

/* ── Auth and account types ── */

export interface SessionUser {
  user_id: string;
  email: string;
  display_name: string | null;
  job_title: string | null;
  organization_name: string | null;
}

export interface AuthSessionResponse {
  authenticated: boolean;
  user: SessionUser | null;
}

export interface MagicLinkRequestResponse {
  ok: boolean;
  message: string;
}

export interface AccountProfile {
  user_id: string;
  email: string;
  display_name: string | null;
  job_title: string | null;
  organization_name: string | null;
  marketing_opt_in: boolean;
}

export interface ForecastPreferences {
  default_city_copo?: string | null;
  default_county_name?: string | null;
  default_tax_type?: string | null;
  forecast_model?: string | null;
  forecast_horizon_months?: number | null;
  forecast_lookback_months?: number | null;
  forecast_confidence_level?: number | null;
  forecast_indicator_profile?: string | null;
  forecast_scope?: string | null;
  forecast_activity_code?: string | null;
}

export interface JurisdictionInterest {
  interest_id: string;
  interest_type: string;
  copo: string | null;
  county_name: string | null;
  label: string;
}

export interface JurisdictionInterestsResponse {
  items: JurisdictionInterest[];
}

export interface SavedAnomaly {
  saved_anomaly_id: string;
  copo: string;
  tax_type: string;
  anomaly_date: string;
  anomaly_type: string;
  activity_code: string | null;
  status: string;
  note: string | null;
  city_name: string | null;
}

export interface SavedAnomaliesResponse {
  items: SavedAnomaly[];
}

export interface SavedMissedFiling {
  saved_missed_filing_id: string;
  copo: string;
  tax_type: string;
  anomaly_date: string;
  activity_code: string;
  baseline_method: string;
  expected_value: number | null;
  actual_value: number | null;
  missing_amount: number | null;
  missing_pct: number | null;
  status: string;
  note: string | null;
  city_name: string | null;
}

export interface SavedMissedFilingsResponse {
  items: SavedMissedFiling[];
}

/* ── Statewide NAICS sector trends ── */

export interface SectorMonthlyData {
  year: number;
  month: number;
  total: number;
}

export interface NaicsSectorItem {
  sector: string;
  sector_name: string | null;
  monthly_data: SectorMonthlyData[];
}

export interface NaicsSectorsResponse {
  tax_type: string;
  sectors: NaicsSectorItem[];
  count: number;
}

/* ── View interface ── */

export interface View {
  render(container: HTMLElement, params: Record<string, string>): void;
  destroy(): void;
}
