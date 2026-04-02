# User Profile And Magic-Link Auth Plan

## Goal

Add first-party user accounts to MuniRevenue so a municipal user can:

- sign in with a passwordless magic link sent to email
- maintain a profile with city and county associations
- save default forecast preferences
- save anomaly follow-ups
- save potential missed-tax-payment follow-ups
- access protected intelligence surfaces only after login:
  - `/forecast`
  - `/anomalies`
  - `/missed-filings`

Public SEO and exploration pages remain public:

- `/`
- `/city/...`
- `/county/...`
- `/compare`
- `/rankings`
- `/trends`
- `/oklahoma-cities/...`
- `/oklahoma-counties/...`
- `/insights/...`

## Reality Check

Current state in the repo:

- backend auth only protects `/api/*` globally through `MUNIREV_API_AUTH_MODE`
- current auth modes are `off`, `token`, and `proxy`
- there is no user table, session table, or browser login flow
- the SPA router has no route-guard concept
- forecasts, anomalies, and missed-filings are currently just public frontend routes
- there is no email delivery integration
- `backend/app/api/cities.py` and `backend/app/api/analytics.py` currently attach `Depends(require_scopes("api:read"))` at the router level, which is too coarse for a mixed public-plus-protected surface

This means the correct implementation is not a small patch. It needs a real browser-session subsystem added alongside the existing service-token/proxy auth.

## Security Position

Magic links are acceptable for this product as a convenience sign-in method, but they are not phishing-resistant or high-assurance. The design should therefore:

- treat email as a moderate-assurance authenticator, not an admin-grade control
- use one-time, short-lived, hashed login tokens
- use server-side sessions in `HttpOnly` cookies
- keep the app ready for later step-up auth such as OIDC or passkeys
- require reauthentication for sensitive account changes, especially email-address change

The design follows:

- OWASP Authentication Cheat Sheet
- OWASP Session Management Cheat Sheet
- OWASP Forgot Password Cheat Sheet
- NIST SP 800-63B-4 guidance that email is not suitable for out-of-band authentication at higher assurance levels
- vendor patterns from Auth0, Clerk, and Supabase for passwordless email login

## Product Scope

### MVP Cut

Phase 1 in this implementation:

- magic-link auth
- browser session cookie
- protected routes and APIs for forecasts, anomalies, and missed-filings
- account profile with primary city and county
- forecast preferences
- anomaly follow-up saves
- missed-filing follow-up saves

Phase 2 later:

- richer session-management UI
- email-change reauthentication
- invite-only or admin-managed access
- MFA / OIDC / passkeys

### In Scope

- self-serve magic-link sign-in by email
- new account creation on first successful login request
- profile page
- city and county associations
- saved forecast defaults
- saved anomaly follow-ups
- saved missed-filing follow-ups
- route gating in the SPA
- API gating for the protected intelligence endpoints
- session management and logout
- test coverage for security, persistence, and route behavior

### Out Of Scope For This Phase

- organization admin panel
- invite workflow
- MFA
- SAML / OIDC identity provider integration
- billing / subscriptions
- per-jurisdiction authorization rules
- mobile deep links

## High-Level Architecture

Add a parallel browser-auth system instead of replacing the current API auth system.

### Existing auth remains

- `MUNIREV_API_AUTH_MODE=off|token|proxy` continues to work for machine access and reverse-proxy use
- public API endpoints stay public when `auth_mode=off`
- endpoint-level dependencies must replace the current router-wide read dependency so the product can support both public and logged-in surfaces intentionally

### New browser auth layer

- middleware resolves an optional browser session from a signed cookie
- protected frontend routes redirect unauthenticated users to `/login`
- protected API endpoints require either:
  - a valid browser session, or
  - existing elevated machine auth if present

This avoids breaking current public pages while still enforcing login where requested.

Important implementation detail:

- remove router-wide `Depends(require_scopes("api:read"))` from the whole cities and analytics routers
- apply explicit per-endpoint dependencies instead
- otherwise later `token` or `proxy` mode would accidentally force login across public exploration APIs

