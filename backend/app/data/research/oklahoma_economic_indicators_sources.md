# Oklahoma Economic Indicators: Data Source Research
## MuniRevenue Municipal Revenue Forecasting Platform

**Research Date:** 2026-03-29
**Researcher:** Data Research Agent
**Purpose:** Identify and document publicly available data sources for Oklahoma economic
indicators to enhance municipal revenue forecasting accuracy.

---

## Executive Summary

This document catalogs 28 economic indicator series across 4 categories (Labor,
Retail, Housing/Construction, Population/Demographic) available from 7 primary data
providers. The strongest candidates for automated ingestion are FRED API series (single
API, 20+ Oklahoma series) and BLS API v2 (county-level labor data). Together these
cover the indicators most correlated with municipal sales/use tax revenue.

**Priority ranking for implementation:**

| Priority | Source        | Indicators | Automation | Revenue Correlation |
|----------|---------------|------------|------------|---------------------|
| 1        | FRED API      | 20+        | Excellent  | High                |
| 2        | BLS API v2    | 10+        | Excellent  | High                |
| 3        | Census BPS    | 4+         | Good       | Medium-High         |
| 4        | HUD SOCDS     | 2+         | Good       | Medium              |
| 5        | Zillow ZHVI   | 3+         | Good       | Medium              |
| 6        | Census PEP    | 2          | Moderate   | Medium              |
| 7        | OK Treasurer  | 5+         | Poor (PDF) | Very High           |

---

## API Key Requirements Summary

| Provider             | API Key Required | Cost | Registration URL                                      |
|----------------------|------------------|------|-------------------------------------------------------|
| FRED (St. Louis Fed) | Yes              | Free | https://fredaccount.stlouisfed.org/apikeys             |
| BLS                  | Yes (for v2)     | Free | https://data.bls.gov/registrationEngine/              |
| Census Bureau        | Yes              | Free | https://api.census.gov/data/key_signup.html            |
| HUD                  | No (Open Data)   | Free | N/A (ArcGIS REST endpoint)                            |
| Zillow               | No (CSV bulk)    | Free | N/A (direct download or Econ Data API)                |

---

## 1. LABOR INDICATORS

Labor market health is the single strongest leading indicator of municipal sales tax
revenue. Employment drives consumer spending, which drives taxable retail sales.

---

### 1.1 Monthly Unemployment Rate (State Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | U.S. Bureau of Labor Statistics (BLS) via FRED                     |
| **Program**         | Local Area Unemployment Statistics (LAUS)                          |
| **FRED Series ID**  | `OKUR` (seasonally adjusted), `OKURN` (not seasonally adjusted)    |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free registration at fredaccount.stlouisfed.org             |
| **Format**          | JSON, XML                                                          |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~3-4 weeks after reference month                                   |
| **History**         | January 1976 to present                                            |
| **Retrieval**       | REST API GET request                                               |

**Sample API Call:**
```
GET https://api.stlouisfed.org/fred/series/observations?
    series_id=OKUR
    &api_key={YOUR_KEY}
    &file_type=json
    &observation_start=2020-01-01
    &observation_end=2026-03-01
```

**Revenue Relevance:** Unemployment rate is inversely correlated with consumer
spending. A 1-point rise in unemployment typically leads to a 0.5-1.5% decline in
retail sales within 1-2 months, directly impacting sales tax collections. This is the
single most important leading indicator for municipal revenue forecasting.

**Database Mapping:**
```
geography_type = 'state'
geography_key  = 'OK'
indicator_family = 'labor'
indicator_name = 'unemployment_rate_sa'
source_name = 'BLS LAUS via FRED (OKUR)'
```

---

### 1.2 Monthly Unemployment Rate (County Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS LAUS via FRED                                                  |
| **FRED Series IDs** | Pattern: `{OK}{COUNTY}URN` or `LAUCN40{FIPS}0000000003`           |
| **Examples**        | `OKOKLA9URN` (Oklahoma County), `OKTULS3URN` (Tulsa County)       |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON, XML                                                          |
| **Geography**       | County (all 77 Oklahoma counties)                                  |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~5-6 weeks after reference month                                   |
| **History**         | January 1990 to present                                            |
| **Retrieval**       | REST API GET request (one call per county per series)              |

**Key Oklahoma County FRED Series IDs:**

| County          | FIPS  | FRED Series ID    | Alt Series ID             |
|-----------------|-------|-------------------|---------------------------|
| Oklahoma County | 40109 | OKOKLA9URN        | LAUCN401090000000003A     |
| Tulsa County    | 40143 | OKTULS3URN        | LAUCN401430000000003      |
| Cleveland County| 40027 | OKCLEV5URN        | LAUCN400270000000003      |
| Canadian County | 40017 | OKCANA7URN        | LAUCN400170000000003      |
| Comanche County | 40031 | OKCOMA1URN        | LAUCN400310000000003      |

**Note:** For all 77 counties, use the LAUS series ID format:
`LAUCN40{county_fips_3digit}0000000003` where `03` = unemployment rate.
Measure codes: `03` = unemployment rate, `04` = unemployment count,
`05` = employment count, `06` = labor force count.

**Revenue Relevance:** County-level unemployment is the most granular labor indicator
available and maps directly to municipal geographies. This enables city-specific
revenue forecasting by matching each municipality to its county labor conditions.

**Database Mapping:**
```
geography_type = 'county'
geography_key  = 'Oklahoma County'  -- (or Tulsa County, etc.)
indicator_family = 'labor'
indicator_name = 'unemployment_rate_nsa'
source_name = 'BLS LAUS via FRED (OKOKLA9URN)'
```

---

