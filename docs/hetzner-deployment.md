# Hetzner Deployment Guide

## Recommended Shape

Current recommended production infrastructure remains:

- one Hetzner VM
- Docker Engine + Docker Compose
- Caddy for TLS and reverse proxy
- FastAPI application container
- PostgreSQL container

Optional browser-auth overlay:

- `oauth2-proxy` for OIDC / SSO

The repo now also supports first-party browser auth via magic links, so production auth posture is a real deployment decision rather than a docs-only future idea.

## Suggested VM Size

Recommended first box:

- `CPX31`

Safer headroom option:

- `CPX41`

## Deployment Assets

Deployment assets live in:

- [docker-compose.yml](/C:/Users/brian/GitHub/MuniRevenue/deploy/hetzner/docker-compose.yml)
- [Caddyfile](/C:/Users/brian/GitHub/MuniRevenue/deploy/hetzner/Caddyfile)
- [docker-compose.oidc.yml](/C:/Users/brian/GitHub/MuniRevenue/deploy/hetzner/docker-compose.oidc.yml)
- [Caddyfile.oidc](/C:/Users/brian/GitHub/MuniRevenue/deploy/hetzner/Caddyfile.oidc)
- [.env.hetzner.example](/C:/Users/brian/GitHub/MuniRevenue/deploy/hetzner/.env.hetzner.example)

## First-Time Server Setup

1. Provision the VM.
2. Point DNS at the server IP.
3. Install Docker Engine and the Docker Compose plugin.
4. Clone the repo.
5. Copy `deploy/hetzner/.env.hetzner.example` to `deploy/hetzner/.env.hetzner`.
6. Fill in:
   - domain
   - PostgreSQL password
   - auth posture
   - browser-auth settings if used
7. Start the base stack:

```bash
cd /path/to/MuniRevenue
docker compose -f deploy/hetzner/docker-compose.yml --env-file deploy/hetzner/.env.hetzner up --build -d
```

## Production Auth Decision

### Option A — First-party magic-link auth

Use the app’s built-in browser auth.

Required env:

- `MUNIREV_AUTH_MAGIC_LINK_ENABLED=true`
- `MUNIREV_AUTH_MAGIC_LINK_BASE_URL=https://munirevenue.com`
- `MUNIREV_AUTH_SESSION_SECRET=<strong random secret>`
- `MUNIREV_EMAIL_MODE=smtp`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS=true`
- `MUNIREV_EMAIL_FROM`

Recommended:

- keep `MUNIREV_AUTH_COOKIE_SECURE=true`
- keep `MUNIREV_AUTH_COOKIE_SAMESITE=lax`
- leave API docs disabled in production

### Option B — OIDC overlay

Use:

- `MUNIREV_API_AUTH_MODE=proxy`
- `oauth2-proxy`
- OIDC issuer / client configuration

Start with overlay:

```bash
cd /path/to/MuniRevenue
docker compose \
  -f deploy/hetzner/docker-compose.yml \
  -f deploy/hetzner/docker-compose.oidc.yml \
  --env-file deploy/hetzner/.env.hetzner \
  up --build -d
```

### Option C — Hybrid

Keep first-party browser auth for product users while still supporting `token` or `proxy` for integrations/admin access.

This is well-supported by the current code.

## Base Security Settings

Typical base values:

- `DOMAIN=munirevenue.com`
- `MUNIREV_ALLOWED_HOSTS=munirevenue.com,www.munirevenue.com`
- `MUNIREV_CORS_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_CSRF_TRUSTED_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_RATE_LIMIT_ENABLED=true`
- `MUNIREV_TRUST_X_FORWARDED_FOR=true`
- `MUNIREV_OPENAPI_ENABLED=false`

If using the OIDC overlay:

- `MUNIREV_API_AUTH_MODE=proxy`
- `MUNIREV_FORCE_HTTPS=true`

If using first-party magic-link browser auth:

- `MUNIREV_AUTH_MAGIC_LINK_ENABLED=true`
- keep the SMTP settings populated

## Machine-To-Machine Access

For automation and operational tooling:

- use `token` mode or hybrid support
- issue narrow JWT or service-token credentials
- do not reuse human browser auth credentials for automation

## Backup And Operations

Minimum ops expectations:

- scheduled PostgreSQL dumps
- off-server backup retention
- system patching cadence
- TLS / certificate monitoring
- auth failure review
- email delivery monitoring if using magic-link auth

## Smoke Checks After Deploy

Always verify:

1. `GET /api/health` returns `200`
2. SPA loads over `https://munirevenue.com`
3. public SEO pages still load:
   - `/`
   - `/oklahoma-cities`
   - `/oklahoma-counties`
   - `/insights/anomalies`
   - `/insights/missed-filings`
4. protected app routes redirect or load correctly:
   - `/login`
   - `/account`
   - `/forecast`
   - `/anomalies`
   - `/missed-filings`

If using first-party magic-link auth, also verify:

1. `POST /api/auth/magic-link/request` succeeds from the live origin
2. magic-link email is delivered
3. `/auth/verify` sets the session cookie and redirects correctly
4. saved profile/preferences/follow-up flows work

If using the OIDC overlay, also verify:

1. unauthenticated browser request redirects into OIDC
2. authenticated user can load the protected SPA routes
3. `GET /api/auth/me` shows the expected subject/roles
4. admin access works for `GET /api/admin/security`

## Operational Reality To Remember

The deployment docs should not assume proxy/OIDC is the only production browser-auth path anymore.

The repo now supports:

- public exploration
- authenticated product workflows
- machine-auth operations

Choose the production auth posture intentionally before deploy.
