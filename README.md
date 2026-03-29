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

## Notes On The Analytics Migration

The original R report used ANOVA, Tukey comparisons, and ARIMA forecasting. The Python version preserves the same business flow and analytical intent, while implementing:

- month-over-month and year-over-year change analysis
- seasonality summaries by month
- one-way ANOVA with a best-effort p-value when SciPy is installed
- a seasonally adjusted trend forecast with 12 future months

The forecast intentionally degrades gracefully if optional scientific packages are unavailable.