### 1.3 Monthly Unemployment Rate (MSA Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS LAUS via FRED                                                  |
| **FRED Series IDs** | `OKLA440URN` (OKC MSA NSA), `OKLA440UR` (OKC MSA SA)             |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | MSA (Oklahoma City, Tulsa, Lawton, etc.)                           |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~4-5 weeks                                                         |
| **History**         | January 1990 to present                                            |

**Key Oklahoma MSA Series IDs:**

| MSA                  | CBSA Code | SA Series       | NSA Series       |
|----------------------|-----------|-----------------|------------------|
| Oklahoma City        | 36420     | OKLA440UR       | OKLA440URN       |
| Tulsa                | 46140     | TULS440UR       | TULS440URN       |
| Lawton               | 30020     | LAWT440UR       | LAWT440URN       |

**Revenue Relevance:** MSAs encompass the economic catchment area for major Oklahoma
cities. MSA-level metrics capture commuter-driven economic activity that influences
urban sales tax collections.

---

### 1.4 Total Nonfarm Payroll Employment (State Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS Current Employment Statistics (CES) via FRED                   |
| **FRED Series IDs** | `SMU40000000000000001A` (NSA), `SMU40000000000000001` (SA)         |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~3 weeks after reference month                                     |
| **History**         | 1939 to present                                                    |
| **Retrieval**       | REST API                                                           |

**Revenue Relevance:** Total employment is a coincident indicator of economic activity.
More people employed means more consumer spending and more sales tax revenue. Month-
over-month employment changes are a strong predictor of near-term revenue shifts.

---

### 1.5 Nonfarm Payroll Employment by Sector (State Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS CES via FRED                                                   |
| **Program**         | State and Area Employment (SAE)                                    |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State, select MSAs                                                 |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~3-4 weeks                                                         |

**BLS CES Series ID Structure for Oklahoma:**
Format: `SMU40{area}{industry}{datatype}`
- State FIPS: `40` (Oklahoma)
- Area: `00000` for statewide, `36420` for OKC MSA, `46140` for Tulsa MSA
- Industry: NAICS supersector code (6 digits)
- Datatype: `01` = all employees (thousands)

**Key Sector Series IDs (Oklahoma State):**

| Sector                    | NAICS  | FRED Series ID                |
|---------------------------|--------|-------------------------------|
| Total Nonfarm             | 000000 | SMU40000000000000001          |
| Mining/Logging            | 100000 | SMU40000001000000001          |
| Construction              | 200000 | SMU40000002000000001          |
| Manufacturing             | 300000 | SMU40000003000000001          |
| Trade/Transport/Utilities | 400000 | SMU40000004000000001          |
| Retail Trade              | 420000 | SMU40000004200000001          |
| Professional/Business     | 600000 | SMU40000006000000001          |
| Leisure/Hospitality       | 700000 | SMU40000007000000001          |
| Government                | 900000 | SMU40000009000000001          |

**Revenue Relevance:** Sector-level employment reveals the composition of economic
activity. Retail Trade employment is directly tied to sales tax; Mining/Logging
employment correlates with gross production tax; Construction employment correlates
with building permit activity and use tax on materials. Sector shifts help explain
why aggregate employment may rise while specific revenue streams decline.

---

### 1.6 Initial Unemployment Claims (State Level, Weekly)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | U.S. Employment and Training Administration via FRED               |
| **FRED Series ID**  | `OKICLAIMS` (initial claims), `OKCCLAIMS` (continued claims)      |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Weekly (can aggregate to monthly via FRED aggregation parameter)   |
| **Lag**             | ~1-2 weeks (one of the most timely indicators)                     |
| **History**         | 1986 to present                                                    |

**Sample API Call (with monthly aggregation):**
```
GET https://api.stlouisfed.org/fred/series/observations?
    series_id=OKICLAIMS
    &api_key={YOUR_KEY}
    &file_type=json
    &frequency=m
    &aggregation_method=sum
    &observation_start=2020-01-01
```

**Revenue Relevance:** Initial claims are the most timely leading indicator of labor
market deterioration. A spike in claims precedes unemployment rate increases by 4-6
weeks and sales tax declines by 1-3 months. This is a high-value early warning signal
for revenue forecasting models.

---

### 1.7 Labor Force Participation Rate (State Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS LAUS via FRED                                                  |
| **FRED Series IDs** | `LBSSA40` (SA), `LBSNSA40` (NSA)                                  |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~4 weeks                                                           |
| **History**         | January 1976 to present                                            |

**Revenue Relevance:** Labor force participation captures structural changes in the
workforce that unemployment rate alone misses. A declining participation rate means
fewer potential consumers even if unemployment appears low, which suppresses tax
base growth over time.

---

### 1.8 BLS Direct API Access (Alternative to FRED)

For scenarios requiring bulk county-level labor data or BLS-specific features:

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS Public Data API v2                                             |
| **API Endpoint**    | `https://api.bls.gov/publicAPI/v2/timeseries/data/`               |
| **API Key**         | Yes -- free registration at https://data.bls.gov/registrationEngine/|
| **Format**          | JSON                                                               |
| **Method**          | POST with JSON body                                                |
| **Rate Limit**      | 500 queries/day, 50 series per query, 20 years per query           |
| **Geography**       | State, County, MSA (all Oklahoma counties available)               |

**Sample POST Request Body:**
```json
{
  "seriesid": [
    "LAUCN401090000000003",
    "LAUCN401430000000003",
    "LAUCN400270000000003",
    "LAUCN400170000000003"
  ],
  "startyear": "2020",
  "endyear": "2026",
  "registrationkey": "{YOUR_BLS_API_KEY}"
}
```

**Advantages over FRED for county data:**
- Can request up to 50 county series in a single POST call
- More efficient for bulk retrieval of all 77 Oklahoma counties
- Direct source, no intermediary

