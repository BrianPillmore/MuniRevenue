# Database Design — MuniRev

## Overview

PostgreSQL 16 stores all Oklahoma municipal tax data from OkTAP. Designed for time-series queries across ~677 jurisdictions with monthly granularity.

## Entity Relationship

```
jurisdictions (copo PK)
    │
    ├──< ledger_records (copo FK, tax_type, voucher_date)
    │       UNIQUE(copo, tax_type, voucher_date)
    │
    ├──< naics_records (copo FK, tax_type, year, month, activity_code)
    │       UNIQUE(copo, tax_type, year, month, activity_code)
    │
    ├──< anomalies (copo FK)
    │
    └──< forecasts (copo FK)
            UNIQUE(copo, tax_type, forecast_date, model_type)

naics_codes (code PK) — reference table, not FK'd (some codes are UNCLASSIFIED)

data_imports (id PK) — audit trail, referenced by ledger/naics records
```

## Table Details

### jurisdictions
Oklahoma cities and counties. Primary key is the OkTAP `copo` code.

| Column | Type | Notes |
|---|---|---|
| copo | VARCHAR(10) PK | OkTAP jurisdiction code (e.g., "0955" = Yukon) |
| name | VARCHAR(255) | City/county name |
| jurisdiction_type | VARCHAR(10) | 'city' or 'county' |
| county_name | VARCHAR(255) | Parent county for cities |
| population | INTEGER | Latest known population |
| latitude/longitude | NUMERIC(9,6) | For map display |

### ledger_records
Monthly revenue per jurisdiction per tax type. This is the core time-series table.

| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| copo | VARCHAR(10) FK | -> jurisdictions |
| tax_type | VARCHAR(10) | 'lodging', 'sales', or 'use' |
| voucher_date | DATE | Monthly payment date |
| returned | NUMERIC(15,2) | Net revenue — the key metric |
| tax_rate | NUMERIC(10,4) | Local tax rate |
| current_month_collection | NUMERIC(15,2) | Gross collections |
| refunded/suspended/apportioned | NUMERIC(15,2) | Adjustment columns |
| revolving_fund | NUMERIC(15,2) | Fund deduction (usually negative) |
| interest_returned | NUMERIC(15,2) | Interest earned |

**Key query**: `WHERE copo = ? AND tax_type = ? ORDER BY voucher_date` for time-series charts.

### naics_records
Monthly revenue by industry. ~470 rows per city per month per tax type.

| Column | Type | Notes |
|---|---|---|
| id | BIGSERIAL PK | |
| copo | VARCHAR(10) FK | -> jurisdictions |
| tax_type | VARCHAR(10) | 'sales' or 'use' only |
| year | INTEGER | Report year |
| month | INTEGER | Report month (1-12) |
| activity_code | VARCHAR(10) | 6-digit NAICS code |
| sector | VARCHAR(15) | 2-digit sector or 'UNCLASSIFIED' |
| sector_total | NUMERIC(15,2) | Current month revenue |
| year_to_date | NUMERIC(15,2) | Cumulative YTD revenue |

**Key queries**:
- Top industries: `WHERE copo = ? AND year = ? AND month = ? ORDER BY sector_total DESC`
- Industry trend: `WHERE copo = ? AND activity_code = ? ORDER BY year, month`
- Cross-city: `WHERE activity_code = ? AND year = ? AND month = ?`

### anomalies
Detected anomalies flagged for investigation.

| Column | Type | Notes |
|---|---|---|
| severity | VARCHAR(10) | 'low', 'medium', 'high', 'critical' |
| anomaly_type | VARCHAR(50) | 'mom_spike', 'yoy_drop', 'missing_data', 'naics_shift' |
| expected_value | NUMERIC(15,2) | What the model predicted |
| actual_value | NUMERIC(15,2) | What was reported |
| deviation_pct | NUMERIC(10,2) | % deviation from expected |
| investigated | BOOLEAN | Has a human reviewed this? |

### forecasts
Stored forecast projections per jurisdiction.

| Column | Type | Notes |
|---|---|---|
| forecast_date | DATE | Future date being predicted |
| projected_returned | NUMERIC(15,2) | Point estimate |
| lower_bound/upper_bound | NUMERIC(15,2) | 95% confidence interval |
| model_type | VARCHAR(50) | 'seasonal_trend', 'prophet', 'arima' |

## Indexing Strategy

1. **Composite**: (copo, tax_type, voucher_date) — primary ledger query path
2. **Composite**: (copo, tax_type, year, month) — primary NAICS query path
3. **Single**: (activity_code) — cross-city NAICS lookups
4. **Single**: (voucher_date) — statewide time-range queries
5. **Partial**: WHERE investigated = FALSE on anomalies — dashboard queries

## Import Semantics

**Upsert on import**: `INSERT ON CONFLICT (unique_key) DO UPDATE SET ...`

This means re-importing the same file for the same period is safe — it updates existing records rather than creating duplicates. The `data_imports` table logs each import for audit.

## Scaling Notes

- At full statewide coverage: ~5-10 GB total
- Monthly growth: ~500K NAICS rows, ~2K ledger rows
- No partitioning needed initially; add by year if queries slow down
- Materialized views for dashboard aggregates (refresh on import)
