# MuniRev — Continue From Here

**Last updated:** 2026-03-31  
**Repo target:** https://github.com/BrianPillmore/MuniRevenue  
**Planned production domain:** https://munirevenue.com  
**Local path:** `C:\Users\brian\GitHub\CityTax`

## Current State

MuniRev is now a database-backed municipal analytics app with:

- TypeScript SPA frontend
- FastAPI backend
- PostgreSQL runtime data store
- persisted forecasting framework
- API security middleware plus route-level authorization
- documented Hetzner deployment assets

## What Is Working

### Product surface

- statewide overview, trends, anomalies, rankings, compare, export, county, and forecast views
- revenue explorer by municipality
- upload-based spreadsheet analysis and HTML report generation
- forecast compare/drivers endpoints and explainability payloads

### Data and forecasting

- `644` jurisdictions in the database
- ~`78k` ledger rows
- ~`9.0M` NAICS rows
- `24k+` anomalies
- forecast persistence tables:
  - `forecast_runs`
  - `forecast_predictions`
  - `forecast_backtests`
  - `economic_indicators`

### Security

- request IDs on API responses
- security headers
- host enforcement
- optional HTTPS redirect
- token bucket rate limiting
- auth modes:
  - `off`
  - `token`
  - `proxy`
- route scopes:
  - `api:read`
  - `analysis:run`
  - `reports:generate`
  - `data:import`
  - `api:admin`
- ops endpoints:
  - `/api/auth/me`
  - `/api/admin/security`

## Recommended Production Path

Current recommendation: **Hetzner single VM**

Reason:

- lowest-cost operationally reasonable path
- easy fit for Docker Compose
- lets us keep browser auth at the proxy with oauth2-proxy
- app remains responsible for authorization and rate limiting

Deployment assets:

- `deploy/hetzner/docker-compose.yml`
- `deploy/hetzner/Caddyfile`
- `deploy/hetzner/.env.hetzner.example`
- `docs/hetzner-deployment.md`

Recommended starter machine:

- `CPX31` on Hetzner for the first production box
- `CPX41` if we want more comfortable headroom for imports + forecasting + Postgres on one VM

## Security Notes

Recommended production mode:

- `MUNIREV_API_AUTH_MODE=proxy`
- Caddy in front
- oauth2-proxy providing OIDC login
- app trusting `X-Auth-Request-*` headers only from the proxy

Planned production env values:

- `DOMAIN=munirevenue.com`
- `MUNIREV_ALLOWED_HOSTS=munirevenue.com,www.munirevenue.com`
- `MUNIREV_CORS_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_CSRF_TRUSTED_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_FORCE_HTTPS=true`
- `MUNIREV_OPENAPI_ENABLED=false`

Service integrations can use:

- static tokens for limited internal cases
- HS256 JWTs for better machine-to-machine access

## Key Files

### Backend

- `backend/app/main.py`
- `backend/app/security.py`
- `backend/app/api/cities.py`
- `backend/app/api/analytics.py`
- `backend/app/api/oktap.py`
- `backend/app/api/system.py`
- `backend/app/services/forecasting.py`

### Frontend

- `frontend/src/main.ts`
- `frontend/src/api.ts`
- `frontend/src/views/forecast.ts`

### Docs / plans

- `README.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/api-security.md`
- `docs/hetzner-deployment.md`
- `plans/v1-platform.md`
- `plans/testing-strategy.md`
- `plans/database-design.md`

## Verification Snapshot

Last completed verification in this workstream:

- backend security tests passed
- full backend suite passed: `142` tests, `5` skipped
- frontend build had previously passed

## Things To Watch

- The rate limiter is in-memory. That is okay for the recommended single-VM Hetzner deployment, but not for multi-node scaling.
- Proxy-auth group mapping will need to match the chosen OIDC provider’s group/claim behavior.
- Forecast/data-model docs were updated to reflect the newer persistence structure; older notes elsewhere may still reference the legacy `forecasts` table.

## Important Repo-State Note

There are unrelated frontend modifications that were already present and were intentionally left alone:

- `frontend/src/components/chart-controls.ts`
- `frontend/src/views/anomalies.ts`
- `frontend/src/views/rankings.ts`

Do not revert or overwrite those casually.

## Best Next Steps

1. Choose the OIDC provider for Hetzner deployment and map groups to `viewer` / `analyst` / `operator` / `admin`.
2. Add deployment smoke tests for the Hetzner compose stack.
3. Add backup automation and a restore rehearsal runbook.
4. Add a canonical-domain redirect plan so `www.munirevenue.com` points to `munirevenue.com`.
5. If desired, prepare commit/push to the `MuniRevenue` GitHub repo once repo-state is reviewed.
