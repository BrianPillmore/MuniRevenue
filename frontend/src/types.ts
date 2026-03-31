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
  copo: number;
  name: string;
  jurisdiction_type: string;
  county_name: string;
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
  earliest_date: string;
  latest_date: string;
  total_returned: number;
}

export interface CityDetailResponse {
  copo: number;
  name: string;
  jurisdiction_type: string;
  county_name: string;
  tax_type_summaries: TaxTypeSummary[];
  naics_record_count: number;
}

export interface LedgerRecord {
  voucher_date: string;
  returned: number;
  mom_pct: number | null;
  yoy_pct: number | null;
  tax_rate: number | null;
}

export interface CityLedgerResponse {
  copo: number;
  tax_type: string;
  records: LedgerRecord[];
  count: number;
}

export interface TopCityBySales {
  copo: number;
  name: string;
  total_sales_returned: number;
}

export interface OverviewResponse {
  jurisdictions_with_data: number;
  total_ledger_records: number;
  total_naics_records: number;
  earliest_ledger_date: string;
  latest_ledger_date: string;
  top_cities_by_sales: TopCityBySales[];
}
