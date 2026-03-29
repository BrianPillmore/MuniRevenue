# MuniRev Platform — Implementation Plan

## Phase 1: Data Foundation (Current)

### Done
- [x] OkTAP XML SpreadsheetML parser (ledger + NAICS reports)
- [x] Import API: `/api/oktap/import/ledger`, `/naics`, `/auto`, `/bulk`
- [x] Auto-detection of report type from file headers
- [x] PostgreSQL schema: jurisdictions, ledger_records, naics_records, anomalies, forecasts
- [x] SQLAlchemy ORM models matching the schema
- [x] Database connection module with PostgreSQL + SQLite fallback
- [x] Docker multi-stage build (Node frontend + Python backend)
- [x] docker-compose.yml: app + postgres + caddy
- [x] Caddy reverse proxy with auto-TLS
- [x] 20 passing tests (analysis + OkTAP parser)
- [x] Real OkTAP test fixtures (Yukon 0955 ledger + NAICS exports)
- [x] Original analysis engine (upload xlsx, MoM/YoY, seasonality, ANOVA, forecast)
- [x] HTML report generator
- [x] TypeScript SPA with upload, results rendering, report download

### Remaining (Phase 1 completion)
- [ ] Alembic migration from schema.sql
- [ ] Wire import endpoints to database (INSERT ON CONFLICT UPDATE)
- [ ] Auto-create jurisdiction if copo not found during import
- [ ] Data retrieval API:
  - `GET /api/cities` — list all jurisdictions
  - `GET /api/cities/{copo}` — jurisdiction detail
  - `GET /api/cities/{copo}/ledger?tax_type=sales&start=2023-01&end=2026-03` — time series
  - `GET /api/cities/{copo}/naics?tax_type=sales&year=2026&month=2` — industry breakdown
- [ ] Seed script for top 50 Oklahoma cities (copo codes, names, counties)
- [ ] Frontend: OkTAP import tab (upload .xls files, see parsed results)

## Phase 2: Analysis Engine

- [ ] Run analysis from database (not just uploaded files)
- [ ] Anomaly detection service:
  - Z-score on month-over-month changes (flag > 2 sigma)
  - IQR-based outlier detection on seasonal patterns
  - Sudden revenue drops/spikes (> 15% unexpected change)
  - Missing data detection (expected month not reported)
- [ ] NAICS driver analysis:
  - Rank industries by revenue contribution per city
  - Detect composition shifts (industry growing/shrinking share)
  - Identify concentration risk (single industry > 30% of revenue)
- [ ] Store forecasts in database per city per tax type
- [ ] Dashboard frontend:
  - City picker dropdown
  - Tax type tabs (lodging, sales, use)
  - Time series chart (D3.js or Chart.js)
  - Anomaly highlights panel
  - Top NAICS industries table
  - Revenue summary cards

## Phase 3: Statewide Coverage

- [ ] Batch import tool: process multiple cities' exports at once
- [ ] Reverse-engineer OkTAP API for automated data retrieval
- [ ] Cross-city comparison dashboard
- [ ] Peer benchmarking (similar population, region, economy)
- [ ] Email/webhook alerts when anomalies detected
- [ ] Public read-only API with rate limiting
- [ ] City/county geographic map view

## Phase 4: Intelligence Layer

- [ ] ML forecasting (Prophet, ARIMA) alongside current seasonal trend
- [ ] NAICS composition drift detection over time
- [ ] Revenue risk scoring per jurisdiction
- [ ] Economic indicator correlation (unemployment, population, permits)
- [ ] Exportable reports for city council presentations
- [ ] Multi-tenant access (city officials see their data)
- [ ] Subscription tier for premium analytics

## Technical Debt

- [ ] Pin Python dependencies (pip-compile)
- [ ] Add frontend tests (vitest)
- [ ] Add API endpoint tests (TestClient)
- [ ] Add tsc --noEmit to CI
- [ ] Replace .claude/commands with MuniRev-specific commands
- [ ] Add eslint + ruff for linting
