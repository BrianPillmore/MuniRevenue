# Reality Check: User Profile And Magic-Link Auth

## Claimed Status

The plan assumed auth/profile needed to be built from scratch.

## Actual Status

### Working

- The repo already had a partial browser-auth implementation in [user_auth.py](/C:/Users/brian/GitHub/CityTax/backend/app/user_auth.py) and [account.py](/C:/Users/brian/GitHub/CityTax/backend/app/api/account.py).
- Existing backend tests already covered core magic-link, profile, and follow-up flows in [test_user_auth.py](/C:/Users/brian/GitHub/CityTax/backend/tests/test_user_auth.py).
- Existing API security tests were already validating the machine-auth modes in [test_api_security.py](/C:/Users/brian/GitHub/CityTax/backend/tests/test_api_security.py).

### Partial

- The preexisting auth branch had schema, endpoints, and tests, but it was not fully wired into protected feature access.
- Protected frontend routes had no session gate or account UI.
- Forecast preferences and saved follow-ups existed at the API layer, but not in the user-facing frontend.

### Missing Or Broken

- The auth/account path was split across multiple files without a clean review of what already existed.
- Saved-anomaly matching had a null-key edge and parameter mismatch risk.
- Browser-session resolution was duplicated in app middleware and not aligned with feature-level protection.
- Forecast endpoint verification in auth tests could trigger unrelated persistence contention and was not a good auth assertion.

## Completion

Before implementation cleanup: about 45%.

After the current pass in this turn:

- backend auth/profile/follow-up slice: materially complete and passing targeted tests
- frontend login/account/protected-route slice: implemented and building

## Issues Found

1. The repo already had unfinished auth files in [account.py](/C:/Users/brian/GitHub/CityTax/backend/app/api/account.py) and [user_auth.py](/C:/Users/brian/GitHub/CityTax/backend/app/user_auth.py), so a parallel fresh implementation would have forked the system instead of finishing it.
2. Protected-route enforcement needed to happen at the feature level, not by globally changing all API auth behavior, because the app still has a public SEO and exploration surface.
3. The account follow-up flow needed realistic tests that isolate auth behavior from unrelated forecast persistence work.

## Corrections Applied

- Reused and completed the existing auth/account backend path instead of introducing a second competing stack.
- Added protected access only to forecasts, anomalies, and missed-filings APIs.
- Integrated browser sessions into the existing security middleware path.
- Kept public pages and public API reads reachable in the current `MUNIREV_API_AUTH_MODE=off` posture.
- Added frontend login and account views, route guards, sidebar account state, and save-for-follow-up actions.

## Remaining Follow-Up

- Add dedicated frontend unit tests once a frontend test runner is introduced.
- Decide whether browser sessions should also satisfy read access when `MUNIREV_API_AUTH_MODE=token|proxy` in a fully mixed public/private deployment. The current production posture is `off`, which matches the implemented path.
- Decide whether saved anomaly and missed-filing records should persist more snapshot metadata for richer account reporting.
