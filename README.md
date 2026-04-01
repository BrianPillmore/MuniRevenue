# MuniRevenue

## Municipal Revenue Intelligence for Oklahoma

MuniRevenue helps city managers, finance directors, mayors, and county commissioners understand, forecast, and act on their tax revenue data. Built with publicly available data from the Oklahoma Tax Commission.

**Live at [munirevenue.com](https://munirevenue.com)**

## What It Does

- **Revenue Explorer** — Drill into any Oklahoma city or county's sales, use, and lodging tax history
- **Industry Breakdown** — See which NAICS industries drive your city's economy
- **Forecasting** — 12-month revenue projections with confidence intervals
- **Anomaly Detection** — Automatic flagging of unusual revenue changes with industry decomposition
- **Statewide Rankings** — Compare jurisdictions by total revenue, growth rate, or peer group
- **Seasonality Analysis** — Identify predictable monthly patterns in your revenue
- **Data Export** — Download revenue data, forecasts, and charts as CSV, PNG, or SVG

## Data

- **644 jurisdictions** (567 cities + 77 counties)
- **78,756 monthly ledger records** (sales, use, lodging tax)
- **9,057,555 NAICS industry records**
- **Coverage:** 2020–2026
- **Source:** Oklahoma Tax Commission public reports

## Tech Stack

- **Frontend:** TypeScript, Vite, Highcharts
- **Backend:** Python, FastAPI, PostgreSQL
- **Deployment:** Docker Compose, Caddy (auto-TLS), Hetzner

## Quick Start (Local Development)

```bash
# Prerequisites: Python 3.13+, Node 20+, Docker

# Start PostgreSQL
docker compose up -d postgres

# Backend
cd backend
python -m venv .venv
.venv/Scripts/activate  # or source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## Verified Local Checks

These commands were validated locally in this repository:

```bash
# Frontend production build
cd frontend
npm run build

# Frontend type-check
cd frontend
npx tsc --noEmit

# Backend test suite
cd backend
.venv/Scripts/python -m pytest tests -v

# Repo-root backend test invocation
cd ..
backend/.venv/Scripts/python -m pytest backend/tests -v
```

## Local Docker Smoke Deploy

For a containerized smoke test of the packaged app and SPA shell, use:

```bash
docker compose -f docker-compose.local.yml up --build
```

This local Compose file is intentionally minimal and does not provision the full Postgres-backed analytics dataset. It is meant to verify the container build, the `/api/health` endpoint, and SPA serving at `http://127.0.0.1:8000`.

## Local Postgres Bootstrap

If you want a real Postgres-backed local dataset from the checked-in raw OkTAP files:

```bash
# Start PostgreSQL
docker compose up -d postgres

# Initialize the schema and forecast support tables
cd backend
.venv/Scripts/python ../scripts/init_db.py

# Load raw ledger + NAICS data
.venv/Scripts/python ../scripts/load_data.py
```

For a smaller validation run before a full import:

```bash
cd backend
.venv/Scripts/python ../scripts/load_data.py --ledger-limit 1 --naics-limit 1
```

Economic indicator ETL is separate and optional:

```bash
cd ..
backend/.venv/Scripts/python -m etl.bls.run
backend/.venv/Scripts/python -m etl.census.run
backend/.venv/Scripts/python -m etl.fred.run
```

## Configuration

Copy `.env.example` to `.env` and fill in your values. See the example file for all available options.

## Documentation

- [Architecture](docs/architecture.md)
- [Data Model](docs/data-model.md)
- [Data Import Guide](docs/data-import-guide.md)
- [API Security](docs/api-security.md)

## License

MIT License. See [LICENSE](LICENSE).
