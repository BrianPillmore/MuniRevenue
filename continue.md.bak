# MuniRev — Continue From Here

**Last updated:** 2026-04-02  
**Repo target:** https://github.com/BrianPillmore/MuniRevenue  
**Production domain:** https://munirevenue.com  
**Local path:** `C:\Users\brian\GitHub\CityTax`

## Current Reality

The repo is in an in-progress but verified state for the new **user profile / magic-link login** workstream.

This work is **implemented in the local worktree but not yet committed, pushed, or deployed**.

The current implementation adds:

- first-party browser auth via one-time magic links
- HttpOnly session cookies
- user profile storage
- jurisdiction interests
- saved forecast defaults
- saved anomaly follow-ups
- saved missed-filing follow-ups
- protected routing for:
  - `/forecast`
  - `/forecast/:copo`
  - `/anomalies`
  - `/missed-filings`
  - `/account`

It also preserves the intended mixed-mode behavior:

- public exploration APIs remain public
- protected product surfaces still require login
- this now works even when `MUNIREV_API_AUTH_MODE=token` or `proxy`

## Verified Status

### Backend

Implemented and tested:

- magic-link request endpoint
- magic-link verify endpoint
- browser session resolution
- logout
- account profile CRUD
- jurisdiction interests CRUD
- forecast preference CRUD
- saved anomaly follow-up CRUD
- saved missed-filing follow-up CRUD
- request-origin enforcement for unsafe browser writes
- magic-link single-use semantics
- magic-link request abuse throttling
- mixed machine-auth + browser-auth compatibility

Key backend files:

- `backend/app/main.py`
- `backend/app/security.py`
- `backend/app/user_auth.py`
- `backend/app/db/psycopg.py`
- `backend/app/api/account.py`
- `backend/app/api/cities.py`
- `backend/app/api/analytics.py`

### Frontend

Implemented and tested:

- `/login` view
- `/account` view
- sidebar signed-in / signed-out state
- protected route redirects to `/login?next=...`
- direct navigation to protected routes is intercepted and redirected
- forecast defaults load from account preferences
- anomaly follow-ups can be saved from feed and managed in account
- missed-filing follow-ups can be saved from feed and managed in account

Key frontend files:

- `frontend/src/auth.ts`
- `frontend/src/api.ts`
- `frontend/src/main.ts`
- `frontend/src/paths.ts`
- `frontend/src/router.ts`
- `frontend/src/views/login.ts`
- `frontend/src/views/account.ts`
- `frontend/src/views/forecast.ts`
- `frontend/src/views/anomalies.ts`
- `frontend/src/views/missed-filings.ts`

### Plans / Review Docs

- `plans/user-profile-auth-magic-link.md`
- `plans/user-profile-auth-magic-link-review.md`
- `plans/seo-enhancement.md`

## Latest Test Snapshot

Most recent green checks in this workstream:

- `pytest backend/tests/test_user_auth.py backend/tests/test_api_security.py -q`
  - `25 passed`
- `npm test` in `frontend`
  - `14 passed`
- `npm run build` in `frontend`
  - passed

Important test coverage now includes:

- direct protected-route redirect behavior
- token/proxy mixed-mode access behavior
- invalid forecast default rejection
- invalid follow-up target rejection
- trusted-origin enforcement

## Security / Auth Design Now In Tree

### Browser auth

- magic link token is generated server-side
- only token hashes are stored
- `/auth/verify` consumes the raw token server-side
- raw token does **not** enter SPA state or browser storage
- session cookie is `HttpOnly`
- session cookie settings are env-driven

### Mixed-mode behavior

The app now supports:

- public exploration routes without machine credentials
- gated login-only product routes for forecasts/anomalies/missed-filings
- optional machine auth for integrations and ops

### Abuse controls

The current implementation includes:

- token bucket API rate limiting
- trusted-origin enforcement for unsafe browser writes
- dedicated magic-link request throttles by email and IP

## Production Prerequisites For Magic-Link Login