## User Experience

### Login request flow

1. User opens `/login`.
2. User submits email and optional `next` path.
3. Backend always returns the same generic success message.
4. Backend generates a one-time token, stores only its hash, and emails a link.
5. Link targets backend route `/auth/verify?token=...&next=...`.

### Login verification flow

1. User clicks the email link.
2. Backend validates:
   - token exists
   - token is unused
   - token is unexpired
   - token hash matches
3. Backend creates a new server-side session.
4. Backend invalidates the magic-link token and sets session cookie.
5. Backend redirects to sanitized internal `next`, defaulting to `/account`.

### Protected route flow

1. User navigates to `/forecast`, `/anomalies`, or `/missed-filings`.
2. SPA boots the session state before first protected render to avoid a flash of protected content.
3. If not authenticated, user is redirected to `/login?next=...`.
4. If authenticated, route renders normally.

### Account flow

The `/account` page will include:

- profile identity block
- connected city
- connected county
- forecast default settings
- saved anomaly follow-ups
- saved missed-filing follow-ups
- active-session summary with logout action

## Data Model

Use explicit relational tables for security-sensitive items and user-owned domain data.

### 1. `app_users`

Purpose: stable user identity.

Columns:

- `user_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `email TEXT NOT NULL`
- `email_normalized TEXT NOT NULL UNIQUE`
- `display_name TEXT`
- `job_title TEXT`
- `organization_name TEXT`
- `status TEXT NOT NULL DEFAULT 'active'`
- `marketing_opt_in BOOLEAN NOT NULL DEFAULT FALSE`
- `email_verified_at TIMESTAMPTZ`
- `last_login_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:

- `status IN ('active', 'disabled')`
- normalized email stored as lowercase trimmed value

Notes:

- do not store password fields
- future step-up auth can attach to this table cleanly

### 2. `user_magic_links`

Purpose: one-time login tokens.

Columns:

- `magic_link_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE`
- `token_hash TEXT NOT NULL UNIQUE`
- `next_path TEXT`
- `requested_ip INET`
- `requested_user_agent_hash TEXT`
- `expires_at TIMESTAMPTZ NOT NULL`
- `consumed_at TIMESTAMPTZ`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Rules:

- token lifetime: 15 minutes
- store only SHA-256 hash of the raw token
- single use only
- verification rejects expired or consumed tokens

### 3. `user_sessions`

Purpose: browser sessions.

Columns:

- `session_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE`
- `session_token_hash TEXT NOT NULL UNIQUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `expires_at TIMESTAMPTZ NOT NULL`
- `revoked_at TIMESTAMPTZ`
- `created_ip INET`
- `last_seen_ip INET`
- `user_agent_hash TEXT`

Rules:

- absolute session lifetime: 30 days
- idle extension window: rolling, capped by absolute lifetime
- store only token hash, never raw session token
- logout sets `revoked_at`
- use an opaque random session token; do not depend on client-side readable JWTs or local storage

### 4. `user_profile_preferences`

Purpose: per-user defaults and UI preferences.

Columns:

- `user_id UUID PRIMARY KEY REFERENCES app_users(user_id) ON DELETE CASCADE`
- `default_city_copo VARCHAR(4) REFERENCES jurisdictions(copo)`
- `default_county_name VARCHAR(50)`
- `default_tax_type tax_type`
- `forecast_model TEXT`
- `forecast_horizon_months INTEGER`
- `forecast_lookback_months INTEGER`
- `forecast_confidence_level NUMERIC(5,4)`
- `forecast_indicator_profile TEXT`
- `forecast_scope TEXT`
- `forecast_activity_code VARCHAR(6) REFERENCES naics_codes(activity_code)`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:

- `forecast_scope IN ('municipal', 'naics')`
- `forecast_model` constrained to supported frontend/backend models
- `default_county_name` must be validated against the supported Oklahoma county list in backend validation logic

### 5. `user_jurisdiction_interests`

Purpose: explicit list of places the user follows.

Columns:

- `interest_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE`
- `interest_type TEXT NOT NULL`
- `copo VARCHAR(4) REFERENCES jurisdictions(copo)`
- `county_name VARCHAR(50)`
- `label TEXT NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:

- `interest_type IN ('city', 'county')`
- city rows require `copo`
- county rows require `county_name`
- `county_name` must be validated against the supported Oklahoma county list
- unique composite to prevent duplicates per user

### 6. `user_saved_anomalies`

Purpose: follow-up queue for anomaly items.

Columns:

- `saved_anomaly_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE`
- `copo VARCHAR(4) NOT NULL REFERENCES jurisdictions(copo)`
- `tax_type tax_type NOT NULL`
- `anomaly_date DATE NOT NULL`
- `anomaly_type TEXT NOT NULL`
- `activity_code VARCHAR(6) REFERENCES naics_codes(activity_code)`
- `status TEXT NOT NULL DEFAULT 'saved'`
- `note TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:

- `status IN ('saved', 'investigating', 'resolved', 'dismissed')`
- unique composite on user plus anomaly natural key

### 7. `user_saved_missed_filings`

Purpose: follow-up queue for missed-filing candidates.

Columns:

- `saved_missed_filing_id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE`
- `copo VARCHAR(4) NOT NULL REFERENCES jurisdictions(copo)`
- `tax_type tax_type NOT NULL`
- `anomaly_date DATE NOT NULL`
- `activity_code VARCHAR(6) NOT NULL REFERENCES naics_codes(activity_code)`
- `baseline_method TEXT NOT NULL`
- `expected_value NUMERIC(14,2)`
- `actual_value NUMERIC(14,2)`
- `missing_amount NUMERIC(14,2)`
- `missing_pct NUMERIC(9,4)`
- `status TEXT NOT NULL DEFAULT 'saved'`
- `note TEXT`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`

Constraints:

- `status IN ('saved', 'investigating', 'resolved', 'dismissed')`
- unique composite on user plus missed-filing natural key

Reason for denormalized metrics:

- missed-filings feed is computed from a snapshot table, not a permanent business table
- storing the key plus metrics preserves what the user chose to follow even if future thresholds change

## Backend Design

## Session Resolution

Add a new auth module that:

- reads a session cookie on every request
- hashes the raw cookie token
- loads the active session and associated user
- attaches `request.state.user_session`

This should be optional. Missing cookie must not reject the request by itself.

## New Dependencies

Add route dependencies:

- `require_user_session()`
  - requires valid browser session
- `require_feature_access()`
  - accepts either browser session or existing service auth context
- `get_optional_user_session()`
  - returns session or `None`

Hard rule:

- service-auth bypass for protected endpoints is allowed only when `MUNIREV_API_AUTH_MODE != 'off'` and the request has a valid non-anonymous machine auth context with the required scopes
- `auth_mode=off` must never count as authenticated access for protected browser features

## Protected API Endpoints

Require login for:

- `GET /api/cities/{copo}/forecast`
- `GET /api/cities/{copo}/forecast/compare`
- `GET /api/cities/{copo}/forecast/drivers`
- `GET /api/stats/anomalies`
- `GET /api/stats/missed-filings`
- anomaly and missed-filing save/follow-up endpoints
- account/profile endpoints

Keep public:

- city search
- city detail
- ledger / NAICS explorer
- county summary
- overview / rankings / trends
- public insight and SEO routes

## New Auth / Account Endpoints

### Auth

- `POST /api/auth/magic-link/request`
- `GET /auth/verify`
- `GET /api/auth/session`
- `POST /api/auth/logout`

### Account

- `GET /api/account/profile`
- `PUT /api/account/profile`
- `GET /api/account/interests`
- `PUT /api/account/interests`
- `GET /api/account/forecast-preferences`
- `PUT /api/account/forecast-preferences`