**LAUS Series ID Construction for Any Oklahoma County:**
```
LA + U + CN + 40{county_fips_3digit} + 0000000 + {measure_code}

Measure codes:
  03 = unemployment rate
  04 = unemployment (count)
  05 = employment (count)
  06 = labor force (count)
```

---

### 1.9 OESC Direct Data (Oklahoma Employment Security Commission)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Oklahoma Employment Security Commission (OESC)                     |
| **URL**             | https://oklahoma.gov/oesc/labor-market.html                        |
| **API Key**         | N/A -- no public API                                               |
| **Format**          | Excel (XLSX), PDF reports                                          |
| **Geography**       | State, County, MSA                                                 |
| **Frequency**       | Monthly (LAUS, CES), Quarterly (QCEW)                             |
| **Lag**             | Varies; typically 4-8 weeks                                        |
| **History**         | Varies by dataset                                                  |
| **Retrieval**       | Manual download from website                                       |

**Available Datasets:**

1. **LAUS** -- Local Area Unemployment Statistics (same data as BLS, published on
   OESC site): https://oklahoma.gov/oesc/labor-market/local-area-statistics.html

2. **CES** -- Current Employment Statistics:
   https://oklahoma.gov/oesc/labor-market/current-employment-statistics.html

3. **QCEW** -- Quarterly Census of Employment and Wages (county-level establishment
   and wage data): https://oklahoma.gov/oesc/labor-market/qcew.html

4. **Claims Data** -- Initial and continued UI claims (weekly spreadsheet download):
   https://oklahoma.gov/oesc/labor-market/claims-data.html

**Revenue Relevance:** OESC is the original producer of Oklahoma labor data before
it flows to BLS and FRED. The QCEW dataset provides county-level quarterly wages and
establishment counts not available elsewhere, offering a direct measure of the wage
base that drives consumer spending and tax revenue.

**Automation Note:** OESC does not offer a public API. Data must be scraped or manually
downloaded. For automated pipelines, prefer FRED or BLS API for the same underlying
LAUS/CES data. Use OESC only for QCEW data not available via API.

---

## 2. RETAIL INDICATORS

Retail indicators are the most directly correlated with municipal sales tax revenue.
Sales tax is typically the largest single revenue source for Oklahoma municipalities.

---

### 2.1 Monthly State Retail Sales (Oklahoma)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | U.S. Census Bureau Monthly Retail Trade Survey (MRTS) via FRED     |
| **Program**         | Monthly State Retail Sales (MSRS) -- experimental product          |
| **FRED Series IDs** | Pattern: `MSRSOK{NAICS_code}`                                     |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free FRED key                                               |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma) -- NOT available at county/city level             |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~6-8 weeks (experimental release schedule)                         |
| **History**         | January 2019 to present                                            |
| **Retrieval**       | REST API                                                           |

**Oklahoma MSRS Series IDs by NAICS Subsector:**

| Subsector                          | NAICS | FRED Series ID | Data Type      |
|------------------------------------|-------|----------------|----------------|
| Total (excl. nonstore)             | --    | MSRSOKTOTAL    | YoY % change   |
| Motor Vehicle & Parts Dealers      | 441   | MSRSOK441      | YoY % change   |
| Furniture & Home Furnishing        | 442   | MSRSOK442      | YoY % change   |
| Electronics & Appliances           | 443   | MSRSOK443      | YoY % change   |
| Building Materials & Supplies      | 444   | MSRSOK444      | YoY % change   |
| Food & Beverage                    | 445   | MSRSOK445      | YoY % change   |
| Health & Personal Care             | 446   | MSRSOK446      | YoY % change   |
| Gasoline Stations                  | 447   | MSRSOK447      | YoY % change   |
| Clothing & Accessories             | 448   | MSRSOK448      | YoY % change   |
| Sporting Goods & Hobby             | 451   | MSRSOK451      | YoY % change   |
| General Merchandise                | 452   | MSRSOK452      | YoY % change   |
| Miscellaneous Retailers            | 453   | MSRSOK453      | YoY % change   |

**Important Note:** These series report year-over-year percentage changes, NOT absolute
dollar values. They are modeled/experimental data using a blend of survey, admin, and
third-party data. Use as a directional indicator, not a precise dollar forecast.

**Sample API Call:**
```
GET https://api.stlouisfed.org/fred/series/observations?
    series_id=MSRSOKTOTAL
    &api_key={YOUR_KEY}
    &file_type=json
    &observation_start=2019-01-01
```

**Revenue Relevance:** This is the closest publicly available proxy for municipal
sales tax base. The total retail sales measure (MSRSOKTOTAL) correlates directly with
the statewide taxable sales base. Subsector breakdowns help identify which retail
categories are driving growth or contraction, enabling more precise revenue modeling.

---

### 2.2 State Government Sales Tax Collections (Oklahoma)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | U.S. Census Bureau Quarterly Summary of State & Local Tax Revenue  |
| **FRED Series ID**  | `OKSALESTAX`                                                       |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Quarterly                                                          |
| **Lag**             | ~3-4 months                                                        |
| **History**         | Q1 1963 to present                                                 |

**Revenue Relevance:** State sales tax collections are a direct measure of taxable
commercial activity. While quarterly (not monthly), this series provides a benchmark
for validating municipal-level sales tax models. Municipal sales tax rates are
typically applied to the same base as state sales tax.

---

### 2.3 Oklahoma Gross Receipts to the Treasury

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Oklahoma State Treasurer's Office                                  |
| **URL**             | https://oklahoma.gov/treasurer.html (Economic Reports section)     |
| **API Key**         | N/A -- no API                                                      |
| **Format**          | PDF reports (monthly)                                              |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~4-5 weeks                                                         |
| **History**         | Multiple years of archives available                               |
| **Retrieval**       | Manual PDF download and parsing                                    |