If production should use **first-party magic-link login**, you still need to provide:

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

Recommended operationally:

- use a transactional email provider with SMTP compatibility
- examples:
  - Postmark
  - Amazon SES SMTP
  - Mailgun SMTP
  - SendGrid SMTP

Current local/test mode works with:

- `MUNIREV_EMAIL_MODE=log`

That is fine for local development and tests, but it will not send real sign-in emails.

## Production Auth Decision Still Needed

There are now two viable paths:

### Option A — First-party magic-link login

Use the new browser-auth system directly in the app.

Pros:

- matches current product design
- supports saved user preferences and follow-up workflow cleanly
- simple user experience

Needs:

- SMTP setup
- secure session secret
- production env rollout
- deployment smoke checks

### Option B — Proxy / OIDC login

Keep or restore the Hetzner `oauth2-proxy` / OIDC model for browser auth.

Pros:

- centralized identity
- stronger enterprise posture

Tradeoff:

- the new first-party account/profile UX would need to coexist with or be adapted to proxy identity

### Option C — Hybrid

Allow first-party magic-link browser sessions for product users while keeping `token` or `proxy` support for integrations/admin access.

This is the direction the current code most closely supports.

## Important Repo-State Note

The worktree is currently dirty with this auth/profile feature.

Do not assume these changes are already committed or deployed.

Before any ship step:

1. review `git status`
2. separate this feature from unrelated changes if needed
3. run tests again
4. commit intentionally
5. push
6. deploy

## Recommended Next Steps

### Immediate

1. Decide whether production should use:
   - first-party magic links
   - proxy/OIDC
   - hybrid
2. If using magic links, provision SMTP credentials and a strong `MUNIREV_AUTH_SESSION_SECRET`.
3. Add the production auth env values to `deploy/hetzner/.env.hetzner`.
4. Commit, push, and deploy the auth/profile work once repo-state is reviewed.

### After deploy

1. Smoke test:
   - `/login`
   - `/account`
   - `/forecast`
   - `/anomalies`
   - `/missed-filings`
   - direct navigation to protected routes
   - magic-link request and verify flow
2. Confirm public exploration still works without login:
   - city search / city detail
   - rankings
   - statewide trend
   - county summary
3. Verify cookies/security behavior on the live domain.

### Follow-up engineering

1. Add broader frontend tests for the account page and follow-up management UI.
2. Add deploy smoke checks for the auth flow.
3. Decide whether to keep the longer-term Hetzner/OIDC path in docs as primary, or update docs to make first-party browser auth the main recommendation.
4. If desired, add email templates/branding for magic-link messages instead of plain text.
5. If desired, add explicit user-disable / admin-management tools for browser accounts.

## Thorough Continuation Prompt

Use this prompt at the start of the next session:

> Continue from the current local worktree in `C:\Users\brian\GitHub\CityTax`.  
> Focus on the user-profile / magic-link auth feature that is already implemented locally but not yet committed/deployed.  
> Read these first:
> - `continue.md`
> - `plans/user-profile-auth-magic-link.md`
> - `plans/user-profile-auth-magic-link-review.md`
> - `backend/app/user_auth.py`
> - `backend/app/api/account.py`
> - `backend/app/security.py`
> - `frontend/src/router.ts`
> - `frontend/src/views/login.ts`
> - `frontend/src/views/account.ts`
>
> Current verified state:
> - magic-link auth, profile/preferences, and saved follow-ups are implemented
> - forecasts/anomalies/missed-filings/account require login
> - public exploration remains public even in mixed auth modes
> - backend auth/security tests are green
> - frontend auth/router tests are green
> - frontend production build is green
>
> Before making changes:
> 1. inspect `git status`
> 2. avoid overwriting unrelated local changes
> 3. rerun relevant tests after edits
>
> The main unresolved product/ops question is production auth posture:
> - first-party magic-link
> - proxy/OIDC
> - or hybrid
>
> If production is going to use first-party magic-link auth, require SMTP configuration and a strong session secret before deploy.