### Follow-Ups

- `GET /api/account/saved-anomalies`
- `POST /api/account/saved-anomalies`
- `PATCH /api/account/saved-anomalies/{saved_anomaly_id}`
- `DELETE /api/account/saved-anomalies/{saved_anomaly_id}`
- `GET /api/account/saved-missed-filings`
- `POST /api/account/saved-missed-filings`
- `PATCH /api/account/saved-missed-filings/{saved_missed_filing_id}`
- `DELETE /api/account/saved-missed-filings/{saved_missed_filing_id}`

## Email Delivery

Use a simple server-side email sender abstraction:

- mode `log` for local/dev
- mode `smtp` for production

Suggested environment variables:

- `MUNIREV_AUTH_MAGIC_LINK_ENABLED=true`
- `MUNIREV_AUTH_MAGIC_LINK_BASE_URL=https://munirevenue.com`
- `MUNIREV_AUTH_MAGIC_LINK_TTL_MINUTES=15`
- `MUNIREV_AUTH_SESSION_DAYS=30`
- `MUNIREV_AUTH_COOKIE_NAME=munirev_session`
- `MUNIREV_AUTH_COOKIE_SECURE=true`
- `MUNIREV_AUTH_COOKIE_SAMESITE=lax`
- `MUNIREV_EMAIL_MODE=log|smtp`
- `MUNIREV_EMAIL_FROM=noreply@munirevenue.com`
- `SMTP_HOST=...`
- `SMTP_PORT=587`
- `SMTP_USERNAME=...`
- `SMTP_PASSWORD=...`
- `SMTP_USE_TLS=true`

Production requirement:

- an SMTP relay or transactional mail provider is required to send real magic links
- examples: Postmark, SES SMTP, Mailgun SMTP, SendGrid SMTP

## Frontend Design

### New Views

- `/login`
- `/account`
- `/auth/complete` optional frontend landing page after verification redirect

### New Client State

Add an auth/session store with:

- current user
- loading state
- login-required check
- logout action
- bootstrap-before-render behavior for protected routes

### Route Guarding

Guard these routes:

- `/forecast`
- `/forecast/:copo`
- `/anomalies`
- `/missed-filings`

Behavior:

- if no session, redirect to `/login?next=...`
- if authenticated, render normally

### Sidebar Changes

- show `Login` when signed out
- show `Account` and `Logout` when signed in
- protected nav clicks should still route through the guard

### Save Actions In Protected Views

Forecasts:

- load defaults from profile when entering the page
- optionally save current controls as defaults

Anomalies:

- add “Save for follow-up” on cards
- allow note and status on saved items

Missed Filings:

- add “Save for follow-up” on cards
- allow note and status on saved items

Account page:

- edit profile basics
- choose primary city/county
- manage interests
- manage saved anomalies
- manage saved missed filings
- active-session management can be deferred if time is tight; it is not required for the first secure release

## Security Controls

### Token Handling

- raw magic-link tokens are random 32-byte secrets
- store only SHA-256 hashes
- single use
- 15-minute expiry
- invalidate on consumption

### Session Handling

- server-side session store
- raw cookie token random and opaque
- `HttpOnly`
- `Secure` in production
- `SameSite=Lax`
- rotate on login
- revoke on logout

### CSRF Handling

Any session-cookie authenticated unsafe request must enforce browser-origin checks:

- allow `GET`, `HEAD`, `OPTIONS`, `TRACE` without CSRF check
- require trusted `Origin` or `Referer` for `POST`, `PUT`, `PATCH`, and `DELETE`
- use the same trusted-origin settings pattern already present in `security.py`

### Anti-Enumeration

- login-request endpoint always returns the same generic response
- identical response shape and similar timing whether the account exists or not

### Rate Limiting

Add specific request throttling for magic-link requests:

- by normalized email
- by source IP

### Redirect Safety

- `next` must be an internal path
- reject absolute URLs and protocol-relative values

### Reauthentication

Require fresh magic-link verification for future sensitive changes:

- email-address change
- any future admin privilege changes

This reauthentication requirement can be planned now even if the first release only stores profile fields.

### Auditability

Log:

- magic-link requested
- magic-link consumed
- session created
- session revoked

Exclude raw tokens and email secrets from logs.

## Migration Strategy

1. Add schema DDL and startup initialization.
2. Add backend auth/session services and endpoints.
3. Add frontend login/session store and guarded routes.
4. Add account/profile/follow-up UI.
5. Add save actions to anomalies and missed-filings.
6. Add forecast default persistence.
7. Add tests and deploy with SMTP disabled or `log` mode first.
8. After verification, switch production to real SMTP credentials.

## Testing Strategy

### Backend Unit Tests

- email normalization and safe `next` validation
- magic-link creation hashes the token and sets expiry correctly
- magic-link verification rejects:
  - expired token
  - reused token
  - malformed token
- session resolution rejects revoked and expired sessions
- feature-access dependency allows:
  - valid browser session
  - valid service auth
- feature-access dependency blocks anonymous users on protected endpoints

### Backend API Tests

- `POST /api/auth/magic-link/request` returns generic success
- `GET /auth/verify` sets cookie and redirects
- `GET /api/auth/session` returns current user when logged in
- protected endpoints return `401` or `403` when anonymous
- protected endpoints succeed when authenticated
- saved anomalies CRUD
- saved missed-filings CRUD
- profile and forecast preference update flows

### Frontend Tests

Current frontend stack has no test runner. Add one during implementation.

Recommended:

- `vitest`
- `jsdom`

Frontend coverage should include:

- auth store bootstrap
- protected-route redirect behavior
- login form submission state
- logout state reset

### End-To-End Smoke Tests

- request magic link in `log` mode and capture emitted link
- complete login
- open `/forecast`
- save forecast preferences
- save an anomaly
- save a missed filing
- logout and confirm protected routes redirect back to login

## Agent Split

### Review Agent

Task: critique the plan against the current repo and call out missing acceptance criteria, hidden coupling, and security gaps.

### Backend Worker

Ownership:

- `backend/app/security.py`
- new auth/account modules
- `backend/app/main.py`
- `backend/app/db/schema.sql`
- backend tests
- env examples and docs

### Frontend Worker

Ownership:

- `frontend/src/router.ts`
- `frontend/src/paths.ts`
- `frontend/src/api.ts`
- new auth/account components and views
- `frontend/src/components/sidebar.ts`
- protected intelligence views
- frontend tests and package updates

## Acceptance Criteria

- anonymous users cannot access Forecasts, Anomalies, or Missed Filings pages
- anonymous users cannot call the corresponding protected API endpoints
- direct navigation to protected SPA paths still serves the SPA shell and redirects unauthenticated users to `/login?next=...` without breaking public routing
- magic-link sign-in works end to end with generic request responses
- session cookie is `HttpOnly`
- profile city and county can be saved and reloaded
- forecast defaults can be saved and reused
- anomaly follow-ups can be saved and managed
- missed-filing follow-ups can be saved and managed
- public SEO pages remain publicly reachable
- build passes
- backend tests pass
- frontend tests pass

## Open Operational Requirement

Production email sending will require one of the following before final rollout:

- SMTP server credentials, or
- SMTP-compatible transactional email provider credentials

Local development can proceed immediately with `MUNIREV_EMAIL_MODE=log`.

Implementation note:

- `/auth/verify` must remain a backend route that consumes the token server-side and redirects to a clean frontend path so the raw token never enters SPA state or browser storage

## Source Notes

Primary references used for the design:

- OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- NIST SP 800-63B-4: https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63b-4.pdf
- Auth0 passwordless docs: https://auth0.com/docs/authenticate/passwordless
- Clerk magic links docs: https://clerk.com/docs/authentication/social-connections/magic-links
- Supabase passwordless docs: https://supabase.com/docs/guides/auth/auth-email-passwordless
