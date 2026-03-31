# MuniRev Platform Plan

## Current State

The project is beyond the original “phase 1” framing. The platform now has:

- TypeScript SPA with statewide exploration views
- FastAPI backend serving municipal, county, anomaly, ranking, export, and forecast APIs
- PostgreSQL-backed runtime data model
- forecasting persistence tables and explainability payloads
- API security middleware plus route-level authorization
- a concrete Hetzner deployment path using Caddy + oauth2-proxy

## Now Complete

- OkTAP parsing for ledger and NAICS exports
- database-backed read APIs
- statewide dashboard views
- persisted forecasting framework:
  - `forecast_runs`
  - `forecast_predictions`
  - `forecast_backtests`
  - `economic_indicators`
- security foundation:
  - auth modes
  - route scopes
  - request IDs
  - rate limiting
  - trusted proxy support
- Hetzner deployment assets under `deploy/hetzner/`

## Priority 1: Production Readiness

- [x] Centralize API security behavior
- [x] Add role/scope authorization
- [x] Document Hetzner deployment pattern
- [ ] Add automated backup/restore runbook execution scripts
- [ ] Add structured application logging
- [ ] Add database migration check to deployment workflow
- [ ] Add secret-rotation guidance and operational checklist

## Priority 2: Forecasting Depth

- [x] Multi-model framework scaffolding
- [x] backtest persistence and explainability payloads
- [ ] improve indicator ingestion pipeline
- [ ] schedule municipal forecast precompute after data refresh
- [ ] add cached NAICS top-industry forecast generation
- [ ] tighten data-quality gating around missing month coverage
- [ ] improve export/report output for forecast comparison and drivers

## Priority 3: Product Hardening

- [ ] frontend test coverage
- [ ] linting and formatting standards across frontend/backend
- [ ] background job strategy for import + anomaly + forecast pipelines
- [ ] admin/ops dashboard for import status, forecast freshness, and failures
- [ ] backup verification workflow

## Recommended Near-Term Sequencing

1. Finish deployment/operations automation for Hetzner.
2. Stabilize auth role mapping with the chosen identity provider.
3. Add scheduled jobs for data refresh, anomaly detection, and forecast refresh.
4. Expand forecast indicator ingestion and backtesting coverage.
