# MuniRev Architecture

## Current System Shape

MuniRev is a monorepo with:

- a TypeScript SPA frontend
- a FastAPI backend
- PostgreSQL as the operational datastore

The app now combines three major product surfaces:

1. Public municipal revenue exploration
2. Authenticated investigation workflows
3. Data import / forecasting / reporting operations

```
Frontend SPA
   |
   v
FastAPI application
   |
   +--> Security middleware
   +--> Browser auth + account/profile services
   +--> Analytics APIs
   +--> Forecasting services
   +--> OkTAP parsing / import services
   |
   v
PostgreSQL
```

## Production Edge Shapes

### Base Hetzner stack

```
Internet
   |
   v
Caddy
   |
   v
FastAPI
   |
   v
PostgreSQL
```

### Optional OIDC overlay

```
Internet
   |
   v
Caddy
   |
   +--> oauth2-proxy
   |
   v
FastAPI
   |
   v
PostgreSQL
```

### First-party browser auth

When using magic-link login, the browser still talks directly to the SPA + FastAPI stack, but FastAPI owns login, session issuance, and account/profile storage.

## Major Components

### Frontend

- Vite + TypeScript
- vanilla modular SPA
- path-based routing
- public routes plus protected product routes

Primary UI areas:

- overview
- city explorer
- county view
- rankings / trends / compare / export
- forecasts
- anomalies
- missed filings
- login
- account/profile

Protected routes:

- `/forecast`
- `/forecast/:copo`
- `/anomalies`
- `/missed-filings`
- `/account`

### Backend

The backend now has five main responsibilities:

1. Serve operational read APIs from PostgreSQL
2. Support browser auth and user account/profile workflows
3. Parse upload workflows and OkTAP imports
4. Generate forecasts and persist forecast metadata
5. Enforce security controls: auth, authorization, headers, rate limiting, and request-origin checks

Key backend modules:

- `backend/app/main.py`
- `backend/app/security.py`
- `backend/app/user_auth.py`
- `backend/app/db/psycopg.py`
- `backend/app/api/account.py`
- `backend/app/api/cities.py`
- `backend/app/api/analytics.py`
- `backend/app/api/oktap.py`
- `backend/app/api/system.py`
- `backend/app/services/forecasting.py`

### Database

PostgreSQL stores:

- jurisdictions
- ledger records
- NAICS records
- anomalies
- missed-filing cache and refresh metadata
- forecast framework tables
- economic indicators
- browser-auth/account tables

The operational source of truth is PostgreSQL, not flat parsed CSVs.

## Security Architecture

Security is layered:

1. Network / edge
   - TLS at Caddy
   - host enforcement
   - optional proxy-auth / OIDC
2. Application middleware
   - request IDs
   - security headers
   - auth-mode evaluation
   - browser-session resolution
   - rate limiting
   - trusted-origin checks for unsafe browser writes
   - mixed-mode public/protected API handling
3. Route authorization
   - scope-based machine access
   - browser-session feature access for protected product routes

Supported auth modes:

- `off`
- `token`
- `proxy`

First-party browser auth is an additional capability layered on top of those modes, not a separate machine-auth mode.

## Browser Auth / Account Architecture

The repo now contains a first-party browser auth subsystem.

It supports:

- magic-link login
- session cookies
- user profile data
- jurisdiction interests
- saved forecast defaults
- saved anomaly follow-ups
- saved missed-filing follow-ups

The key design choices are:

- raw login tokens are never stored directly
- session cookies are `HttpOnly`
- `/auth/verify` consumes the raw token server-side
- protected SPA routes are enforced both client-side and server-side

## Forecasting Architecture

The forecasting layer supports:

- baseline seasonal trend
- SARIMA / SARIMAX
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

## Missed-Filings Architecture

The missed-filings feature is now an exhaustive rolling-window cache, not a top-N heuristic shortlist.

Important properties:

- rolling prior 24 months
- sales and use tax only
- per city / month / 6-digit NAICS
- multiple run-rate methods
- UI-tunable materiality and severity thresholds
- persisted refresh metadata

Operational tables:

- `missed_filing_candidates`
- `missed_filing_candidates_refresh_meta`

## Public SEO Surface vs App Surface

The repo now also has an SEO/public-content surface that is distinct from the authenticated app surface.

Examples of public SEO content:

- `/`
- `/oklahoma-cities`
- `/oklahoma-counties`
- generated city/county landing pages
- `/insights/anomalies`
- `/insights/missed-filings`

Examples of protected app functionality:

- forecast UI
- anomalies investigation UI
- missed-filings workflow UI
- account/profile UI

## Deployment Guidance

### Local / development

- machine auth may be `off`
- browser magic-link auth may be enabled with `MUNIREV_EMAIL_MODE=log`
- frontend is built locally and served by FastAPI

### Hetzner / recommended production

Base recommendation:

- single VM
- Docker Compose
- Caddy
- FastAPI
- PostgreSQL

Browser auth decision still needs to be made per environment:

- first-party magic-link
- OIDC proxy
- or hybrid

## Current Operational Reality

The codebase now supports both of these futures:

1. first-party authenticated product workflows owned by the app
2. stronger SSO-driven deployments through `oauth2-proxy`

The next production decision should choose which of those becomes primary.
