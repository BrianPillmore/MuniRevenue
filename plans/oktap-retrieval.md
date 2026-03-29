# OkTAP Automated Data Retrieval

## Problem

OkTAP (oktap.tax.ok.gov) provides public tax data but has no documented API. Data must be retrieved through a web form interface. To build a statewide platform, we need to automate downloading reports for ~677 jurisdictions across multiple years, tax types, and report formats.

## Approach: Playwright Browser Automation

The OkTAP site is a JavaScript SPA with hash routing. The most reliable retrieval method is headless browser automation using Playwright, which:
- Handles JavaScript rendering and form interactions
- Works with any SPA framework (no API reverse-engineering needed)
- Can capture file downloads triggered by the Export button
- Is resilient to minor UI changes

### Why Not Direct HTTP Requests?

The OkTAP site uses hash-based routing (#1, #2) and likely makes XHR/fetch calls from JavaScript. Without access to browser DevTools on the live site, we can't reliably determine the exact API endpoints, request format, or required headers/cookies. Playwright sidesteps this entirely.

## OkTAP Form Structure (from screenshots)

### Ledger Report (#1)

URL: `https://oktap.tax.ok.gov/OkTAP/Web/_/#1`

| Field | Type | Values |
|---|---|---|
| Tax Type | Radio | Lodging, Sales, Use |
| City/County | Radio | City, County |
| Year | Dropdown | 2026, 2025, 2024, 2023, 2022 (5 years) |
| Month | Dropdown | 01-12 or blank (all months in year) |
| Copo | Text input | City/county code (e.g., "0955" for Yukon) |
| Search | Button | Submits form, loads results into table |
| Export | Link/Button | Downloads .xls file (XML SpreadsheetML) |

### NAICS Report (#2)

URL: `https://oktap.tax.ok.gov/OkTAP/Web/_/#2`

| Field | Type | Values |
|---|---|---|
| Tax Type | Radio | Sales, Use |
| City/County/State | Radio | City, County, State |
| Year | Dropdown | 2026, 2025, 2024, 2023, 2022 |
| Month | Dropdown | 01-12 (required, single month) |
| Copo | Text input | City/county code |
| Sector | Dropdown | NAICS sector filter (optional) |
| Search | Button | Submits form |
| Export | Link/Button | Downloads .xls file |

## Retrieval Service Design

### File: `backend/app/services/oktap_retriever.py`

```python
class OkTAPRetriever:
    """Automated retrieval of OkTAP reports via headless browser."""

    async def fetch_ledger(self, copo: str, tax_type: str, year: int) -> bytes
    async def fetch_naics(self, copo: str, tax_type: str, year: int, month: int) -> bytes
    async def fetch_city_all(self, copo: str, years: list[int]) -> list[RetrievalResult]
    async def fetch_statewide(self, year: int, month: int) -> list[RetrievalResult]
```

### Flow

1. Launch headless Chromium via Playwright
2. Navigate to OkTAP page (#1 for ledger, #2 for NAICS)
3. Fill form fields (tax type, city/county, year, month, copo)
4. Click Search button
5. Wait for results table to populate (or "No Results" message)
6. If results exist, click Export to trigger .xls download
7. Capture downloaded file bytes
8. Return raw bytes (caller can then parse with existing parser)

### Rate Limiting

- 3-second delay between requests (respectful to government server)
- Max 10 requests per minute
- Exponential backoff on errors (5s, 10s, 20s, 40s, give up)
- User-Agent identifies MuniRev as a municipal analytics tool

### Error Handling

- No results: log and skip (some city/month combinations have no data)
- Timeout (30s): retry once, then skip
- Page error: close browser, wait 30s, retry with fresh session
- Network error: exponential backoff

## API Endpoints

### File: `backend/app/api/retrieval.py`

| Method | Path | Description |
|---|---|---|
| POST | /api/oktap/fetch/ledger | Fetch ledger report for one city/year |
| POST | /api/oktap/fetch/naics | Fetch NAICS report for one city/year/month |
| POST | /api/oktap/fetch/city | Fetch all reports for a city (all types, all available years) |
| POST | /api/oktap/fetch/batch | Queue batch retrieval for multiple cities |
| GET | /api/oktap/fetch/status/{job_id} | Check status of batch retrieval job |

### Request Example

```json
POST /api/oktap/fetch/ledger
{
  "copo": "0955",
  "tax_type": "sales",
  "year": 2026
}
```

### Response

```json
{
  "status": "success",
  "copo": "0955",
  "tax_type": "sales",
  "year": 2026,
  "records_found": 9,
  "records": [...],   // parsed ledger records
  "stored": true      // whether records were saved to DB
}
```

## Batch Retrieval Strategy

### For one city (full history)

```
For each year in [2022, 2023, 2024, 2025, 2026]:
  For each tax_type in [sales, use, lodging]:
    Fetch ledger (copo, tax_type, year)  → 15 requests
  For each tax_type in [sales, use]:
    For each month in [1..12]:
      Fetch NAICS (copo, tax_type, year, month) → 120 requests

Total: ~135 requests per city
At 3s delay: ~7 minutes per city
```

### For statewide (one month)

```
For each city in jurisdictions table (~600):
  Fetch ledger (copo, sales, current_year)
  Fetch NAICS (copo, sales, current_year, current_month)

Total: ~1200 requests
At 3s delay: ~60 minutes
```

### Priority Order

1. Start with Yukon (0955) — our test city
2. Top 30 Oklahoma cities by population
3. All remaining cities
4. Counties

## Dependencies

```
playwright>=1.40
```

Playwright requires browser binaries:
```bash
pip install playwright
playwright install chromium
```

Docker: add Playwright + Chromium to Dockerfile (increases image size by ~300MB).

## Alternative: Guided Manual Download

If Playwright proves unreliable or OkTAP blocks automation, fallback to a guided workflow:

1. Frontend shows a checklist of what data is missing for each city
2. User clicks a city → opens OkTAP in a new tab with pre-filled URL params (if possible)
3. User downloads the .xls file manually
4. User drags the file into MuniRev upload area
5. MuniRev auto-detects and imports

This is slower but always works. The existing import API already supports this flow.
