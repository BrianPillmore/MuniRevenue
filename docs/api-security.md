# API Security

## Goals

The API security model is designed around two principles:

1. Browser identity should be handled by an upstream auth layer in production.
2. The application should still enforce authorization itself instead of trusting “authenticated means allowed.”

## Layers

### 1. Edge / proxy

Recommended production pattern:

- Caddy terminates TLS
- oauth2-proxy performs OIDC login
- oauth2-proxy forwards trusted identity headers to FastAPI

That keeps long-lived credentials out of the browser app.

### 2. Application middleware

The middleware in [security.py](c:/Users/brian/GitHub/CityTax/backend/app/security.py) applies:

- request IDs
- security headers
- authentication
- token bucket rate limiting
- proxy-mode CSRF origin checks for unsafe methods

Headers added by the API:

- `X-Request-ID`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Cache-Control: no-store` on `/api/*`

### 3. Route authorization

Authorization is scope-based.

Current scopes:

- `api:read`
- `analysis:run`
- `reports:generate`
- `data:import`
- `api:admin`

## Auth Modes

### `off`

Use only for local development.

### `token`

Use for automation, service integrations, or emergency operational access.

Supported token paths:

- static `X-API-Key`
- static `Authorization: Bearer <token>`
- HS256 JWT bearer tokens

Recommended production usage:

- prefer JWTs for service integrations
- keep static secrets for break-glass or short-lived internal use

### `proxy`

Use for browser-facing deployments.

The app trusts identity forwarded from an upstream auth layer. By default it can read:

- subject headers such as `X-Auth-Request-Email`
- role/group headers such as `X-Auth-Request-Groups`
- optional scope headers

When proxy auth is active, unsafe methods also require an `Origin` or `Referer` that matches the trusted origin list. This protects write endpoints against cross-site request forgery when browser sessions are backed by proxy cookies.

## Roles

Built-in role expansion:

- `viewer` -> `api:read`
- `analyst` -> `api:read`, `analysis:run`, `reports:generate`
- `operator` -> analyst scopes plus `data:import`
- `service` -> analyst/import style service scope bundle
- `admin` -> `api:admin` and implied scopes

If a proxy provides group membership, those group values can map directly to the role names above.

## JWT Expectations

The JWT validator currently supports:

- algorithm: `HS256`
- issuer validation
- audience validation
- `exp`, `nbf`, and `iat` checks

Recognized claims:

- subject: `sub`, `preferred_username`, `email`, `client_id`
- roles: `roles`, `role`, `groups`
- scopes: `scope`, `scp`

## Rate Limiting

Rate limiting uses an in-memory token bucket:

- configurable request count
- configurable window
- keyed by authenticated subject when available, otherwise client IP

This is a good fit for the recommended single-VM Hetzner deployment. If the app later scales across multiple app instances, move rate limiting to a shared backend such as Redis.

## Recommended Production Posture

For Hetzner:

- `MUNIREV_API_AUTH_MODE=proxy`
- enable rate limiting
- enable HTTPS redirect
- set a strict host allowlist
- trust `X-Forwarded-For` only behind Caddy
- set `MUNIREV_CSRF_TRUSTED_ORIGINS` to the production app origin
- keep `/api/health` as the only unauthenticated API route
- disable interactive OpenAPI docs unless there is a concrete operational reason to expose them

For machine clients:

- keep browser traffic on proxy auth
- use separate JWT or service-token credentials for automation
- grant the narrowest role/scope needed

## Operational Endpoints

- `GET /api/auth/me`
  - returns the active auth context for the caller
- `GET /api/admin/security`
  - admin-only summary of security posture and header expectations

These are intentionally limited to non-secret operational information.
