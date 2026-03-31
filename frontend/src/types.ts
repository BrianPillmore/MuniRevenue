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

export interface CountySummaryResponse {
  county: string;
  tax_type: string;
  total_returned: number;
  jurisdiction_count: number;
  top_jurisdictions: TopCityBySales[];
}

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

export interface CityForecastPoint {
  date: string;
  projected_returned: number;
  lower_bound: number;
  upper_bound: number;
}

export interface ForecastResponse {
  copo: string;
  tax_type: string;
  forecast: CityForecastPoint[];
  count: number;
}

export interface AnomalyItem {
  copo: string;
  city_name: string;
  tax_type: string;
  anomaly_date: string;
  severity: string;
  description: string;
  deviation_pct: number;
}

export interface AnomaliesResponse {
  items: AnomalyItem[];
  count: number;
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
