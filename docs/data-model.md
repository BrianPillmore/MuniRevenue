# MuniRev Data Model

## Data Sources

All data originates from the Oklahoma Tax Commission's OkTAP system at `oktap.tax.ok.gov`.

### Ledger Reports

Monthly tax revenue by jurisdiction. Available for three tax types: **lodging**, **sales**, and **use**. Each report is run for a specific city or county (by copo code), for a given year. Returns all months in that year with data.

| Column | Type | Description |
|---|---|---|
| Copo | string | City/county code (e.g., "0955" = Yukon) |
| Tax Rate | decimal | Local tax rate (e.g., 0.04 = 4%) |
| Current Month Collection | decimal | Gross collections for the period |
| Refunded | decimal | Refunds issued |
| Suspended Monies | decimal | Amounts held in suspense |
| Apportioned | decimal | Amount after apportionment |
| Revolving Fund | decimal | Revolving fund deduction (typically negative) |
| Interest Returned | decimal | Interest earned |
| **Returned** | decimal | **Net amount returned to jurisdiction — the key revenue figure** |
| Voucher Date | date | Payment date (monthly, e.g., 2025-07-09) |

### NAICS Reports (State Tax by NAICS)

Monthly tax revenue broken down by industry (NAICS code). Available for **sales** and **use** tax types. Run for a specific jurisdiction, year, and month.

| Column | Type | Description |
|---|---|---|
| Copo | string | City/county code |
| Sector | string | 2-digit NAICS sector (e.g., "22" = Utilities) |
| Activity Code | string | 6-digit NAICS code (e.g., "221111") |
| Activity Code Description | string | Industry name |
| Tax Rate | decimal | Local tax rate |
| Sector Total | decimal | Current month collection for this industry |
| Year To Date | decimal | Cumulative collection for this industry YTD |

**Scale per city per month:** ~470 unique NAICS codes (Yukon example).

## Export Format

OkTAP exports are `.xls` files in XML SpreadsheetML format (not binary Excel). Each file contains:
- XML declaration with `<?mso-application progid="Excel.Sheet"?>`
- One `Worksheet` with a `Table` of `Row` elements
- First row is headers
- Last row is a totals row (empty Copo) — excluded during import
- Numeric values are strings that must be parsed to decimals

## Database Schema

See `backend/app/db/schema.sql` for the full PostgreSQL schema.

### Key Tables

- **jurisdictions** — Oklahoma cities and counties with copo codes
- **ledger_records** — Monthly revenue time series (unique on copo + tax_type + voucher_date)
- **naics_records** — Monthly industry breakdown (unique on copo + tax_type + year + month + activity_code)
- **naics_codes** — Reference table for NAICS code descriptions
- **data_imports** — Audit trail of imported files
- **anomalies** — Detected anomalies with severity and investigation status
- **forecasts** — Stored forecast projections with confidence intervals

### Key Relationships

```
jurisdictions (copo)
  ├── ledger_records (many, by copo + tax_type + voucher_date)
  ├── naics_records (many, by copo + tax_type + year + month + activity_code)
  ├── anomalies (many)
  └── forecasts (many)
```

## Copo Codes

The `copo` field is the Oklahoma Tax Commission's jurisdiction identifier. Examples:
- `0955` = City of Yukon
- `0750` = Oklahoma City
- `0900` = Tulsa

A full list is maintained in `scripts/seed_jurisdictions.py` and expanded automatically as new codes appear in imported data.