**Report URL Pattern:**
```
https://oklahoma.gov/content/dam/ok/en/treasurer/documents/
  inside-the-office/economic-reports/monthly-gross-receipts-reports/
  {YEAR}/GR_{Month}{Year}.pdf
```

**Included Metrics:**
- Individual income tax collections
- Corporate income tax collections
- Sales tax collections (state level)
- Use tax collections
- Gross production tax (oil & gas)
- Motor vehicle tax collections
- Other taxes and fees

**Revenue Relevance:** This is the most comprehensive monthly view of Oklahoma's
fiscal health. The breakdown by tax type provides context for understanding how
different economic sectors are performing. The motor vehicle tax component correlates
with auto sales; gross production tax correlates with energy sector activity.

**Automation Challenge:** Data is published as PDF documents, not machine-readable
format. Would require PDF parsing (tabula, camelot) or OCR to automate. Consider
as a supplemental manual data source rather than an automated pipeline.

---

### 2.4 Per Capita Personal Income (State and County)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Bureau of Economic Analysis (BEA) via FRED                         |
| **FRED Series IDs** | `OKPCPI` (state), `PCPI40{county_fips}` pattern (county)          |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State, County                                                      |
| **Frequency**       | Annual                                                             |
| **Lag**             | ~6-9 months (substantial lag for county data)                      |
| **History**         | 1929 (state), 1969 (county)                                       |

**Revenue Relevance:** Personal income is the fundamental driver of consumer spending
power. While annual frequency limits its utility for monthly forecasting, it provides
essential context for long-range revenue projections and cross-county comparisons.

---

### 2.5 Consumer Price Index (National/Regional)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS via FRED                                                       |
| **FRED Series IDs** | `CPIAUCSL` (national SA), `CUURA421SA0` (South urban, closest OK) |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | National, Census Region (South)                                    |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~2-3 weeks                                                         |
| **History**         | 1947 to present                                                    |

**Note:** BLS does not produce a city-level CPI for any Oklahoma metropolitan area.
The closest geographic specificity is the South Census Region CPI.

**Revenue Relevance:** CPI is essential for deflating nominal revenue figures to
real terms and for understanding whether revenue growth is genuine or merely reflects
price inflation. A municipality collecting 3% more sales tax in a 3% inflation
environment has zero real revenue growth.

---

## 3. HOUSING / CONSTRUCTION INDICATORS

Housing and construction activity generates use tax revenue (on building materials),
building permit fees, and signals population/economic growth that drives future sales
tax base expansion.

---

### 3.1 Building Permits -- State Level (Oklahoma)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | U.S. Census Bureau Building Permits Survey (BPS) via FRED          |
| **FRED Series ID**  | `OKBPPRIV` (total private housing units authorized)                |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma)                                                   |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~6-8 weeks                                                         |
| **History**         | 1988 to present                                                    |

---

### 3.2 Building Permits -- MSA Level

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Census BPS via FRED                                                |
| **FRED Series IDs** | `OKLA440BPPRIVSA` (OKC MSA SA), `OKLA440BP1FH` (OKC 1-unit)      |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | MSA (Oklahoma City, Tulsa, etc.)                                   |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~6-8 weeks                                                         |
| **History**         | ~1988 to present                                                   |

---

### 3.3 Building Permits -- County Level

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Census BPS via HUD SOCDS                                           |
| **URL**             | https://socds.huduser.gov/permits/                                 |
| **Alt Source**       | HUD Open Data ArcGIS REST API                                     |
| **ArcGIS Endpoint** | https://hudgis-hud.opendata.arcgis.com (Residential Construction  |
|                     | Permits by County dataset)                                         |
| **API Key**         | No -- open data                                                    |
| **Format**          | CSV download (SOCDS), JSON/GeoJSON (ArcGIS REST)                  |
| **Geography**       | County, place-level                                                |
| **Frequency**       | Monthly (for ~9,000 monthly-reporting jurisdictions)               |
| **Lag**             | ~8-10 weeks                                                        |
| **History**         | January 1997 to present (monthly reporters)                        |
| **Retrieval**       | Web form query (SOCDS) or ArcGIS REST API                         |

**Census BPS Direct Download (Alternative):**
```
https://www.census.gov/construction/bps/txt/tb3u{YYYY}{MM}.txt
```
(Monthly county-level data in fixed-width text format)

**Revenue Relevance:** Building permits are a leading indicator of construction
activity, which generates use tax on materials and construction employment income.
New residential permits signal population growth that will expand the tax base in
subsequent years. This is especially important for rapidly growing Oklahoma City
suburbs (Canadian County, Cleveland County).

---

### 3.4 FHFA House Price Index (State, MSA, County)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Federal Housing Finance Agency (FHFA) via FRED                     |
| **FRED Series IDs** | See table below                                                    |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State, MSA, County                                                 |
| **Frequency**       | Quarterly (state/MSA), Annual (county)                             |
| **Lag**             | ~2-3 months for quarterly                                          |
| **History**         | 1975 (state), 1977 (MSA), varies by county                        |

**Key FHFA HPI Series IDs for Oklahoma:**

| Geography           | FRED Series ID         | Frequency  | Start   |
|----------------------|------------------------|------------|---------|
| Oklahoma (state)     | OKSTHPI                | Quarterly  | 1975-Q1 |
| Oklahoma City MSA    | ATNHPIUS36420Q         | Quarterly  | 1977-Q1 |
| Tulsa MSA            | ATNHPIUS46140Q         | Quarterly  | 1977-Q1 |
| Oklahoma County      | ATNHPIUS40109A         | Annual     | 1975    |
| Tulsa County         | ATNHPIUS40143A         | Annual     | 1975    |
| Cleveland County     | ATNHPIUS40027A         | Annual     | 1982    |
| Canadian County      | ATNHPIUS40017A         | Annual     | 1982    |
| Logan County         | ATNHPIUS40083A         | Annual     | 1982    |

