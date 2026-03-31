# MuniRev Data Import Guide

## Overview

MuniRev ingests municipal tax data from the Oklahoma Tax Commission's public reporting system. Data arrives in two formats: **Ledger Reports** (monthly revenue by jurisdiction) and **NAICS Reports** (monthly revenue by industry code).

This guide describes the expected data format for each report type and how to import data into the MuniRev database.

## Data Format: Ledger Reports

Ledger reports contain monthly tax revenue for a city or county. Each report covers one tax type (Sales, Use, or Lodging).

### Required Columns

| Column | Type | Description | Example |
|---|---|---|---|
| Copo | Text (4 digits) | OkTAP jurisdiction code | 0955 |
| Tax Rate | Decimal | Local tax rate | 0.04 |
| Current Month Collection | Decimal | Gross collections | 2301550.28 |
| Refunded | Decimal | Refunds issued | 0.00 |
| Suspended Monies | Decimal | Amounts in suspense | 0.00 |
| Apportioned | Decimal | Distributed amount | 2301550.28 |
| Revolving Fund | Decimal | Fund deduction (usually negative) | -11507.75 |
| Interest Returned | Decimal | Interest earned | 2892.90 |
| **Returned** | **Decimal** | **Net revenue (primary metric)** | **2292935.43** |
| Voucher Date | Date (ISO) | Payment date | 2025-07-09 |

### File Format

XML SpreadsheetML (.xls extension). This is an XML file, not binary Excel.

```xml
<?xml version="1.0" encoding="utf-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
  <Worksheet ss:Name="Sheet0">
    <Table>
      <Row><!-- Header row -->
        <Cell><Data ss:Type="String">Copo</Data></Cell>
        <Cell><Data ss:Type="String">Tax Rate</Data></Cell>
        <!-- ... all 10 columns ... -->
      </Row>
      <Row><!-- Data rows -->
        <Cell><Data ss:Type="String">0955</Data></Cell>
        <Cell><Data ss:Type="Number">0.04</Data></Cell>
        <!-- ... -->
      </Row>
      <!-- Last row is totals (empty Copo) — skipped during import -->
    </Table>
  </Worksheet>
</Workbook>
```

### Notes

- The last row in each file is a totals row with an empty Copo field. This row is excluded during import.
- Voucher dates are in ISO format: `YYYY-MM-DDTHH:MM:SS` (e.g., `2025-07-09T00:00:00`)
- All numeric values are strings in the XML that must be parsed to decimals
- One file typically contains all months for a single year, for all cities of one jurisdiction type (city or county)

---

## Data Format: NAICS Reports

NAICS reports break down monthly tax revenue by 6-digit NAICS industry code. Available for Sales and Use tax only (not Lodging).

### Required Columns

| Column | Type | Description | Example |
|---|---|---|---|
| Copo | Text (4 digits) | OkTAP jurisdiction code | 0955 |
| Sector | Text (2 digits) | NAICS sector code | 22 |
| Activity Code | Text (6 digits) | NAICS industry code | 221111 |
| Activity Code Description | Text | Industry name | Hydroelectric Power Generation |
| Tax Rate | Decimal | Local tax rate | 0.04 |
| Sector Total | Decimal | Current month revenue | 65119.22 |
| Year To Date | Decimal | Cumulative YTD revenue | 674563.20 |

### File Format

Same XML SpreadsheetML format as Ledger reports.

### Notes

- Each file covers one month for one tax type
- The Sector field may be "UNCLASSIFIED" with an empty Activity Code
- ~470 unique NAICS codes per city per month (varies by city size)
- The last row is a totals row (empty Copo) — excluded during import

---

## Database Schema

### Ledger Records Table

```sql
CREATE TABLE ledger_records (
    id BIGSERIAL PRIMARY KEY,
    copo VARCHAR(10) NOT NULL,
    tax_type VARCHAR(10) NOT NULL,  -- 'sales', 'use', or 'lodging'
    voucher_date DATE NOT NULL,
    tax_rate NUMERIC(10, 4),
    current_month_collection NUMERIC(15, 2),
    refunded NUMERIC(15, 2),
    suspended_monies NUMERIC(15, 2),
    apportioned NUMERIC(15, 2),
    revolving_fund NUMERIC(15, 2),
    interest_returned NUMERIC(15, 2),
    returned NUMERIC(15, 2) NOT NULL,
    UNIQUE(copo, tax_type, voucher_date)
);
```

### NAICS Records Table

```sql
CREATE TABLE naics_records (
    id BIGSERIAL PRIMARY KEY,
    copo VARCHAR(10) NOT NULL,
    tax_type VARCHAR(10) NOT NULL,  -- 'sales' or 'use'
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    activity_code VARCHAR(20) NOT NULL,
    activity_code_description TEXT,
    sector VARCHAR(15) NOT NULL,
    tax_rate NUMERIC(10, 4),
    sector_total NUMERIC(15, 2),
    year_to_date NUMERIC(15, 2),
    UNIQUE(copo, tax_type, year, month, activity_code)
);
```

### Jurisdictions Table

```sql
CREATE TABLE jurisdictions (
    copo VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    jurisdiction_type VARCHAR(10) NOT NULL,  -- 'city' or 'county'
    county_name VARCHAR(255),
    population INTEGER
);
```

---

## Import API

MuniRev provides API endpoints for importing data files:

### Upload Ledger Report
```
POST /api/oktap/import/ledger
Form data:
  - file: .xls file
  - tax_type: "sales" | "use" | "lodging"
```

### Upload NAICS Report
```
POST /api/oktap/import/naics
Form data:
  - file: .xls file
  - tax_type: "sales" | "use"
  - year: integer (e.g., 2025)
  - month: integer (1-12)
```

### Auto-Detect and Import
```
POST /api/oktap/import/auto
Form data:
  - file: .xls file
  - tax_type: tax type
  - year: (required for NAICS)
  - month: (required for NAICS)
```

### Bulk Import
```
POST /api/oktap/import/bulk
Form data:
  - files: multiple .xls files
  - tax_type: tax type
  - year: (for NAICS files)
  - month: (for NAICS files)
```

All import endpoints use `ON CONFLICT DO UPDATE` for idempotent re-imports.

---

## Data Source

Oklahoma Tax Commission public reports are available at:
- **oklahoma.gov/tax/reporting-resources/reports.html**

The Copo code directory (mapping codes to city/county names) is published quarterly by the Oklahoma Tax Commission.
