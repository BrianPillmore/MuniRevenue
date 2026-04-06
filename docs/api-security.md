# API Security

## Goals

The current security model has to support both of these at the same time:

1. Public exploration for non-sensitive municipal analytics pages and APIs
2. Authenticated access for user-specific and investigation-oriented features

That means the app is no longer purely "all browser auth at the proxy" or "all API auth everywhere." It is now a mixed-mode system.

## Security Layers

### 1. Edge / proxy

At the edge, Caddy terminates TLS and routes traffic to FastAPI.

Optional hardening:

- `oauth2-proxy` in front of FastAPI
- OIDC / SSO for browser login

This is still a supported production option, but it is no longer the only browser-auth path.

### 2. Application middleware

The middleware in [security.py](/C:/Users/brian/GitHub/MuniRevenue/backend/app/security.py) applies:

- request IDs
- security headers
- auth-mode evaluation
- token bucket rate limiting
- trusted-origin enforcement for unsafe browser writes
- browser session resolution
- mixed-mode handling for:
  - public API paths
  - optional browser-auth paths
  - protected API paths

Headers added by the API:

- `X-Request-ID`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- `Cache-Control: no-store` on `/api/*`

### 3. Route authorization

Authorization is still scope-based for machine and admin flows.

Current scopes:

- `api:read`
- `analysis:run`
- `reports:generate`
- `data:import`
- `api:admin`

In addition, selected browser-facing product features now use login-based gating through `require_feature_access`.

## Browser Authentication

The repo now contains a first-party browser auth path in [user_auth.py](/C:/Users/brian/GitHub/MuniRevenue/backend/app/user_auth.py) and [account.py](/C:/Users/brian/GitHub/MuniRevenue/backend/app/api/account.py).

Current browser-auth flow:

1. User requests a magic link at `POST /api/auth/magic-link/request`
2. Backend generates a one-time token and stores only its hash
3. User receives a link to `GET /auth/verify?token=...`
4. Backend consumes the token server-side and creates a browser session
5. Backend sets an `HttpOnly` session cookie
6. SPA reads session state from `GET /api/auth/session`

Important properties:

- raw magic-link tokens are not stored in browser state
- raw magic-link tokens do not enter SPA local storage
- session cookies are `HttpOnly`
- cookie settings are env-driven
- session and magic-link tokens are hashed before persistence

## Browser-Auth Data Model

Browser auth currently persists:

- `app_users`
- `user_magic_links`
- `user_sessions`
- `user_profile_preferences`
- `user_jurisdiction_interests`
- `user_saved_anomalies`
- `user_saved_missed_filings`

This supports:

- login
- user profile information
- jurisdiction interests
- saved forecast defaults
- saved anomaly follow-ups
- saved missed-filing follow-ups

## Auth Modes

### `off`

Use for local development or fully public deployments.

In this mode:

- machine auth is disabled
- browser login can still be enabled separately with `MUNIREV_AUTH_MAGIC_LINK_ENABLED=true`

### `token`

Use for automation, service integrations, or operational access.

Supported token paths:

- static `X-API-Key`
- static `Authorization: Bearer <token>`
- HS256 JWT bearer tokens

Recommended usage:

- prefer JWTs for service integrations
- keep static secrets for narrow internal or break-glass use

### `proxy`

Use when the browser should authenticate through an upstream proxy / SSO layer.

The app can read:

- subject headers such as `X-Auth-Request-Email`
- role/group headers such as `X-Auth-Request-Groups`
- optional scope headers

When proxy auth is active, unsafe methods require an `Origin` or `Referer` that matches the trusted origin list.

## Mixed Public / Protected Access

This is the current intended behavior.

### Public API surface

Public exploration endpoints remain available without machine credentials, even when auth mode is `token` or `proxy`.

Examples:

- city list / detail
- ledger and NAICS exploration
- statewide overview, trend, rankings, sectors
- county summaries

### Protected product features

These require a browser session or authenticated machine context:

- forecasts
- anomalies
- missed-filings
- account/profile endpoints

This is enforced through `require_feature_access` and the middleware’s public-path exceptions.

## Roles

Built-in role expansion:

- `viewer` -> `api:read`
- `analyst` -> `api:read`, `analysis:run`, `reports:generate`
- `operator` -> analyst scopes plus `data:import`
- `service` -> analyst/import service bundle
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

## Abuse Controls

### API rate limiting

Rate limiting uses an in-memory token bucket:

- configurable request count
- configurable window
- keyed by authenticated subject when available, otherwise client IP

This is acceptable for the current single-VM deployment shape.

### Magic-link request throttling

The browser-auth flow now also has dedicated magic-link throttles:

- per email
- per IP
- configurable rolling window

That is separate from the generic API rate limiter.

### Browser write protection

Unsafe browser writes require a trusted `Origin` or `Referer`.

This applies to:

- account/profile mutations
- interest updates
- forecast preference updates
- saved follow-up mutations
- magic-link request submission

## Recommended Production Postures

### Option A — First-party magic-link browser auth

Use:

- `MUNIREV_API_AUTH_MODE=off` or `token`
- `MUNIREV_AUTH_MAGIC_LINK_ENABLED=true`
- real SMTP credentials
- strong `MUNIREV_AUTH_SESSION_SECRET`

### Option B — Proxy / OIDC browser auth

Use:

- `MUNIREV_API_AUTH_MODE=proxy`
- `oauth2-proxy`
- trusted proxy headers

### Option C — Hybrid

Use first-party browser auth for product users while still supporting `token` or `proxy` for operations and integrations.

This is the direction the current code most directly supports.

## Operational Endpoints

- `GET /api/auth/me`
  - active auth context for the caller
- `GET /api/admin/security`
  - admin-only security posture summary
- `GET /api/auth/session`
  - browser-session status

## Production Prerequisites For First-Party Magic Links

Required for real email delivery:

- `MUNIREV_EMAIL_MODE=smtp`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_USE_TLS=true`
- `MUNIREV_EMAIL_FROM`
- `MUNIREV_AUTH_SESSION_SECRET`

Local/test mode can use:

- `MUNIREV_EMAIL_MODE=log`