**FHFA Direct Download (Alternative):**
FHFA also provides bulk CSV downloads of all HPI data at:
https://www.fhfa.gov/data/hpi/datasets

**Revenue Relevance:** Home prices are a wealth effect indicator. Rising home prices
increase homeowner confidence and spending, boosting sales tax revenue. They also
drive property tax assessments (though property tax is typically county, not city).
HPI trends help predict construction activity: rising prices incentivize new building.

---

### 3.5 Zillow Home Value Index (ZHVI)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | Zillow Research                                                    |
| **FRED Series ID**  | `OKUCSFRCONDOSMSAMID` (state level, mid-tier)                      |
| **Download Page**    | https://www.zillow.com/research/data/                              |
| **API Key**         | No (bulk CSV download); Zillow Econ Data API is also available     |
| **Format**          | CSV (bulk download), JSON (API)                                    |
| **Geography**       | State, MSA, County, City, ZIP code                                 |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~4-6 weeks                                                         |
| **History**         | January 2000 to present                                            |
| **Retrieval**       | Bulk CSV download from Zillow Research Data page                   |

**Available Geographies for Oklahoma (via bulk CSV):**

The Zillow Research Data portal provides ZHVI at:
- State level (Oklahoma)
- Metro level (Oklahoma City, Tulsa, Lawton, etc.)
- County level (all Oklahoma counties with sufficient data)
- City level (select Oklahoma cities)
- ZIP code level (highest granularity)

**Zillow vs FHFA:**
- ZHVI is monthly (FHFA quarterly/annual)
- ZHVI includes all homes (FHFA limited to conforming mortgage transactions)
- ZHVI reports dollar values (FHFA reports index values)
- ZHVI has city/ZIP granularity unavailable from FHFA

**Revenue Relevance:** Monthly frequency and city/ZIP granularity make ZHVI the
preferred housing price indicator for monthly revenue forecasting at the municipal
level. Dollar-denominated values are easier to interpret than index values.

---

### 3.6 Construction Employment (State Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | BLS CES via FRED                                                   |
| **FRED Series ID**  | `SMU40000002000000001` (Construction, SA)                          |
| **API Endpoint**    | `https://api.stlouisfed.org/fred/series/observations`              |
| **API Key**         | Yes -- free                                                        |
| **Format**          | JSON                                                               |
| **Geography**       | State (Oklahoma), select MSAs                                      |
| **Frequency**       | Monthly                                                            |
| **Lag**             | ~3-4 weeks                                                         |
| **History**         | ~1990 to present                                                   |

**MSA-level construction employment (Tulsa example):**
`SMU40461402023800001A` -- Specialty Trade Contractors in Tulsa MSA

**Revenue Relevance:** Construction employment is a proxy for the pace of building
activity that generates use tax revenue on materials. It also reflects confidence in
the local economy's growth trajectory.

---

## 4. POPULATION / DEMOGRAPHIC INDICATORS

Population is the fundamental long-run driver of municipal revenue. More residents
means more consumers, more taxable transactions, and a broader tax base.

---

### 4.1 Annual Population Estimates (County Level)

| Field               | Value                                                              |
|---------------------|--------------------------------------------------------------------|
| **Source**           | U.S. Census Bureau Population Estimates Program (PEP)              |
| **URL**             | https://www.census.gov/programs-surveys/popest.html                |
| **FRED Series IDs** | Pattern: `{STCOUNTY}POP` (e.g., `OKOKLA9POP` for Oklahoma County) |
| **API Endpoint**    | FRED API (preferred) or Census API (limited for recent vintages)   |
| **API Key**         | Yes (FRED key or Census key)                                       |
| **Format**          | JSON (FRED), CSV download (Census)                                 |
| **Geography**       | State, County                                                      |
| **Frequency**       | Annual (July 1 reference date)                                     |
| **Lag**             | ~5-6 months (Vintage 2025 released March 2026)                     |
| **History**         | 2010 to present (current intercensal series)                       |

**Census Bureau Direct Download:**
County population estimates (2020-2025) are available as bulk CSV/Excel downloads
from: https://www.census.gov/programs-surveys/popest/data/tables.html

**Note on Census API Availability:**
As of 2026, the Census PEP API does not reliably serve data for vintages 2022 and
later. For the most current estimates, download data files directly from the PEP
webpage rather than relying on the API.

**FRED Series IDs for Key Oklahoma Counties:**

| County           | FRED Series ID |
|------------------|----------------|
| Oklahoma County  | OKOKLA9POP     |
| Tulsa County     | OKTULS9POP     |
| Cleveland County | OKCLEV5POP     |
| Canadian County  | OKCANA7POP     |
| Comanche County  | OKCOMA1POP     |

**Sample FRED API Call:**
```
GET https://api.stlouisfed.org/fred/series/observations?
    series_id=OKOKLA9POP
    &api_key={YOUR_KEY}
    &file_type=json
```

**Revenue Relevance:** Population is the denominator in per-capita revenue analysis
and the fundamental driver of long-term revenue trends. County population growth
rates help identify municipalities that need upward-revised revenue forecasts vs.
those facing structural decline.

---

### 4.2 Population Growth Rate (Derived)

This indicator is derived from the annual population estimates above:

```
growth_rate = (pop_current - pop_prior) / pop_prior * 100
```

**Database Mapping:**
```
geography_type = 'county'
geography_key  = 'Canadian County'
indicator_family = 'population'
indicator_name = 'population_growth_rate_annual'
source_name = 'Census PEP via FRED (derived)'
is_forecast = false
```

**Revenue Relevance:** Growth rate is more useful than absolute population for
forecasting because it captures the trajectory. A county growing at 2% annually
should see approximately 2% baseline revenue growth from population alone, before
considering per-capita spending changes.

