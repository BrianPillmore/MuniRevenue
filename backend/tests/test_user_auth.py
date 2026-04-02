from __future__ import annotations

import os
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db.psycopg import get_cursor
from app.main import create_app
from app.user_auth import hash_secret


YUKON_COPO = "0955"


def cleanup_user(email: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM app_users WHERE email_normalized = %s",
            [email.strip().lower()],
        )


class TestUserAuth(unittest.TestCase):
    browser_headers = {"Origin": "http://testserver"}

    def create_client(self, env_overrides: dict[str, str] | None = None) -> TestClient:
        env = {
            "MUNIREV_API_AUTH_MODE": "off",
            "MUNIREV_AUTH_MAGIC_LINK_ENABLED": "true",
            "MUNIREV_EMAIL_MODE": "log",
            "MUNIREV_AUTH_COOKIE_SECURE": "false",
            "MUNIREV_AUTH_MAGIC_LINK_BASE_URL": "http://testserver",
            "MUNIREV_CSRF_TRUSTED_ORIGINS": "http://testserver",
        }
        if env_overrides:
            env.update(env_overrides)
        patcher = patch.dict(
            os.environ,
            env,
            clear=False,
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        client = TestClient(create_app())
        client.headers.update({"Origin": "http://testserver"})
        return client

    def _issue_magic_link(self, client: TestClient, email: str, next_path: str = "/forecast/0955") -> str:
        cleanup_user(email)
        self.addCleanup(cleanup_user, email)
        response = client.post(
            "/api/auth/magic-link/request",
            json={"email": email, "next_path": next_path},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sign-in link", response.json()["message"])
        link = client.app.state.magic_link_debug_links[email.lower()]
        parsed = urlparse(link)
        token = parse_qs(parsed.query)["token"][0]
        return token

    def _login(self, client: TestClient, email: str, next_path: str = "/forecast/0955") -> None:
        token = self._issue_magic_link(client, email, next_path)
        verify_response = client.get(f"/auth/verify?token={token}", follow_redirects=False)
        self.assertEqual(verify_response.status_code, 303)
        self.assertEqual(verify_response.headers["location"], next_path)
        self.assertIn("munirev_session", client.cookies)

    def test_protected_routes_require_login_when_enabled(self) -> None:
        client = self.create_client()
        forecast_response = client.get(f"/api/cities/{YUKON_COPO}/forecast")
        anomalies_response = client.get("/api/stats/anomalies")
        public_response = client.get("/api/cities?limit=1")

        self.assertEqual(forecast_response.status_code, 401)
        self.assertEqual(anomalies_response.status_code, 401)
        self.assertEqual(public_response.status_code, 200)

    def test_magic_link_flow_creates_session(self) -> None:
        client = self.create_client()
        self._login(client, "auth-flow@example.com")

        session_response = client.get("/api/auth/session")
        self.assertEqual(session_response.status_code, 200)
        self.assertTrue(session_response.json()["authenticated"])
        self.assertEqual(session_response.json()["user"]["email"], "auth-flow@example.com")

        anomalies_response = client.get("/api/stats/anomalies")
        self.assertEqual(anomalies_response.status_code, 200)

    def test_magic_link_request_ignores_invalid_email_format(self) -> None:
        client = self.create_client()
        email = "invalid-email-format"
        cleanup_user(email)
        self.addCleanup(cleanup_user, email)

        response = client.post(
            "/api/auth/magic-link/request",
            json={"email": email, "next_path": "/account"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("sign-in link", response.json()["message"])
        self.assertNotIn(email.lower(), client.app.state.magic_link_debug_links)

    def test_magic_link_verify_rejects_expired_token(self) -> None:
        client = self.create_client()
        token = self._issue_magic_link(client, "expired@example.com", "/account")
        token_hash = hash_secret(token, client.app.state.browser_auth_settings.session_secret)

        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE user_magic_links
                SET expires_at = NOW() - INTERVAL '1 day'
                WHERE token_hash = %s
                """,
                [token_hash],
            )

        response = client.get(f"/auth/verify?token={token}", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?error=invalid-link")

    def test_magic_link_verify_returns_disabled_redirect_when_feature_is_off(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_AUTH_MAGIC_LINK_ENABLED": "false",
            }
        )

        response = client.get("/auth/verify?token=disabled-token", follow_redirects=False)

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login?disabled=1")

    def test_magic_link_requests_are_rate_limited_by_email(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_AUTH_MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS": "3600",
                "MUNIREV_AUTH_MAGIC_LINK_RATE_LIMIT_PER_EMAIL": "1",
                "MUNIREV_AUTH_MAGIC_LINK_RATE_LIMIT_PER_IP": "10",
            }
        )
        email = "rate-limit@example.com"
        cleanup_user(email)
        self.addCleanup(cleanup_user, email)

        first = client.post(
            "/api/auth/magic-link/request",
            json={"email": email, "next_path": "/forecast/0955"},
        )
        second = client.post(
            "/api/auth/magic-link/request",
            json={"email": email, "next_path": "/anomalies"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

        with get_cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS request_count
                FROM user_magic_links ml
                JOIN app_users u ON u.user_id = ml.user_id
                WHERE u.email_normalized = %s
                """,
                [email],
            )
            count_row = cur.fetchone()
        self.assertEqual(int(count_row["request_count"]), 1)

    def test_magic_link_tokens_are_single_use(self) -> None:
        client = self.create_client()
        token = self._issue_magic_link(client, "single-use@example.com", "/account")

        first_response = client.get(f"/auth/verify?token={token}", follow_redirects=False)
        second_response = client.get(f"/auth/verify?token={token}", follow_redirects=False)

        self.assertEqual(first_response.status_code, 303)
        self.assertEqual(first_response.headers["location"], "/account")
        self.assertEqual(second_response.status_code, 303)
        self.assertEqual(second_response.headers["location"], "/login?error=invalid-link")

    def test_browser_auth_flow_works_when_machine_auth_mode_is_token(self) -> None:
        client = self.create_client(
            {
                "MUNIREV_API_AUTH_MODE": "token",
            }
        )

        session_before = client.get("/api/auth/session")
        self.assertEqual(session_before.status_code, 200)
        self.assertFalse(session_before.json()["authenticated"])

        self._login(client, "token-mode-browser@example.com")

        session_after = client.get("/api/auth/session")
        self.assertEqual(session_after.status_code, 200)
        self.assertTrue(session_after.json()["authenticated"])

        profile_response = client.get("/api/account/profile")
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["email"], "token-mode-browser@example.com")

        anomalies_response = client.get("/api/stats/anomalies")
        self.assertEqual(anomalies_response.status_code, 200)

    def test_profile_preferences_and_followups_round_trip(self) -> None:
        client = self.create_client()
        self._login(client, "profile-test@example.com", "/account")

        update_profile = client.put(
            "/api/account/profile",
            json={
                "display_name": "Taylor Clerk",
                "job_title": "Finance Director",
                "organization_name": "Yukon",
                "marketing_opt_in": True,
            },
            headers=self.browser_headers,
        )
        self.assertEqual(update_profile.status_code, 200)
        self.assertEqual(update_profile.json()["display_name"], "Taylor Clerk")

        update_preferences = client.put(
            "/api/account/forecast-preferences",
            json={
                "default_city_copo": YUKON_COPO,
                "default_county_name": "Canadian",
                "default_tax_type": "sales",
                "forecast_model": "auto",
                "forecast_horizon_months": 12,
                "forecast_lookback_months": 36,
                "forecast_confidence_level": 0.95,
                "forecast_indicator_profile": "balanced",
                "forecast_scope": "municipal",
            },
            headers=self.browser_headers,
        )
        self.assertEqual(update_preferences.status_code, 200)
        self.assertEqual(update_preferences.json()["default_city_copo"], YUKON_COPO)

        replace_interests = client.put(
            "/api/account/interests",
            json={
                "items": [
                    {"interest_type": "city", "copo": YUKON_COPO},
                    {"interest_type": "county", "county_name": "Canadian"},
                ]
            },
            headers=self.browser_headers,
        )
        self.assertEqual(replace_interests.status_code, 200)
        self.assertEqual(len(replace_interests.json()["items"]), 2)

        save_anomaly = client.post(
            "/api/account/saved-anomalies",
            json={
                "copo": YUKON_COPO,
                "tax_type": "sales",
                "anomaly_date": "2025-12-01",
                "anomaly_type": "yoy_drop",
                "status": "saved",
                "note": "Investigate later",
            },
            headers=self.browser_headers,
        )
        self.assertEqual(save_anomaly.status_code, 200)
        self.assertEqual(len(save_anomaly.json()["items"]), 1)

        save_missed_filing = client.post(
            "/api/account/saved-missed-filings",
            json={
                "copo": YUKON_COPO,
                "tax_type": "sales",
                "anomaly_date": "2025-12-01",
                "activity_code": "455110",
                "baseline_method": "hybrid",
                "expected_value": 10000,
                "actual_value": 1000,
                "missing_amount": 9000,
                "missing_pct": 90,
                "status": "saved",
                "note": "Follow up with retailer",
            },
            headers=self.browser_headers,
        )
        self.assertEqual(save_missed_filing.status_code, 200)
        self.assertEqual(len(save_missed_filing.json()["items"]), 1)

        saved_missed_filing_id = save_missed_filing.json()["items"][0]["saved_missed_filing_id"]
        update_missed_filing = client.patch(
            f"/api/account/saved-missed-filings/{saved_missed_filing_id}",
            json={"status": "investigating", "note": "Reviewed with clerk"},
            headers=self.browser_headers,
        )
        self.assertEqual(update_missed_filing.status_code, 200)
        self.assertEqual(update_missed_filing.json()["items"][0]["status"], "investigating")
        self.assertEqual(update_missed_filing.json()["items"][0]["note"], "Reviewed with clerk")

        delete_missed_filing = client.delete(
            f"/api/account/saved-missed-filings/{saved_missed_filing_id}",
            headers=self.browser_headers,
        )
        self.assertEqual(delete_missed_filing.status_code, 200)
        self.assertEqual(delete_missed_filing.json()["items"], [])

    def test_account_mutations_require_trusted_origin(self) -> None:
        client = self.create_client()
        self._login(client, "origin-guard@example.com", "/account")

        response = client.put(
            "/api/account/profile",
            json={"display_name": "Blocked Update"},
            headers={"Origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_magic_link_request_requires_trusted_origin(self) -> None:
        client = self.create_client()

        response = client.post(
            "/api/auth/magic-link/request",
            json={"email": "blocked@example.com", "next_path": "/account"},
            headers={"Origin": "https://evil.example"},
        )

        self.assertEqual(response.status_code, 403)

    def test_saved_missed_filing_rejects_invalid_baseline_method(self) -> None:
        client = self.create_client()
        self._login(client, "invalid-baseline@example.com", "/account")

        response = client.post(
            "/api/account/saved-missed-filings",
            json={
                "copo": YUKON_COPO,
                "tax_type": "sales",
                "anomaly_date": "2025-12-01",
                "activity_code": "455110",
                "baseline_method": "bad-method",
            },
            headers=self.browser_headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_saved_followups_reject_invalid_targets(self) -> None:
        client = self.create_client()
        self._login(client, "invalid-targets@example.com", "/account")

        invalid_interest = client.put(
            "/api/account/interests",
            json={"items": [{"interest_type": "county", "county_name": "NotARealCounty"}]},
            headers=self.browser_headers,
        )
        invalid_missed_filing = client.post(
            "/api/account/saved-missed-filings",
            json={
                "copo": YUKON_COPO,
                "tax_type": "lodging",
                "anomaly_date": "2025-12-01",
                "activity_code": "455110",
                "baseline_method": "hybrid",
            },
            headers=self.browser_headers,
        )

        self.assertEqual(invalid_interest.status_code, 400)
        self.assertEqual(invalid_missed_filing.status_code, 400)

    def test_saved_anomaly_supports_patch_and_delete(self) -> None:
        client = self.create_client()
        self._login(client, "anomaly-followup@example.com", "/account")

        create_response = client.post(
            "/api/account/saved-anomalies",
            json={
                "copo": YUKON_COPO,
                "tax_type": "sales",
                "anomaly_date": "2025-12-01",
                "anomaly_type": "yoy_drop",
                "status": "saved",
            },
            headers=self.browser_headers,
        )
        self.assertEqual(create_response.status_code, 200)
        saved_anomaly_id = create_response.json()["items"][0]["saved_anomaly_id"]

        patch_response = client.patch(
            f"/api/account/saved-anomalies/{saved_anomaly_id}",
            json={"status": "resolved", "note": "Confirmed and closed"},
            headers=self.browser_headers,
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["items"][0]["status"], "resolved")
        self.assertEqual(patch_response.json()["items"][0]["note"], "Confirmed and closed")

        delete_response = client.delete(
            f"/api/account/saved-anomalies/{saved_anomaly_id}",
            headers=self.browser_headers,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["items"], [])

    def test_saved_missed_filing_supports_patch_and_delete(self) -> None:
        client = self.create_client()
        self._login(client, "missed-followup@example.com", "/account")

        create_response = client.post(
            "/api/account/saved-missed-filings",
            json={
                "copo": YUKON_COPO,
                "tax_type": "sales",
                "anomaly_date": "2025-12-01",
                "activity_code": "455110",
                "baseline_method": "hybrid",
                "expected_value": 10000,
                "actual_value": 1000,
                "missing_amount": 9000,
                "missing_pct": 90,
                "status": "saved",
            },
            headers=self.browser_headers,
        )
        self.assertEqual(create_response.status_code, 200)
        saved_missed_filing_id = create_response.json()["items"][0]["saved_missed_filing_id"]

        patch_response = client.patch(
            f"/api/account/saved-missed-filings/{saved_missed_filing_id}",
            json={"status": "investigating", "note": "Finance director reviewing"},
            headers=self.browser_headers,
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.json()["items"][0]["status"], "investigating")
        self.assertEqual(patch_response.json()["items"][0]["note"], "Finance director reviewing")

        delete_response = client.delete(
            f"/api/account/saved-missed-filings/{saved_missed_filing_id}",
            headers=self.browser_headers,
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["items"], [])

    def test_forecast_preferences_reject_invalid_defaults(self) -> None:
        client = self.create_client()
        self._login(client, "invalid-forecast-defaults@example.com", "/account")

        cases = [
            {"forecast_model": "not-a-model"},
            {"forecast_horizon_months": 48},
            {"forecast_lookback_months": 18},
            {"forecast_confidence_level": 0.5},
            {"forecast_indicator_profile": "not-a-profile"},
        ]

        for payload in cases:
            with self.subTest(payload=payload):
                response = client.put(
                    "/api/account/forecast-preferences",
                    json={
                        "default_city_copo": YUKON_COPO,
                        "default_tax_type": "sales",
                        "forecast_scope": "municipal",
                        **payload,
                    },
                    headers=self.browser_headers,
                )
                self.assertEqual(response.status_code, 400)

    def test_saved_anomaly_rejects_invalid_type_and_tax(self) -> None:
        client = self.create_client()
        self._login(client, "invalid-anomaly@example.com", "/account")

        bad_tax = client.post(
            "/api/account/saved-anomalies",
            json={
                "copo": YUKON_COPO,
                "tax_type": "bad-tax",
                "anomaly_date": "2025-12-01",
                "anomaly_type": "yoy_drop",
                "status": "saved",
            },
            headers=self.browser_headers,
        )
        bad_type = client.post(
            "/api/account/saved-anomalies",
            json={
                "copo": YUKON_COPO,
                "tax_type": "sales",
                "anomaly_date": "2025-12-01",
                "anomaly_type": "not-real",
                "status": "saved",
            },
            headers=self.browser_headers,
        )

        self.assertEqual(bad_tax.status_code, 400)
        self.assertEqual(bad_type.status_code, 400)

    def test_interest_update_rejects_incomplete_target(self) -> None:
        client = self.create_client()
        self._login(client, "bad-interest@example.com", "/account")

        response = client.put(
            "/api/account/interests",
            json={"items": [{"interest_type": "city"}]},
            headers=self.browser_headers,
        )

        self.assertEqual(response.status_code, 400)

    def test_logout_revokes_session(self) -> None:
        client = self.create_client()
        self._login(client, "logout-test@example.com")

        logout_response = client.post("/api/auth/logout", headers=self.browser_headers)
        self.assertEqual(logout_response.status_code, 200)

        session_response = client.get("/api/auth/session")
        self.assertFalse(session_response.json()["authenticated"])
        protected_response = client.get("/api/stats/missed-filings")
        self.assertEqual(protected_response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
