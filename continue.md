# MuniRev — Continue From Here

**Last session:** 2026-03-31
**Repo:** https://github.com/BrianPillmore/MuniRev
**Local:** C:\Users\brian\GitHub\CityTax

## What's Working

### Platform
- **10 views** with sidebar navigation
- **9.1M records** in PostgreSQL (78K ledger + 9M NAICS)
- **644 jurisdictions** (567 cities + 77 counties)
- **24,642 detected anomalies** (YoY spike/drop, MoM outlier, revenue cliff)
- **1,399 NAICS codes** with sector reference tables
- **14+ API endpoints** all working

### Views
| View | Route | Features |
|---|---|---|
| Overview | #/overview | KPI cards, top 10 cities bar chart |
| Revenue Explorer | #/city/{copo} | Search, 4 sub-tabs (Revenue, Industries, Seasonality, Details) |
| County View | #/county/{county} | Aggregate trend + city breakdown |
| Compare | #/compare | Multi-city overlay (up to 5 cities) |
| Forecasts | #/forecast/{copo} | Historical + projected line, confidence bands, CSV download, methodology |
| Anomalies | #/anomalies | Full filtering: severity, tax type, anomaly type, city search, min deviation |
| Rankings | #/rankings | Paginated table with peer group filters (population bands) |
| Trends | #/trends | Statewide revenue line chart with controls |
| Export | #/export | CSV download builder |
| About | #/about | Project info + disclaimer |

### Chart Controls (Revenue Explorer + Trends)
- Smoothing: Raw / 3-Mo / 6-Mo / TTM rolling averages
- Nominal / Seasonally Adjusted toggle
- Linear trendline overlay
- Y-axis from zero toggle

### Infrastructure
- PostgreSQL 16 (Docker)
- FastAPI backend with 14+ endpoints
- Vite + TypeScript frontend (374KB bundle)
- Highcharts for all visualizations
- Anomaly detection service
- OkTAP automated retrieval (Playwright)

## In Progress (agent teams running)
- $ Amount / % Change display toggle on all charts
- Enhanced Export (all tax types + forecast data)
- Fix 5 failing tests
- Date range filter on anomaly endpoints
- NAICS industry-level anomaly detection
- Visual design polish (CSS improvements)

## Future Backlog
- Better overall UI/UX design
- NAICS composition drift analysis
- Economic indicator integration
- Prophet/ARIMA forecasting models
- Municipal contact directory
- Hetzner deployment
- Authentication/multi-tenant access

## Key Files
| File | Purpose |
|---|---|
| frontend/src/main.ts | App entry, router, sidebar |
| frontend/src/views/*.ts | 10 view modules |
| frontend/src/components/*.ts | Reusable components (sidebar, search, kpi, toggle, chart-controls, loading) |
| frontend/src/api.ts | 17+ API wrapper functions |
| frontend/src/theme.ts | Highcharts theme config |
| frontend/src/utils.ts | Formatting + analysis utilities |
| backend/app/api/cities.py | 10+ city/county endpoints |
| backend/app/api/analytics.py | 4 statewide analytics endpoints |
| backend/app/services/anomaly_detector.py | Anomaly detection engine |
| backend/app/services/analysis.py | Revenue analysis (legacy upload) |
| scripts/fetch_statewide.py | OkTAP ledger retrieval |
| scripts/fetch_naics_slow.py | OkTAP NAICS retrieval |
| scripts/load_naics_fast.py | Fast NAICS DB loader (COPY) |
| scripts/run_anomaly_detection.py | Batch anomaly scan |

## Local Commands
```bash
# Start server (backend serves frontend)
cd backend && .venv\Scripts\activate && uvicorn app.main:app --host 127.0.0.1 --port 8000

# Build frontend
cd frontend && npm run build

# Run tests
cd backend && .venv\Scripts\python -m pytest tests/ -v

# Start PostgreSQL (Docker)
docker compose up -d postgres
```
