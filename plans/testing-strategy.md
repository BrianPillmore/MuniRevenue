# MuniRev Testing Strategy

## Goals

The test strategy should protect four things:

1. ingestion correctness
2. API correctness
3. forecasting correctness
4. security and deployment correctness

## Current Coverage Areas

### Parsing and analysis

- spreadsheet upload analysis
- OkTAP parser behavior
- OkTAP retriever behavior

### API coverage

- municipal and statewide endpoints
- forecast endpoints
- security behavior:
  - auth required vs exempt
  - scope/role enforcement
  - JWT bearer support
  - proxy-auth role expansion
  - rate limiting

### Forecasting coverage

- forecast response shaping
- quality gating
- persistence support
- API parameter validation

## Required Ongoing Test Layers

### Unit tests

Protect:

- security scope expansion
- JWT validation helpers
- forecast model selection helpers
- data-quality classification helpers

### API tests

Protect:

- authorization on every route family
- forecast compare/drivers endpoints
- export and report endpoints
- OkTAP import authorization
- admin/ops endpoints

### Integration tests

Protect:

- PostgreSQL-backed forecast generation
- persistence of forecast runs/predictions/backtests
- realistic municipality paths such as Yukon sales
- sparse-series fallback paths
- gap-affected forecast warnings

### Deployment smoke tests

Protect:

- app starts with production env
- `/api/health` stays exempt
- proxy-auth header contract works
- Caddy and oauth2-proxy route requests correctly

## Immediate Gaps To Close

- [ ] add direct unit tests for scope implication rules
- [ ] add tests for `/api/auth/me` and `/api/admin/security`
- [ ] add a deployment smoke test for the Hetzner compose stack
- [ ] add frontend type-check and test jobs into CI
- [ ] add migration smoke test before app startup in production automation

## Recommended CI Shape

1. backend unit + API tests
2. frontend build + type-check
3. migration lint / upgrade check
4. optional containerized smoke test for deploy assets

## Manual Release Checklist

Before each production push:

1. run backend tests
2. run frontend build
3. confirm alembic head is current
4. verify `.env` / deployment env additions are documented
5. verify auth mode and allowed hosts for the target environment
