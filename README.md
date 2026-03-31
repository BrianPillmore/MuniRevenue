# MuniRevenue

**Municipal Revenue Intelligence for Oklahoma**

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

## Configuration

Copy `.env.example` to `.env` and fill in your values. See the example file for all available options.

## Documentation

- [Architecture](docs/architecture.md)
- [Data Model](docs/data-model.md)
- [Data Import Guide](docs/data-import-guide.md)
- [API Security](docs/api-security.md)

## License

MIT License. See [LICENSE](LICENSE).
