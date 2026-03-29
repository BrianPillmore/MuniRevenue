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
