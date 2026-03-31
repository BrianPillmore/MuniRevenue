# MuniRev Data Model

## Source Systems

Primary operational source:

- Oklahoma Tax Commission OkTAP exports

Supporting source families for forecasting:

- labor indicators
- retail proxies
- housing / construction indicators

The parsed CSV files under `data/parsed/` are useful for audit and troubleshooting, but the application now treats PostgreSQL as the runtime source of truth.

## Core Tables

### `jurisdictions`

Reference table for Oklahoma cities and counties.

Key columns:

- `copo`
- `name`
- `jurisdiction_type`
- `county_name`
- `population`

### `ledger_records`

Monthly revenue time series by jurisdiction and tax type.

Natural grain:

- `(copo, tax_type, voucher_date)`

Important revenue field:

- `returned`

Supported tax types:

- `sales`
- `use`
- `lodging`

### `naics_records`

Monthly industry breakdown for sales and use tax.

Natural grain:

- `(copo, tax_type, year, month, activity_code)`

Important fields:

- `activity_code`
- `activity_code_description`
- `sector`
- `sector_total`
- `year_to_date`

### `anomalies`

Stored anomaly detection output for follow-up and UI presentation.

Important fields:

- `copo`
- `tax_type`
- `anomaly_type`
- `period` / `anomaly_date`
- `severity`
- `expected_value`
- `actual_value`
- `deviation_pct`

## Forecasting Tables

### `forecasts`

Legacy simple forecast storage. Still present for compatibility, but no longer the preferred structure.

### `forecast_runs`

One row per forecast request / persisted run.

Important fields:

- `copo`
- `tax_type`
- `activity_code`
- `series_scope`
- `requested_model`
- `selected_model`
- `horizon_months`
- `lookback_months`
- `confidence_level`
- `indicator_profile`
- `training_start`
- `training_end`
- `feature_set`
- `model_parameters`
- `explanation`
- `data_quality`
- `selected`

### `forecast_predictions`

One row per run, model, and target month.

Natural grain:

- `(run_id, model_type, target_date)`

Important fields:

- `projected_value`
- `lower_bound`
- `upper_bound`

### `forecast_backtests`

Stores model evaluation output for a forecast run.

Important fields:

- `run_id`
- `model_type`
- `mape`
- `smape`
- `mae`
- `rmse`
- `coverage`
- `fold_count`
- `holdout_description`

### `economic_indicators`

Normalized monthly indicators used for driver-aware forecasting.

Natural grain:

- `(geography_type, geography_key, indicator_family, indicator_name, period_date)`

Important fields:

- `value`
- `source_name`
- `source_vintage`
- `is_forecast`
- `metadata`

## Forecasting Grain Rules

### Municipal forecasts

Primary grain:

- `(copo, tax_type)`

### Industry forecasts

NAICS grain:

- `(copo, tax_type, activity_code)`

Eligibility rules:

- `sales` and `use`: advanced models require at least `36` monthly observations
- `lodging`: advanced models require at least `24` monthly observations
- NAICS-level forecasts require at least `24` observations plus non-trivial recent share

## Data Quality Metadata

Forecast runs record quality signals that affect model eligibility and UI warnings:

- structural gaps
- stale latest month
- sparse histories
- unresolved systemic gaps
- fallback-only status

## Key Relationships

```
jurisdictions
  ├── ledger_records
  ├── naics_records
  ├── anomalies
  ├── forecasts
  └── forecast_runs
         ├── forecast_predictions
         └── forecast_backtests

economic_indicators
  └── linked by geography metadata and forecast run feature sets
```

## Operational Notes

- The app reads directly from PostgreSQL for dashboards and forecasts.
- Forecasts are reproducible because run metadata, predictions, and backtests are persisted.
- Economic indicators are modeled as first-class data, not baked into one-off training artifacts.
