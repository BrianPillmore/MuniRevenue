# MuniRev Architecture

## Current System Shape

MuniRev is a monorepo with a TypeScript frontend, a FastAPI backend, and PostgreSQL as the operational data store for statewide municipal revenue analytics.

```
Frontend SPA
   |
   v
FastAPI application
   |
   +--> Forecasting services
   +--> OkTAP parsing / upload analysis services
   +--> Security middleware + authorization layer
   |
   v
PostgreSQL
```

In production on Hetzner, the expected edge stack is:

```
Internet
   |
   v
Caddy
   |
   +--> oauth2-proxy (browser authentication)
   |
   v
FastAPI
   |
   v
PostgreSQL
```

## Major Components

### Frontend

- Built with Vite and TypeScript
- Vanilla module-based SPA, no heavyweight framework
- Reads from the `/api/*` surface and renders:
  - overview KPIs
  - jurisdiction explorer
  - compare view
  - forecasts
  - anomalies
  - rankings
  - trends
  - exports

### Backend

The backend has four main responsibilities:

1. Serve operational read APIs from PostgreSQL
2. Parse upload workflows and OkTAP exports
3. Generate forecasts and persist forecast run metadata
4. Enforce security controls: auth, authorization, headers, and rate limiting

Key backend modules:

- `backend/app/main.py`: app factory, middleware, router registration, upload/report endpoints
- `backend/app/security.py`: auth context, HS256 JWT validation, role/scope authorization, rate limiting
- `backend/app/api/cities.py`: municipal, county, forecast, export, and anomaly endpoints
- `backend/app/api/analytics.py`: statewide analytics and rankings
- `backend/app/api/oktap.py`: OkTAP import endpoints
- `backend/app/api/system.py`: auth introspection and admin security status endpoints
- `backend/app/services/forecasting.py`: municipal and NAICS forecasting framework

### Database

PostgreSQL stores:

- jurisdictions
- ledger records
- NAICS records
- anomalies
- legacy forecast rows
- forecast run framework tables
- economic indicator rows

The forecasting source of truth is now the database, not parsed CSV snapshots.

## Security Architecture

Security is layered:

1. Network / edge
   - TLS at Caddy
   - host enforcement
   - optional proxy-auth via oauth2-proxy
2. Application middleware
   - request IDs
   - security headers
   - authentication
   - rate limiting
3. Route authorization
   - `api:read`
   - `analysis:run`
   - `reports:generate`
   - `data:import`
   - `api:admin`

Auth modes:

- `off`: dev only
- `token`: static secrets or HS256 JWT bearer tokens
- `proxy`: trusted identity forwarded from a reverse proxy / SSO layer

Roles expand into scopes:

- `viewer` -> `api:read`
- `analyst` -> `api:read`, `analysis:run`, `reports:generate`
- `operator` -> analyst scopes plus `data:import`
- `service` -> operator-style service automation defaults
- `admin` -> `api:admin` and implied scopes

## Forecasting Architecture

The forecasting layer supports:

- baseline seasonal trend
- SARIMA/SARIMAX
- Prophet
- ensemble forecasts
- rolling backtests
- explainability payloads
- municipal and NAICS-level scopes

The backend persists:

- `forecast_runs`
- `forecast_predictions`
- `forecast_backtests`
- `economic_indicators`

That makes each forecast reproducible and comparable.

## Deployment Guidance

### Local / development

- auth may be `off`
- frontend can be built locally and served by FastAPI
- CORS allowlist points at local Vite origins

### Hetzner / recommended production

- single VM
- Docker Compose
- root disk with regular volume backups
- Caddy + oauth2-proxy at the edge
- FastAPI in `proxy` auth mode
- rate limiting enabled

This is the lowest-complexity production shape that still keeps browser credentials out of the SPA and gives us a clean path to OIDC SSO.
