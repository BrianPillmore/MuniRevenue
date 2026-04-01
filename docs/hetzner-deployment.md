# Hetzner Deployment Guide

## Recommended Shape

For MuniRev, the recommended low-cost production setup is:

- one Hetzner VM
- Docker Engine + Docker Compose
- Caddy for TLS and reverse proxy
- FastAPI application container
- PostgreSQL container

Optional hardening layer:

- oauth2-proxy for OIDC login

Why this is the current recommendation:

- lower monthly cost than many managed platforms
- simple operational model for a single internal/public app
- easy to operate even before browser SSO is wired up
- clean fit for proxy-auth with route-level authorization inside the app when we enable the OIDC overlay

## Suggested VM Size

Recommended first production box:

- `CPX31`

Safer headroom option:

- `CPX41`

Why:

- this app is not just a static site and API
- we plan to run FastAPI, PostgreSQL, Caddy, oauth2-proxy, and forecasting/import workloads on one VM
- `CPX31` is a better fit than the smaller `CX` floor for steady application + database usage

If forecasting jobs or imports become heavier, move up to `CPX41` before splitting the architecture.

## Directory And Files

Deployment assets live in:

- [docker-compose.yml](c:/Users/brian/GitHub/CityTax/deploy/hetzner/docker-compose.yml)
- [Caddyfile](c:/Users/brian/GitHub/CityTax/deploy/hetzner/Caddyfile)
- [docker-compose.oidc.yml](c:/Users/brian/GitHub/CityTax/deploy/hetzner/docker-compose.oidc.yml)
- [Caddyfile.oidc](c:/Users/brian/GitHub/CityTax/deploy/hetzner/Caddyfile.oidc)
- [.env.hetzner.example](c:/Users/brian/GitHub/CityTax/deploy/hetzner/.env.hetzner.example)

## First-Time Server Setup

1. Provision the VM in Hetzner Cloud.
2. Point your DNS record at the server IP.
3. Install Docker Engine and Docker Compose plugin.
4. Clone the repo onto the VM.
5. Copy `deploy/hetzner/.env.hetzner.example` to `deploy/hetzner/.env.hetzner`.
6. Fill in:
   - domain
   - PostgreSQL password
   - app security mode
7. Start the stack:

```bash
cd /path/to/MuniRevenue
docker compose -f deploy/hetzner/docker-compose.yml --env-file deploy/hetzner/.env.hetzner up --build -d
```

The base stack matches the current live production posture:

- `Caddy -> FastAPI -> PostgreSQL`
- no oauth2-proxy service in front of the app
- `MUNIREV_API_AUTH_MODE=off`
- `www.munirevenue.com` redirected to `munirevenue.com`

## Optional OIDC Overlay

If you want browser SSO, add:

- OIDC issuer/client settings
- oauth2-proxy cookie secret
- `MUNIREV_API_AUTH_MODE=proxy`
- `MUNIREV_FORCE_HTTPS=true`
- `MUNIREV_OPENAPI_ENABLED=false`

Then start with the overlay too:

```bash
cd /path/to/MuniRevenue
docker compose \
  -f deploy/hetzner/docker-compose.yml \
  -f deploy/hetzner/docker-compose.oidc.yml \
  --env-file deploy/hetzner/.env.hetzner \
  up --build -d
```

## OIDC Auth Flow

When the overlay is enabled, the auth path is:

1. User hits `https://munirevenue.com`
2. Caddy forwards auth checks to oauth2-proxy
3. oauth2-proxy redirects to your OIDC provider if needed
4. oauth2-proxy returns trusted identity headers
5. FastAPI runs route authorization using roles/scopes from those headers

Recommended OIDC group mapping:

- `viewer`
- `analyst`
- `operator`
- `admin`

That keeps authorization rules understandable and consistent with the app.

## App Security Settings

Current live-compatible base values in `.env.hetzner`:

- `DOMAIN=munirevenue.com`
- `MUNIREV_API_AUTH_MODE=off`
- `MUNIREV_RATE_LIMIT_ENABLED=true`
- `MUNIREV_TRUST_X_FORWARDED_FOR=true`
- `MUNIREV_FORCE_HTTPS=false`
- `MUNIREV_ALLOWED_HOSTS=munirevenue.com,www.munirevenue.com`
- `MUNIREV_CORS_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_CSRF_TRUSTED_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_OPENAPI_ENABLED=false`

Recommended hardened OIDC values:

- `MUNIREV_API_AUTH_MODE=proxy`
- `MUNIREV_PROXY_SUBJECT_HEADERS=X-Auth-Request-Email,X-Auth-Request-User`
- `MUNIREV_PROXY_ROLE_HEADERS=X-Auth-Request-Groups`
- `MUNIREV_PROXY_DEFAULT_ROLES=viewer`
- `MUNIREV_RATE_LIMIT_ENABLED=true`
- `MUNIREV_TRUST_X_FORWARDED_FOR=true`
- `MUNIREV_FORCE_HTTPS=true`
- `MUNIREV_ALLOWED_HOSTS=munirevenue.com,www.munirevenue.com`
- `MUNIREV_CORS_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_CSRF_TRUSTED_ORIGINS=https://munirevenue.com,https://www.munirevenue.com`
- `MUNIREV_OPENAPI_ENABLED=false`

Canonical host recommendation:

- serve `munirevenue.com` as canonical
- redirect `www.munirevenue.com` to `munirevenue.com`

## Machine-To-Machine Access

If you later need API access for automation:

- keep browser auth on proxy mode
- issue HS256 JWTs or tightly scoped service tokens for backend jobs
- separate those credentials from human browser login

That lets us support both SSO users and automation without embedding secrets in the frontend.

## Backup And Operations

Minimum production operations:

- scheduled PostgreSQL dumps
- off-server backup retention
- image/package patching cadence
- TLS/domain monitoring
- request log review and auth failure review

Recommended first backup path:

- nightly `pg_dump`
- push to object storage or another VM

## Smoke Checks After Deploy

Run these after the first production deploy:

1. `GET /api/health` returns `200`
2. SPA loads successfully over `https://munirevenue.com`
3. rate limiting headers appear on normal API calls

If OIDC overlay is enabled, add:

4. unauthenticated browser request redirects into OIDC login
5. authenticated user can load the SPA
6. `GET /api/auth/me` reflects the expected subject and role mapping
7. admin user can access `GET /api/admin/security`

## When To Revisit This Architecture

Consider a bigger change when any of these become true:

- multiple app instances are needed
- background jobs become long-running or memory-heavy
- rate limiting must be shared across nodes
- PostgreSQL needs managed backups/high availability

At that point, we can split the app and database or move selected pieces to managed infrastructure. For now, the Hetzner single-VM setup is the best balance of cost, control, and operational simplicity.
