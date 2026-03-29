# MuniRev — Continue From Here

**Last session:** 2026-03-29
**Repo:** https://github.com/BrianPillmore/MuniRev
**Local:** C:\Users\brian\GitHub\CityTax

## What's Working

- **Backend** (Python FastAPI) running on port 8000
  - Analysis engine: upload xlsx, get MoM/YoY, seasonality, ANOVA, 12-month forecast
  - HTML report generator with inline SVG charts
  - OkTAP XML SpreadsheetML parser (ledger + NAICS reports)
  - Import API: POST /api/oktap/import/ledger, /naics, /auto, /bulk
  - 39 tests passing (unit + API + integration)
- **Frontend** (TypeScript SPA) served by backend
  - File upload, analysis rendering, report download, tab navigation
- **Infrastructure**
  - Dockerfile (multi-stage), docker-compose (app + postgres + caddy)
  - PostgreSQL schema (7 tables), SQLAlchemy ORM models
  - Start scripts: `start.bat` / `bash start.sh`

## What's Working NOW (as of 2026-03-29)

- **OkTAP automated retrieval** — WORKING via Playwright headless browser
  - `backend/app/services/oktap_retriever.py` — fills OkTAP forms, clicks Search + Export
  - Single request returns ALL cities (524) or ALL counties (77) for a tax type + year
  - 3 tax types: sales, use, lodging
  - `scripts/fetch_statewide.py` — batch script to pull all years (2021-2026)
  - Raw .xls files saved to `data/raw/`, parsed CSVs to `data/parsed/`
  - 5-second polite delay between requests

## What's NOT Working Yet

- **Database storage** — import endpoints parse and return JSON but don't INSERT into PostgreSQL
- **Alembic migrations** — schema.sql exists but no migration tooling
- **Data retrieval API** — no GET endpoints for stored data (GET /api/cities, /api/cities/{copo}/ledger, etc.)
- **Dashboard frontend** — no city picker, no Highcharts visualizations, no multi-city view
- **NAICS retrieval** — retriever supports it but not yet in the batch script (requires per-month requests)

## Immediate Next Steps

1. **Wire imports to database** — INSERT parsed records into PostgreSQL on import

2. **Build data retrieval API** — GET endpoints to query stored data

3. **Dashboard frontend with Highcharts** — See visualization section below

4. **NAICS batch retrieval** — add per-month NAICS fetching to the statewide script

## Visualization: Highcharts

Use Highcharts for all dashboard charts. It is superior to D3/Chart.js for financial time-series:
- Built-in stock chart with date axis, zoom, range selector
- Drilldown support (statewide → city → industry)
- Export to PNG/PDF built in
- Responsive out of the box

**License:** Highcharts is free for non-commercial / personal use. For a municipal service, evaluate the Non-Profit license or standard commercial license.

**Integration plan:**
- Load via CDN in `frontend/index.html`: `<script src="https://code.highcharts.com/highcharts.js">`
- Additional modules: `highcharts-more.js` (confidence bands), `modules/stock.js` (time series)
- Create `frontend/src/charts/` module with typed wrappers
- Chart types needed:
  - **Line/area**: Revenue time series with forecast confidence bands
  - **Column**: MoM and YoY comparisons
  - **Pie/donut**: NAICS industry share
  - **Heatmap**: Statewide anomaly overview (cities × months)
  - **Treemap**: NAICS industry breakdown by revenue contribution
  - **Stock chart**: Interactive date range selection with navigator

## Key Files

| File | Purpose |
|---|---|
| backend/app/main.py | FastAPI app, route registration |
| backend/app/services/oktap_parser.py | OkTAP XML parser (WORKING) |
| backend/app/services/oktap_retriever.py | OkTAP automated retrieval (WORKING) |
| backend/app/api/oktap.py | Import API endpoints |
| backend/app/db/schema.sql | PostgreSQL DDL (734 lines) |
| backend/app/models/orm.py | SQLAlchemy ORM models |
| backend/app/schemas.py | Pydantic API response models |
| backend/app/services/analysis.py | Revenue analysis engine |
| frontend/src/main.ts | TypeScript SPA |
| scripts/fetch_statewide.py | Batch statewide data retrieval |
| plans/v1-platform.md | Implementation roadmap |
| plans/oktap-retrieval.md | OkTAP automated retrieval design |
| data/raw/ | Raw .xls files from OkTAP (gitignored) |
| data/parsed/ | Parsed CSVs for inspection (gitignored) |

## Local Dev Commands

```bash
# Start everything (single process, production mode)
start.bat

# Backend only (with hot reload)
cd backend && .venv\Scripts\activate && uvicorn app.main:app --reload

# Frontend only (with hot reload, proxies /api to backend)
cd frontend && npm run dev

# Run all tests
cd backend && .venv\Scripts\python -m pytest tests/ ../tests/integration/ -v

# TypeScript type check
cd frontend && npx tsc --noEmit
```

## Data Reconciliation & Analysis (Next Priority)

- **NAICS-to-Ledger reconciliation**: Sum all NAICS sector_totals for a city/month and compare to the ledger `returned` value for that same city/month. The difference = revenue not assigned to a NAICS code (unclassified). Track the reconciliation rate (% of ledger accounted for by NAICS).
- **Industry variance analysis**: For each city, rank NAICS codes by contribution to total revenue. Detect YoY changes in industry mix. Flag industries with sudden drops or spikes. Identify concentration risk (single NAICS > 30% of total).

## Municipal Contact Directory (Planned)

Build a contacts database of Oklahoma municipal officials for outreach:
- City Managers and Finance Directors / CFOs for all cities
- All 3 County Commissioners for all 77 counties
- Mayors and Vice Mayors for all cities
- City Clerks for all cities
- Emails and phone numbers where publicly available

Source: Oklahoma Municipal League, county websites, city websites, public records.

## OkTAP Data Source

- URL: https://oktap.tax.ok.gov/OkTAP/Web/_/#1 (Ledger) and #2 (NAICS)
- Ledger form: Tax Type (Lodging/Sales/Use), City/County, Year, Month, Copo code
- NAICS form: Tax Type (Sales/Use), City/County/State, Year, Month, Copo, Sector
- Export format: XML SpreadsheetML (.xls)
- Yukon = copo 0955, tax rate 0.04
- 5 years of data available online
- Test fixtures in backend/tests/fixtures/ (real Yukon exports)
