# MuniRev

MuniRev is a TypeScript and Python re-platforming of the original CityTax R/Shiny tool.

The application is now organized as:

- `frontend/`: a TypeScript single-page app for uploads, report actions, and interactive analysis review.
- `backend/`: a Python FastAPI service that parses municipal tax spreadsheets, computes analysis, and generates a downloadable HTML report.
- `legacy-r/`: the original Rhino/Shiny implementation kept for migration reference.

## What Changed

The original project combined UI and analysis in an R/Shiny application backed by an RMarkdown PDF workflow. This refactor separates responsibilities so the product can live comfortably in the `MuniRev` GitHub repository:

- TypeScript handles the browser experience.
- Python handles spreadsheet parsing, analytics, and report rendering.
- The original R implementation is retained only as a reference during migration.

## Core Workflow

1. Upload an `.xlsx` municipal sales tax file.
2. Review summary metrics, monthly changes, seasonality, and a 12-month forecast.
3. Download a generated HTML report or the bundled sample assets.

## Quick Start (Local Deployment)

One command builds the frontend and starts everything on port 8000:

```bash
# Windows
start.bat

# Git Bash / WSL / macOS / Linux
bash start.sh
```

Then open http://127.0.0.1:8000 in your browser.

### Development (two processes)

For hot-reload during development, run the backend and frontend separately:

```bash
# Terminal 1 - Backend
cd backend
python -m venv .venv
.venv\Scripts\activate   # or source .venv/bin/activate on Linux/macOS
pip install -r requirements.txt
uvicorn app.main:app --reload

# Terminal 2 - Frontend (proxies /api to backend)
cd frontend
npm install
npm run dev
```

The Vite dev server runs on http://localhost:5173 and proxies `/api` requests to the backend at port 8000.

## API Security

The API now supports centralized hardening controls configured through environment variables in `.env.example`.

- Authentication modes:
  - `off`: local development
  - `token`: require `X-API-Key` or `Authorization: Bearer <token>`
  - `proxy`: trust an upstream identity header such as `X-Authenticated-User`
- Rate limiting:
  - token-bucket limiter applied centrally to `/api/*`
  - configurable request budget and window
  - `429` responses include `Retry-After` and rate-limit headers
- Transport / host hardening:
  - `TrustedHostMiddleware`
  - optional HTTPS redirect
  - strict response headers on API responses (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Cache-Control`)

### Recommended deployment posture

- Public browser app behind a reverse proxy / identity layer:
  - use `MUNIREV_API_AUTH_MODE=proxy`
  - have the proxy authenticate the user and inject `X-Authenticated-User`
  - enable `MUNIREV_FORCE_HTTPS=true`
  - set `MUNIREV_ALLOWED_HOSTS` and `MUNIREV_CORS_ORIGINS` explicitly
- Machine-to-machine API access:
  - use `MUNIREV_API_AUTH_MODE=token`
  - provision long random secrets in `MUNIREV_API_KEYS` or `MUNIREV_BEARER_TOKENS`

For a static frontend deployment, avoid embedding a long-lived API secret in browser code. Use proxy auth for browser traffic and token auth for server-side integrations.

## Notes On The Analytics Migration

The original R report used ANOVA, Tukey comparisons, and ARIMA forecasting. The Python version preserves the same business flow and analytical intent, while implementing:

- month-over-month and year-over-year change analysis
- seasonality summaries by month
- one-way ANOVA with a best-effort p-value when SciPy is installed
- a seasonally adjusted trend forecast with 12 future months

The forecast intentionally degrades gracefully if optional scientific packages are unavailable.
