# MuniRev

Oklahoma municipal revenue intelligence platform. Ingests tax data from OkTAP, stores in PostgreSQL, forecasts revenue, detects anomalies, and analyzes by NAICS industry.

## Tech Stack

- **Frontend**: TypeScript, Vite, vanilla DOM (no framework)
- **Backend**: Python 3.13, FastAPI, Pandas, NumPy, SciPy, SQLAlchemy 2.0
- **Database**: PostgreSQL 16 (dev can use SQLite fallback)
- **Deployment**: Docker Compose, Caddy, Hetzner VPS

## Local Development

```bash
# Backend
cd backend && python -m venv .venv && .venv/Scripts/activate && pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Or use `start.bat` / `bash start.sh` for single-process production mode.

## Project Structure

- `backend/app/api/` — FastAPI route modules
- `backend/app/services/` — Business logic (analysis, oktap_parser, reporting)
- `backend/app/models/` — SQLAlchemy ORM models
- `backend/app/db/` — Database schema and connection
- `frontend/src/` — TypeScript SPA source
- `scripts/` — Data import and seed scripts
- `plans/` — Implementation plans
- `docs/` — Architecture and data model docs
- `tests/` — Integration tests

## Key Commands

```bash
# Run backend tests
cd backend && .venv/Scripts/python -m pytest tests/ -v

# Build frontend
cd frontend && npm run build

# Type-check frontend
cd frontend && npx tsc --noEmit
```

## Data Source

OkTAP (Oklahoma Taxpayer Access Point): `oktap.tax.ok.gov`
- Ledger Reports: monthly revenue by city/county and tax type
- NAICS Reports: monthly revenue by industry code
- Export format: XML SpreadsheetML (.xls)