---

## 5. IMPLEMENTATION RECOMMENDATIONS

### 5.1 Recommended Data Pipeline Architecture

```
Phase 1 (Immediate): FRED API Integration
  - Single API key, single endpoint
  - 20+ Oklahoma series covering labor, retail, housing, population
  - JSON responses, well-documented, reliable uptime
  - Estimated development: 2-3 days

Phase 2 (Short-term): BLS API v2 for County Labor Data
  - Bulk retrieval of all 77 Oklahoma county unemployment data
  - POST requests with up to 50 series per call (2 calls for all counties)
  - Estimated development: 1-2 days

Phase 3 (Medium-term): Census BPS + HUD SOCDS
  - Building permits at county level
  - CSV parsing pipeline
  - Estimated development: 2-3 days

Phase 4 (As needed): Zillow ZHVI Bulk Download
  - Monthly CSV download from Zillow Research
  - Parse and load city/county/ZIP level home values
  - Estimated development: 1-2 days
```

### 5.2 FRED API Master Series List for Automated Ingestion

The following table provides every FRED series ID recommended for the first
implementation phase, mapped to the `economic_indicators` table schema:

```
| FRED Series ID    | geography_type | geography_key       | indicator_family | indicator_name                        | freq    |
|-------------------|----------------|---------------------|------------------|---------------------------------------|---------|
| OKUR              | state          | OK                  | labor            | unemployment_rate_sa                  | monthly |
| OKURN             | state          | OK                  | labor            | unemployment_rate_nsa                 | monthly |
| OKOKLA9URN        | county         | Oklahoma County     | labor            | unemployment_rate_nsa                 | monthly |
| OKTULS3URN        | county         | Tulsa County        | labor            | unemployment_rate_nsa                 | monthly |
| OKLA440UR         | msa            | Oklahoma City MSA   | labor            | unemployment_rate_sa                  | monthly |
| SMU40000000000000001 | state       | OK                  | labor            | nonfarm_employment_total_sa           | monthly |
| SMU40000004200000001 | state       | OK                  | labor            | retail_trade_employment_sa            | monthly |
| SMU40000002000000001 | state       | OK                  | labor            | construction_employment_sa            | monthly |
| SMU40000007000000001 | state       | OK                  | labor            | leisure_hospitality_employment_sa     | monthly |
| OKICLAIMS         | state          | OK                  | labor            | initial_unemployment_claims           | weekly  |
| OKCCLAIMS         | state          | OK                  | labor            | continued_unemployment_claims         | weekly  |
| LBSSA40           | state          | OK                  | labor            | labor_force_participation_rate_sa     | monthly |
| MSRSOKTOTAL       | state          | OK                  | retail           | retail_sales_total_yoy_pct            | monthly |
| MSRSOK441         | state          | OK                  | retail           | retail_sales_motor_vehicle_yoy_pct    | monthly |
| MSRSOK444         | state          | OK                  | retail           | retail_sales_building_materials_yoy   | monthly |
| MSRSOK447         | state          | OK                  | retail           | retail_sales_gasoline_yoy_pct         | monthly |
| MSRSOK452         | state          | OK                  | retail           | retail_sales_general_merch_yoy_pct    | monthly |
| OKSALESTAX        | state          | OK                  | retail           | state_sales_tax_collections           | quarterly|
| OKPCPI            | state          | OK                  | retail           | per_capita_personal_income            | annual  |
| CPIAUCSL          | state          | US                  | retail           | consumer_price_index_national_sa      | monthly |
| OKBPPRIV          | state          | OK                  | construction     | building_permits_private_total        | monthly |
| OKLA440BPPRIVSA   | msa            | Oklahoma City MSA   | construction     | building_permits_private_sa           | monthly |
| OKSTHPI           | state          | OK                  | housing          | house_price_index_fhfa                | quarterly|
| ATNHPIUS36420Q    | msa            | Oklahoma City MSA   | housing          | house_price_index_fhfa                | quarterly|
| ATNHPIUS46140Q    | msa            | Tulsa MSA           | housing          | house_price_index_fhfa                | quarterly|
| ATNHPIUS40109A    | county         | Oklahoma County     | housing          | house_price_index_fhfa                | annual  |
| ATNHPIUS40143A    | county         | Tulsa County        | housing          | house_price_index_fhfa                | annual  |
| OKUCSFRCONDOSMSAMID| state         | OK                  | housing          | zillow_home_value_index               | monthly |
| OKOKLA9POP        | county         | Oklahoma County     | population       | resident_population                   | annual  |
| OKTULS9POP        | county         | Tulsa County        | population       | resident_population                   | annual  |
```

### 5.3 Update Schedule

Recommended ingestion cadence aligned with source data publication schedules:

| Cadence   | Series                                          | When to Run              |
|-----------|------------------------------------------------|--------------------------|
| Weekly    | OKICLAIMS, OKCCLAIMS                            | Every Thursday (claims released Thursday) |
| Monthly   | Unemployment rates (all), employment, retail    | 1st and 15th of month    |
| Quarterly | OKSTHPI, OKSALESTAX, FHFA MSA/county HPI       | 15 days after quarter end|
| Annual    | Population estimates, county HPI, PCPI          | April (after Census release) |

### 5.4 Quality Assurance Checks

For each automated data load, implement these validation rules:

1. **Completeness:** Verify expected number of observations for the date range
2. **Reasonableness:** Flag any month-over-month change exceeding 2 standard
   deviations from the trailing 24-month average
3. **Timeliness:** Alert if expected data for reference month is not available
   within the documented lag period
4. **Consistency:** Cross-validate state totals against sum of county/MSA components
   where applicable (e.g., state employment vs sum of MSA employment)
5. **Revision tracking:** Store `source_vintage` date to track when data was
   retrieved, enabling detection of historical revisions

