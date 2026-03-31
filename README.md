# MuniRev

MuniRev is a TypeScript + Python municipal revenue analytics platform for Oklahoma local tax data. It combines a FastAPI backend, a Vite/TypeScript frontend, PostgreSQL for statewide data, and a forecasting pipeline that now persists forecast runs, predictions, backtests, and explainability metadata.

## What The Repo Contains

- `frontend/`: TypeScript SPA for exploration, forecasting, anomalies, rankings, exports, and upload/report workflows
- `backend/`: FastAPI application, forecasting services, OkTAP import parsing, and API tests
- `data/`: raw and parsed OkTAP snapshots used for import/bootstrap workflows
- `docs/`: architecture, data model, import, security, and deployment documentation
- `plans/`: roadmap and implementation planning documents
- `legacy-r/`: preserved R/Shiny reference implementation
- `deploy/hetzner/`: production-focused Compose + Caddy + oauth2-proxy assets for a Hetzner VM deployment

## Core Product Capabilities

- Municipal and county revenue exploration backed by PostgreSQL
- Forecasting by jurisdiction and NAICS activity with model comparison and explainability
- Statewide anomaly views and rankings
- Upload-based spreadsheet analysis for ad hoc files
- OkTAP `.xls` import parsing for ledger and NAICS exports

## Architecture

```
Browser
  |
  v
Caddy / oauth2-proxy (Hetzner production path)
  |
  v
FastAPI backend
  |
  v
PostgreSQL
```

For local development, the backend can run with auth disabled and serve the built frontend directly.

## Local Development

### Backend

```powershell
cd backend
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run build
```

### Database

```powershell
docker compose up -d postgres
```

## Security Model

The API now supports three security modes:

- `off`: local development only
- `token`: static API keys, static bearer tokens, or HS256 JWT bearer tokens
- `proxy`: trusted upstream identity headers, intended for oauth2-proxy / OIDC setups

Authorization is route-level, not just middleware-level:

- `api:read`: read-only endpoints
- `analysis:run`: upload analysis endpoint
- `reports:generate`: report generation endpoint
- `data:import`: OkTAP import endpoints
- `api:admin`: operational security endpoint

Default roles map to scopes:

- `viewer`
- `analyst`
- `operator`
- `service`
- `admin`

See [docs/api-security.md](c:/Users/brian/GitHub/CityTax/docs/api-security.md) for the full model.

## Hetzner Recommendation

For this project shape, the recommended production path is a single Hetzner VM running:

- Docker Compose
- Caddy for TLS and reverse proxy
- oauth2-proxy for browser SSO
- FastAPI app container
- PostgreSQL container

That keeps cost low while still letting us do auth at the proxy and authorization inside the app. The deployment assets are under `deploy/hetzner/`.

Start with:

- [docs/hetzner-deployment.md](c:/Users/brian/GitHub/CityTax/docs/hetzner-deployment.md)
- [deploy/hetzner/docker-compose.yml](c:/Users/brian/GitHub/CityTax/deploy/hetzner/docker-compose.yml)
- [deploy/hetzner/Caddyfile](c:/Users/brian/GitHub/CityTax/deploy/hetzner/Caddyfile)
- [deploy/hetzner/.env.hetzner.example](c:/Users/brian/GitHub/CityTax/deploy/hetzner/.env.hetzner.example)

## Tests

```powershell
cd backend
.venv\Scripts\python -m pytest tests\ -v
```

The suite covers:

- upload analysis
- OkTAP parsing
- forecasting support
- API behavior against the live database
- security/auth/rate-limiting behavior

## Key Docs

- [architecture.md](c:/Users/brian/GitHub/CityTax/docs/architecture.md)
- [data-model.md](c:/Users/brian/GitHub/CityTax/docs/data-model.md)
- [data-import-guide.md](c:/Users/brian/GitHub/CityTax/docs/data-import-guide.md)
- [api-security.md](c:/Users/brian/GitHub/CityTax/docs/api-security.md)
- [hetzner-deployment.md](c:/Users/brian/GitHub/CityTax/docs/hetzner-deployment.md)
- [continue.md](c:/Users/brian/GitHub/CityTax/continue.md)
