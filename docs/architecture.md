# MuniRev Architecture

## System Overview

MuniRev is a monorepo with three main components:

```
┌────────────┐     ┌──────────────┐     ┌────────────┐
│  Frontend   │────▶│  FastAPI      │────▶│ PostgreSQL │
│  (Vite/TS)  │◀────│  Backend      │◀────│            │
└────────────┘     └──────────────┘     └────────────┘
                          │
                   ┌──────┴──────┐
                   │  OkTAP       │
                   │  (data src)  │
                   └─────────────┘
```

- **Frontend**: TypeScript SPA, Vite build, vanilla DOM (no framework)
- **Backend**: Python 3.13, FastAPI, Pandas, NumPy, SciPy, SQLAlchemy 2.0
- **Database**: PostgreSQL 16
- **Reverse Proxy**: Caddy 2 (auto-TLS)

## Data Flow

```
OkTAP Export (.xls XML)
    │
    ▼
POST /api/oktap/import/{type}
    │
    ▼
oktap_parser.py (XML → Pydantic models)
    │
    ▼
Database INSERT (ledger_records / naics_records)
    │
    ▼
GET /api/cities/{copo}/ledger  ──▶  Frontend dashboard
GET /api/cities/{copo}/naics   ──▶  NAICS breakdown
analysis.py                    ──▶  Forecast + anomalies
```

## Project Structure

```
MuniRev/
├── backend/
│   ├── app/
│   │   ├── api/oktap.py          # OkTAP import endpoints
│   │   ├── db/
│   │   │   ├── connection.py     # SQLAlchemy engine + session
│   │   │   └── schema.sql        # Full PostgreSQL DDL
│   │   ├── models/orm.py         # SQLAlchemy ORM models
│   │   ├── schemas.py            # Pydantic API response models
│   │   ├── services/
│   │   │   ├── analysis.py       # Revenue analysis engine
│   │   │   ├── oktap_parser.py   # OkTAP XML SpreadsheetML parser
│   │   │   └── reporting.py      # HTML report generator
│   │   └── main.py               # FastAPI app + route registration
│   ├── assets/                   # Sample data files
│   ├── tests/                    # pytest suite + fixtures
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── main.ts               # SPA entry point (469 lines)
│   │   ├── styles.css            # Responsive CSS (459 lines)
│   │   └── types.ts              # TypeScript interfaces
│   └── vite.config.ts            # Dev proxy to backend
├── scripts/
│   ├── seed_jurisdictions.py     # Oklahoma city/county seed data
│   └── deploy.sh                 # Hetzner deployment script
├── plans/                        # Implementation roadmap
├── docs/                         # Architecture + data model docs
├── Dockerfile                    # Multi-stage (Node + Python)
├── docker-compose.yml            # app + postgres + caddy
├── Caddyfile                     # Reverse proxy config
└── CLAUDE.md                     # Project context for Claude Code
```

## Database

PostgreSQL 16. Core tables:

| Table | Purpose | Key Columns |
|---|---|---|
| jurisdictions | OK cities/counties | copo (PK), name, type, county |
| ledger_records | Monthly revenue time series | copo, tax_type, voucher_date, returned |
| naics_records | Revenue by industry | copo, tax_type, year, month, activity_code |
| naics_codes | NAICS reference data | code (PK), description, sector |
| data_imports | Import audit trail | report_type, filename, imported_at |
| anomalies | Detected anomalies | copo, severity, expected/actual, investigated |
| forecasts | Stored projections | copo, tax_type, forecast_date, bounds |

**Key indexes**: (copo, tax_type, voucher_date) for time-series queries, (activity_code) for cross-city NAICS analysis.

**Unique constraints** prevent duplicate imports: ledger keyed on (copo, tax_type, voucher_date), NAICS on (copo, tax_type, year, month, activity_code).

## API Endpoints

### Existing (working)
| Method | Path | Purpose |
|---|---|---|
| GET | /api/health | Health check |
| GET | /api/sample-data | Download sample xlsx |
| GET | /api/sample-report | Download sample PDF |
| POST | /api/analyze | Upload xlsx, get analysis JSON |
| POST | /api/report | Upload xlsx, get HTML report |

### OkTAP Import (working)
| Method | Path | Purpose |
|---|---|---|
| GET | /api/oktap/report-types | List supported report types |
| POST | /api/oktap/import/ledger | Import ledger .xls export |
| POST | /api/oktap/import/naics | Import NAICS .xls export |
| POST | /api/oktap/import/auto | Auto-detect and import |
| POST | /api/oktap/import/bulk | Import multiple files |

### Planned (Phase 1-2)
| Method | Path | Purpose |
|---|---|---|
| GET | /api/cities | List all jurisdictions |
| GET | /api/cities/{copo} | Jurisdiction detail |
| GET | /api/cities/{copo}/ledger | Ledger time series |
| GET | /api/cities/{copo}/naics | NAICS breakdown |
| GET | /api/cities/{copo}/forecast | Revenue forecast |
| GET | /api/cities/{copo}/anomalies | Detected anomalies |

## Deployment

**Target**: Hetzner Cloud CX23 (~$5/mo) running Docker Compose.

```
Internet ──▶ Caddy (:80/:443) ──▶ FastAPI (:8000) ──▶ PostgreSQL (:5432)
                                       │
                                  Frontend (static)
```

- **Caddy**: Automatic Let's Encrypt TLS, gzip, security headers
- **App container**: Non-root user, health check, 2 uvicorn workers
- **PostgreSQL**: Persistent volume, health check, 512MB memory limit
- **Backup**: pg_dump cron to off-site storage (planned)

## Data Source: OkTAP

Oklahoma Taxpayer Access Point at `oktap.tax.ok.gov`.

- **Ledger Reports**: 3 tax types (lodging, sales, use) x city x year
- **NAICS Reports**: 2 tax types (sales, use) x city x year x month
- **Export format**: XML SpreadsheetML (.xls), not binary Excel
- **Availability**: Past 5 years online; older data via "Archived Data" link
- **Update frequency**: Each business day
- **Scale**: ~600 municipalities + 77 counties, ~470 NAICS codes per city per month

## Scale Estimates (full statewide)

| Metric | Estimate |
|---|---|
| Jurisdictions | ~677 |
| Ledger records (5yr) | ~120K (677 x 3 types x 60 months) |
| NAICS records (5yr) | ~27M (677 x 2 types x 60 months x 350 avg codes) |
| Database size | ~5-10 GB |
| Monthly growth | ~500K NAICS rows |

PostgreSQL handles this comfortably on a single VPS. Table partitioning by year can be added if query performance degrades.
