# Database Design

## Primary Design Principles

- PostgreSQL is the runtime source of truth
- municipal analytics are query-first, not ORM-first
- forecasts must be reproducible, not just cached point estimates
- the schema should support both municipality-level and NAICS-level forecasting

## Stable Core Tables

- `jurisdictions`
- `ledger_records`
- `naics_records`
- `anomalies`
- `naics_codes`
- `data_imports`

These support the current operational UI and analysis workflows.

## Forecasting Tables

### Legacy

- `forecasts`

Still present for compatibility, but not the preferred long-term shape.

### Preferred

- `forecast_runs`
- `forecast_predictions`
- `forecast_backtests`
- `economic_indicators`

This structure allows:

- persisted explainability
- model comparison
- backtesting by run
- indicator provenance
- municipal and industry drill-down

## Forecast Run Grain

One run should be uniquely understood by:

- `copo`
- `tax_type`
- optional `activity_code`
- `series_scope`
- `requested_model`
- `selected_model`
- `horizon_months`
- `lookback_months`
- `confidence_level`
- `indicator_profile`

## Index Expectations

Must stay fast for:

- `ledger_records (copo, tax_type, voucher_date)`
- `naics_records (copo, tax_type, year, month, activity_code)`
- `forecast_predictions (run_id, model_type, target_date)`
- `forecast_backtests (run_id, model_type)`
- `economic_indicators (indicator_family, geography_type, geography_key, period_date)`

## Data Quality Requirements

Forecasting depends on monthly continuity, so the database design plan needs to keep supporting:

- dedupe on natural keys
- gap detection by month
- stale-series detection
- source provenance

## Follow-On Design Work

- [ ] decide whether the legacy `forecasts` table should be retired after migration confidence
- [ ] add explicit import lineage from raw OkTAP file -> parsed record batch -> persisted rows
- [ ] decide whether high-volume NAICS tables need partitioning by year
- [ ] add formal backup/restore rehearsal documentation tied to this schema
