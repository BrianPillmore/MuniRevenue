# MuniRev Data Model

## Source Systems

Primary operational source:

- Oklahoma Tax Commission OkTAP exports

Supporting source families for forecasting:

- labor indicators
- retail proxies
- housing / construction indicators

The runtime source of truth is PostgreSQL.

## Core Revenue Tables

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

Important field:

- `returned`

Tax types:

- `sales`
- `use`
- `lodging`

### `naics_records`

Monthly industry revenue for sales and use tax.

Natural grain:

- `(copo, tax_type, year, month, activity_code)`

Important fields:

- `activity_code`
- `activity_code_description`
- `sector`
- `sector_total`
- `year_to_date`

### `anomalies`

Stored anomaly detection output used by the product UI.

Important fields:

- `copo`
- `tax_type`
- `anomaly_type`
- `anomaly_date`
- `severity`
- `expected_value`
- `actual_value`
- `deviation_pct`

## Forecasting Tables

### `forecasts`

Legacy forecast storage. Still present for compatibility, but not the preferred structure.

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

### `forecast_backtests`

Evaluation output for a forecast run.

Important fields:

- `run_id`
- `model_type`
- `mape`
- `smape`
- `mae`
- `rmse`
- `coverage`
- `fold_count`

### `economic_indicators`

Normalized monthly indicators used for driver-aware forecasting.

Natural grain:

- `(geography_type, geography_key, indicator_family, indicator_name, period_date)`

## Missed-Filings Tables

### `missed_filing_candidates`

Materialized rolling-window cache for the missed-filings feature.

Grain:

- city / tax type / month / 6-digit NAICS candidate row

Important fields include:

- `copo`
- `city_name`
- `tax_type`
- `anomaly_date`
- `activity_code`
- `activity_description`
- actual and expected values
- multiple baseline variants
- hybrid expected values
- missing amount / missing percent
- city baseline share percent
- severity

### `missed_filing_candidates_refresh_meta`

Snapshot metadata for the live missed-filings cache.

Important fields:

- refresh timestamp
- runtime seconds
- snapshot row count
- min month
- max month

## Browser Auth / Account Tables

### `app_users`

One row per first-party browser account.

Important fields:

- `email`
- `email_normalized`
- `display_name`
- `job_title`
- `organization_name`
- `marketing_opt_in`
- `email_verified_at`
- `last_login_at`
- `status`

### `user_magic_links`

One row per issued one-time login link.

Important fields:

- `user_id`
- `token_hash`
- `next_path`
- `requested_ip`
- `requested_user_agent_hash`
- `expires_at`
- `consumed_at`

### `user_sessions`

Browser session records.

Important fields:

- `user_id`
- `session_token_hash`
- `created_at`
- `last_seen_at`
- `expires_at`
- `revoked_at`
- request IP metadata

### `user_profile_preferences`

Saved forecast defaults and related user settings.

Important fields:

- `default_city_copo`
- `default_county_name`
- `default_tax_type`
- `forecast_model`
- `forecast_horizon_months`
- `forecast_lookback_months`
- `forecast_confidence_level`
- `forecast_indicator_profile`
- `forecast_scope`
- `forecast_activity_code`

### `user_jurisdiction_interests`

User-linked cities and counties of interest.

### `user_saved_anomalies`

Saved anomaly follow-up queue.

Important fields:

- anomaly identity keys
- `status`
- `note`
- `city_name`

### `user_saved_missed_filings`

Saved missed-filing follow-up queue.

Important fields:

- candidate identity keys
- `baseline_method`
- `status`
- `note`
- `city_name`

## Forecasting Grain Rules

### Municipal forecasts

Primary grain:

- `(copo, tax_type)`

### Industry forecasts

Primary grain:

- `(copo, tax_type, activity_code)`

Eligibility rules:

- `sales` and `use`: advanced models require at least `36` monthly observations
- `lodging`: advanced models require at least `24` monthly observations
- NAICS forecasts require sufficient history plus non-trivial recent share

## Relationships

```
jurisdictions
  ├── ledger_records
  ├── naics_records
  ├── anomalies
  ├── missed_filing_candidates
  ├── forecasts
  ├── forecast_runs
  ├── user_profile_preferences
  ├── user_jurisdiction_interests
  ├── user_saved_anomalies
  └── user_saved_missed_filings

forecast_runs
  ├── forecast_predictions
  └── forecast_backtests

app_users
  ├── user_magic_links
  ├── user_sessions
  ├── user_profile_preferences
  ├── user_jurisdiction_interests
  ├── user_saved_anomalies
  └── user_saved_missed_filings
```

## Operational Notes

- PostgreSQL is the runtime source of truth.
- Forecasts are reproducible because runs, predictions, and backtests are persisted.
- Missed-filings is driven from a materialized cache plus refresh metadata.
- User-specific follow-up workflows now persist inside the application database.