---

## 6. REVENUE CORRELATION MATRIX

Theoretical correlation strength between each indicator category and municipal
revenue streams:

```
                        | Sales Tax | Use Tax | Franchise | Permits | Total Rev |
|-----------------------|-----------|---------|-----------|---------|-----------|
| Unemployment Rate     |   -0.85   |  -0.70  |   -0.40   |  -0.30  |   -0.75   |
| Nonfarm Employment    |   +0.80   |  +0.65  |   +0.45   |  +0.35  |   +0.70   |
| Initial Claims        |   -0.75   |  -0.60  |   -0.30   |  -0.25  |   -0.65   |
| Retail Sales (total)  |   +0.95   |  +0.50  |   +0.30   |  +0.20  |   +0.80   |
| Building Permits      |   +0.40   |  +0.85  |   +0.30   |  +0.90  |   +0.55   |
| House Price Index     |   +0.55   |  +0.50  |   +0.25   |  +0.40  |   +0.50   |
| Population Growth     |   +0.70   |  +0.60  |   +0.55   |  +0.65  |   +0.70   |
| Construction Emp      |   +0.35   |  +0.80  |   +0.25   |  +0.85  |   +0.50   |
| Personal Income       |   +0.80   |  +0.55  |   +0.50   |  +0.35  |   +0.70   |
| CPI                   |   +0.60   |  +0.45  |   +0.40   |  +0.20  |   +0.55   |
```

**Note:** These are theoretical/estimated correlations based on economic literature.
Actual correlations should be computed from historical Oklahoma municipal data once
the indicators are loaded. These values guide indicator prioritization, not model
coefficients.

---

## 7. DATA SOURCE REFERENCE LINKS

### Primary APIs
- FRED API Documentation: https://fred.stlouisfed.org/docs/api/fred/
- FRED API Key Registration: https://fredaccount.stlouisfed.org/apikeys
- BLS API v2 Documentation: https://www.bls.gov/developers/api_signature_v2.htm
- BLS API Registration: https://data.bls.gov/registrationEngine/
- Census API Catalog: https://www.census.gov/data/developers/data-sets.html

### Data Portals
- FRED Homepage: https://fred.stlouisfed.org/
- BLS LAUS: https://www.bls.gov/lau/
- BLS CES: https://www.bls.gov/sae/
- Census Building Permits: https://www.census.gov/construction/bps/
- Census Population Estimates: https://www.census.gov/programs-surveys/popest.html
- HUD SOCDS Building Permits: https://socds.huduser.gov/permits/
- FHFA HPI: https://www.fhfa.gov/data/hpi
- Zillow Research Data: https://www.zillow.com/research/data/

### Oklahoma-Specific Sources
- OESC Labor Market: https://oklahoma.gov/oesc/labor-market.html
- OESC LAUS: https://oklahoma.gov/oesc/labor-market/local-area-statistics.html
- OESC CES: https://oklahoma.gov/oesc/labor-market/current-employment-statistics.html
- OESC Claims: https://oklahoma.gov/oesc/labor-market/claims-data.html
- OESC QCEW: https://oklahoma.gov/oesc/labor-market/qcew.html
- OK Treasurer Economic Reports: https://oklahoma.gov/treasurer.html
- OK Policy Institute (Gross Receipts): https://okpolicy.org/gross-receipts/

### Series ID References
- BLS Series ID Formats: https://www.bls.gov/help/hlpforma.htm
- BLS CES Series Structure: https://www.bls.gov/sae/additional-resources/state-and-area-ces-series-code-structure-under-naics.htm
- BLS Oklahoma CES Publication List: https://www.bls.gov/sae/additional-resources/list-of-published-state-and-metropolitan-area-series/oklahoma.htm
- Oklahoma FIPS Codes: https://www.cccarto.com/fipscodes/oklahoma/

---

## Appendix A: Oklahoma County FIPS Codes (for BLS/FRED Series Construction)

For constructing LAUS series IDs (`LAUCN40{3-digit FIPS}0000000003`) and
FRED population series IDs for all 77 Oklahoma counties:

| County      | FIPS 3-digit | County     | FIPS 3-digit |
|-------------|-------------|------------|------------|
| Adair       | 001         | Le Flore   | 079        |
| Alfalfa     | 003         | Lincoln    | 081        |
| Atoka       | 005         | Logan      | 083        |
| Beaver      | 007         | Love       | 085        |
| Beckham     | 009         | Major      | 093        |
| Blaine      | 011         | Marshall   | 095        |
| Bryan       | 013         | Mayes      | 097        |
| Caddo       | 015         | McClain    | 087        |
| Canadian    | 017         | McCurtain  | 089        |
| Carter      | 019         | McIntosh   | 091        |
| Cherokee    | 021         | Murray     | 099        |
| Choctaw     | 023         | Muskogee   | 101        |
| Cimarron    | 025         | Noble      | 103        |
| Cleveland   | 027         | Nowata     | 105        |
| Coal        | 029         | Okfuskee   | 107        |
| Comanche    | 031         | Oklahoma   | 109        |
| Cotton      | 033         | Okmulgee   | 111        |
| Craig       | 035         | Osage      | 113        |
| Creek       | 037         | Ottawa     | 115        |
| Custer      | 039         | Pawnee     | 117        |
| Delaware    | 041         | Payne      | 119        |
| Dewey       | 043         | Pittsburg  | 121        |
| Ellis       | 045         | Pontotoc   | 123        |
| Garfield    | 047         | Pottawatomie| 125       |
| Garvin      | 049         | Pushmataha | 127        |
| Grady       | 051         | Roger Mills| 129        |
| Grant       | 053         | Rogers     | 131        |
| Greer       | 055         | Seminole   | 133        |
| Harmon      | 057         | Sequoyah   | 135        |
| Harper      | 059         | Stephens   | 137        |
| Haskell     | 061         | Texas      | 139        |
| Hughes      | 063         | Tillman    | 141        |
| Jackson     | 065         | Tulsa      | 143        |
| Jefferson   | 067         | Wagoner    | 145        |
| Johnston    | 069         | Washington | 147        |
| Kay         | 071         | Washita    | 149        |
| Kingfisher  | 073         | Woods      | 151        |
| Kiowa       | 075         | Woodward   | 153        |
| Latimer     | 077         |            |            |

