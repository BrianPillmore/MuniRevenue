# MuniRev Data Import Guide

## Overview

MuniRev ingests municipal tax data from the Oklahoma Tax Commission public reporting system.

Primary import families:

- ledger reports
- NAICS reports

This guide describes:

- expected file format
- database targets
- import endpoints
- operational auth requirements

## Source Formats

### Ledger Reports

Ledger reports contain monthly tax revenue by jurisdiction.

Each report covers one tax type:

- sales
- use
- lodging

Required columns:

| Column | Type | Description | Example |
|---|---|---|---|
| Copo | Text (4 digits) | OkTAP jurisdiction code | 0955 |
| Tax Rate | Decimal | Local tax rate | 0.04 |
| Current Month Collection | Decimal | Gross collections | 2301550.28 |
| Refunded | Decimal | Refunds issued | 0.00 |
| Suspended Monies | Decimal | Amounts in suspense | 0.00 |
| Apportioned | Decimal | Distributed amount | 2301550.28 |
| Revolving Fund | Decimal | Fund deduction | -11507.75 |
| Interest Returned | Decimal | Interest earned | 2892.90 |
| Returned | Decimal | Net revenue | 2292935.43 |
| Voucher Date | Date | Payment date | 2025-07-09 |

### NAICS Reports

NAICS reports break down monthly tax revenue by 6-digit NAICS code.

Available tax types:

- sales
- use

Lodging is not supported at the NAICS level in the current pipeline.

Required columns:

| Column | Type | Description | Example |
|---|---|---|---|
| Copo | Text (4 digits) | OkTAP jurisdiction code | 0955 |
| Sector | Text (2 digits) | NAICS sector code | 22 |
| Activity Code | Text (6 digits) | NAICS industry code | 221111 |
| Activity Code Description | Text | Industry label | Hydroelectric Power Generation |
| Tax Rate | Decimal | Local tax rate | 0.04 |
| Sector Total | Decimal | Current month revenue | 65119.22 |
| Year To Date | Decimal | Cumulative YTD revenue | 674563.20 |

## File Format

Both report families are imported from XML SpreadsheetML files that usually carry an `.xls` extension.

These are XML spreadsheets, not binary Excel workbooks.

Important parsing notes:

- the last row is usually a totals row with empty `Copo`
- totals rows are skipped
- voucher dates arrive in ISO-like timestamp format
- numeric values arrive as strings and must be parsed

## Database Targets

Primary destination tables:

- `ledger_records`
- `naics_records`
- `jurisdictions`

Related downstream consumers:

- `anomalies`
- `missed_filing_candidates`
- forecasting tables

## Import API

Import endpoints live under `backend/app/api/oktap.py`.

### Upload ledger report

`POST /api/oktap/import/ledger`

Form data:

- `file`
- `tax_type`

### Upload NAICS report

`POST /api/oktap/import/naics`

Form data:

- `file`
- `tax_type`
- `year`
- `month`

### Auto-detect and import

`POST /api/oktap/import/auto`

Form data:

- `file`
- `tax_type`
- `year` for NAICS
- `month` for NAICS

### Bulk import

`POST /api/oktap/import/bulk`

Form data:

- `files`
- `tax_type`
- `year` for NAICS files
- `month` for NAICS files

All import endpoints are idempotent and use `ON CONFLICT DO UPDATE`.

## Auth Requirements

Import endpoints are not public.

Current authorization:

- imports require `data:import`
- import status / read-side operational views use `api:read`

That means:

- browser users should reach imports only through an authenticated/admin workflow
- machine workflows should use `token` or `proxy` mode with the right scope bundle

## Operational Expectations

When running imports:

- validate tax type before upload
- validate month/year for NAICS files
- preserve raw source files for audit if possible
- rerun downstream refreshes after meaningful data changes

In particular, after large NAICS updates, refresh:

- anomaly pipelines
- missed-filings cache
- forecast-dependent derived outputs as needed

## Source Of Truth

Runtime source of truth is now PostgreSQL.

Parsed files under `data/parsed/` remain useful for:

- audit
- reproducibility
- troubleshooting

But dashboards and feature APIs should be treated as database-driven.

## Data Source

Oklahoma Tax Commission public reporting:

- `https://oklahoma.gov/tax/reporting-resources/reports.html`

The Copo directory is published separately and should be refreshed periodically.