---

## Appendix B: Sample Python Code for FRED API Ingestion

```python
"""
Sample FRED API client for MuniRevenue economic indicator ingestion.
This is illustrative -- production code should use the project's existing
HTTP client, error handling, and database patterns.
"""

import httpx
from datetime import date

FRED_API_KEY = "YOUR_FRED_API_KEY"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# Master list of series to ingest (subset -- see Section 5.2 for full list)
FRED_SERIES = [
    {"series_id": "OKUR",          "geo_type": "state",  "geo_key": "OK",
     "family": "labor",  "name": "unemployment_rate_sa"},
    {"series_id": "OKICLAIMS",     "geo_type": "state",  "geo_key": "OK",
     "family": "labor",  "name": "initial_unemployment_claims"},
    {"series_id": "MSRSOKTOTAL",   "geo_type": "state",  "geo_key": "OK",
     "family": "retail", "name": "retail_sales_total_yoy_pct"},
    {"series_id": "OKBPPRIV",      "geo_type": "state",  "geo_key": "OK",
     "family": "construction", "name": "building_permits_private_total"},
    {"series_id": "OKOKLA9POP",    "geo_type": "county", "geo_key": "Oklahoma County",
     "family": "population", "name": "resident_population"},
]


async def fetch_fred_series(
    series_id: str,
    start_date: str = "2015-01-01",
    end_date: str | None = None,
    frequency: str | None = None,
    aggregation: str | None = None,
) -> list[dict]:
    """Fetch observations for a single FRED series."""
    params = {
        "series_id": series_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }
    if end_date:
        params["observation_end"] = end_date
    if frequency:
        params["frequency"] = frequency       # e.g., 'm' for monthly
    if aggregation:
        params["aggregation_method"] = aggregation  # 'avg', 'sum', 'eop'

    async with httpx.AsyncClient() as client:
        resp = await client.get(FRED_BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

    return data.get("observations", [])


async def ingest_all_series():
    """Fetch all configured series and prepare for database insert."""
    today = date.today().isoformat()
    rows = []

    for cfg in FRED_SERIES:
        obs = await fetch_fred_series(
            series_id=cfg["series_id"],
            frequency="m" if cfg["family"] != "population" else None,
            aggregation="sum" if cfg["name"] == "initial_unemployment_claims" else None,
        )
        for o in obs:
            if o["value"] == ".":
                continue  # FRED uses "." for missing values
            rows.append({
                "geography_type": cfg["geo_type"],
                "geography_key":  cfg["geo_key"],
                "indicator_family": cfg["family"],
                "indicator_name": cfg["name"],
                "period_date":   o["date"],
                "value":         float(o["value"]),
                "source_name":   f"FRED ({cfg['series_id']})",
                "source_vintage": today,
                "is_forecast":   False,
                "metadata":      {"fred_series_id": cfg["series_id"],
                                  "realtime_start": o.get("realtime_start"),
                                  "realtime_end": o.get("realtime_end")},
            })

    return rows
```

---

## Appendix C: Sample BLS API v2 POST for Bulk County Data

```python
"""
Sample BLS API v2 client for bulk county-level unemployment data.
Fetches all 77 Oklahoma counties in 2 API calls (50 series max per call).
"""

import httpx

BLS_API_KEY = "YOUR_BLS_API_KEY"
BLS_ENDPOINT = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

# Oklahoma state FIPS = 40
# County FIPS codes: 001, 003, 005, ... 153 (77 counties)
OK_COUNTY_FIPS = [
    "001","003","005","007","009","011","013","015","017","019",
    "021","023","025","027","029","031","033","035","037","039",
    "041","043","045","047","049","051","053","055","057","059",
    "061","063","065","067","069","071","073","075","077","079",
    "081","083","085","087","089","091","093","095","097","099",
    "101","103","105","107","109","111","113","115","117","119",
    "121","123","125","127","129","131","133","135","137","139",
    "141","143","145","147","149","151","153",
]

def build_laus_series_id(county_fips_3: str, measure: str = "03") -> str:
    """Build a LAUS county-level series ID.
    Measure codes: 03=rate, 04=unemp count, 05=emp count, 06=labor force
    """
    return f"LAUCN40{county_fips_3}0000000{measure}"


async def fetch_county_unemployment(start_year: int = 2020, end_year: int = 2026):
    """Fetch unemployment rates for all 77 Oklahoma counties."""
    all_series = [build_laus_series_id(fips) for fips in OK_COUNTY_FIPS]

    results = []
    # BLS allows max 50 series per request
    for i in range(0, len(all_series), 50):
        batch = all_series[i:i+50]
        payload = {
            "seriesid": batch,
            "startyear": str(start_year),
            "endyear": str(end_year),
            "registrationkey": BLS_API_KEY,
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                BLS_ENDPOINT,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()

        for series in data.get("Results", {}).get("series", []):
            series_id = series["seriesID"]
            for item in series.get("data", []):
                results.append({
                    "series_id": series_id,
                    "year": item["year"],
                    "period": item["period"],    # e.g., "M01" for January
                    "value": item["value"],
                    "period_name": item.get("periodName"),
                })

    return results
```

---

*End of research document. This document should be reviewed and updated quarterly
as data sources may change availability, endpoints, or formats.*
