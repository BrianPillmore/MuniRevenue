"""Tests for the admin-only GTM (go-to-market) dashboard endpoints.

Covers:
    GET  /api/admin/gtm/pipeline
    GET  /api/admin/gtm/users
    POST /api/admin/gtm/send-reports

Auth model:
    - Unauthenticated           → 401
    - Authenticated, non-admin  → 403
    - Authenticated, is_admin   → 200

All tests use the magic-link browser auth flow (auth_mode=off, magic links on).
Admin status is set directly in the database after the login sequence.
"""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.db.psycopg import get_cursor
from app.main import create_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_user(email: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM app_users WHERE email_normalized = %s",
            [email.strip().lower()],
        )


class _AdminBase(unittest.TestCase):
    """Shared helpers for GTM admin tests."""

    browser_headers = {"Origin": "http://testserver"}

    def create_client(self, extra_env: dict[str, str] | None = None) -> TestClient:
        env: dict[str, str] = {
            "MUNIREV_API_AUTH_MODE": "off",
            "MUNIREV_AUTH_MAGIC_LINK_ENABLED": "true",
            "MUNIREV_EMAIL_MODE": "log",
            "MUNIREV_AUTH_COOKIE_SECURE": "false",
            "MUNIREV_AUTH_MAGIC_LINK_BASE_URL": "http://testserver",
            "MUNIREV_CSRF_TRUSTED_ORIGINS": "http://testserver",
        }
        if extra_env:
            env.update(extra_env)
        patcher = patch.dict(os.environ, env, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        tc = TestClient(create_app())
        tc.headers.update({"Origin": "http://testserver"})
        return tc

    def _prepare_user(self, email: str) -> None:
        prepared = getattr(self, "_prepared_users", set())
        if email not in prepared:
            _cleanup_user(email)
            self.addCleanup(_cleanup_user, email)
            prepared.add(email)
            self._prepared_users = prepared

    def _issue_magic_link(self, client: TestClient, email: str, next_path: str = "/account") -> str:
        self._prepare_user(email)
        resp = client.post(
            "/api/auth/magic-link/request",
            json={"email": email, "next_path": next_path},
        )
        self.assertEqual(resp.status_code, 200, f"magic-link request failed: {resp.text}")
        link = client.app.state.magic_link_debug_links[email.lower()]
        return parse_qs(urlparse(link).query)["token"][0]

    def _login(self, client: TestClient, email: str, next_path: str = "/account") -> None:
        """Full two-step magic link flow (verify email, then sign in)."""
        # Step 1: verify email
        token = self._issue_magic_link(client, email, next_path)
        client.get(f"/auth/verify?token={token}", follow_redirects=False)
        # Step 2: sign in (sets session cookie)
        token = self._issue_magic_link(client, email, next_path)
        resp = client.get(f"/auth/verify?token={token}", follow_redirects=False)
        self.assertEqual(resp.status_code, 303, f"Sign-in verify failed: {resp.text}")

    def _make_admin(self, email: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE app_users SET is_admin = TRUE WHERE email_normalized = %s",
                [email.strip().lower()],
            )


# ===========================================================================
# 1. Authentication and authorisation guards
# ===========================================================================


class TestGtmAuthGuards(_AdminBase):
    """All three endpoints must reject unauthenticated and non-admin requests."""

    def test_pipeline_requires_authentication(self) -> None:
        client = self.create_client()
        resp = client.get("/api/admin/gtm/pipeline")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("detail", resp.json())

    def test_users_requires_authentication(self) -> None:
        client = self.create_client()
        resp = client.get("/api/admin/gtm/users")
        self.assertEqual(resp.status_code, 401)

    def test_send_reports_requires_authentication(self) -> None:
        client = self.create_client()
        resp = client.post(
            "/api/admin/gtm/send-reports",
            json={"year": 2026, "month": 3},
        )
        self.assertEqual(resp.status_code, 401)

    def test_pipeline_rejects_non_admin_user(self) -> None:
        client = self.create_client()
        self._login(client, "gtm-nonadmin-pipeline@example.com")
        resp = client.get("/api/admin/gtm/pipeline")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("Admin", resp.json()["detail"])

    def test_users_rejects_non_admin_user(self) -> None:
        client = self.create_client()
        self._login(client, "gtm-nonadmin-users@example.com")
        resp = client.get("/api/admin/gtm/users")
        self.assertEqual(resp.status_code, 403)

    def test_send_reports_rejects_non_admin_user(self) -> None:
        client = self.create_client()
        self._login(client, "gtm-nonadmin-send@example.com")
        resp = client.post(
            "/api/admin/gtm/send-reports",
            json={"year": 2026, "month": 3},
        )
        self.assertEqual(resp.status_code, 403)


# ===========================================================================
# 2. GET /api/admin/gtm/pipeline
# ===========================================================================


class TestGtmPipeline(_AdminBase):
    """Pipeline endpoint returns coverage data for all Oklahoma jurisdictions."""

    @classmethod
    def setUpClass(cls) -> None:
        # Create a shared client + admin user once for all pipeline tests.
        # Each test method still goes through create_client() for isolation,
        # but we pre-seed the admin state here for the class-level methods.
        pass

    def _admin_client(self, email: str) -> TestClient:
        client = self.create_client()
        self._login(client, email)
        self._make_admin(email)
        return client

    def test_pipeline_returns_200(self) -> None:
        client = self._admin_client("gtm-pipeline-200@example.com")
        resp = client.get("/api/admin/gtm/pipeline")
        self.assertEqual(resp.status_code, 200)

    def test_pipeline_top_level_keys(self) -> None:
        client = self._admin_client("gtm-pipeline-keys@example.com")
        data = client.get("/api/admin/gtm/pipeline").json()
        for key in ("stats", "cities", "counties"):
            self.assertIn(key, data)

    def test_pipeline_stats_has_all_fields(self) -> None:
        client = self._admin_client("gtm-pipeline-statsfields@example.com")
        stats = client.get("/api/admin/gtm/pipeline").json()["stats"]
        required = (
            "total_cities", "cities_with_contact", "cities_with_email",
            "cities_with_user", "total_counties", "counties_with_contact",
            "counties_with_email", "counties_with_user",
            "total_active_users", "total_magic_links_sent",
        )
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, stats)
                self.assertIsInstance(stats[field], int)

    def test_pipeline_stats_totals_match_list_lengths(self) -> None:
        client = self._admin_client("gtm-pipeline-totals@example.com")
        data = client.get("/api/admin/gtm/pipeline").json()
        self.assertEqual(data["stats"]["total_cities"], len(data["cities"]))
        self.assertEqual(data["stats"]["total_counties"], len(data["counties"]))

    def test_pipeline_coverage_counts_do_not_exceed_totals(self) -> None:
        client = self._admin_client("gtm-pipeline-coverage@example.com")
        stats = client.get("/api/admin/gtm/pipeline").json()["stats"]
        self.assertLessEqual(stats["cities_with_contact"], stats["total_cities"])
        self.assertLessEqual(stats["cities_with_email"],   stats["total_cities"])
        self.assertLessEqual(stats["cities_with_user"],    stats["total_cities"])
        self.assertLessEqual(stats["counties_with_contact"], stats["total_counties"])
        self.assertLessEqual(stats["counties_with_email"],   stats["total_counties"])
        self.assertLessEqual(stats["counties_with_user"],    stats["total_counties"])

    def test_pipeline_city_row_structure(self) -> None:
        client = self._admin_client("gtm-pipeline-cityrow@example.com")
        cities = client.get("/api/admin/gtm/pipeline").json()["cities"]
        self.assertGreater(len(cities), 0, "Cities list must not be empty")

        row = cities[0]
        for field in ("copo", "name", "jurisdiction_type",
                      "contact_count", "email_count", "phone_count", "user_count"):
            self.assertIn(field, row, f"City row must include '{field}'")

        # Counts are non-negative integers
        for count_field in ("contact_count", "email_count", "phone_count", "user_count"):
            self.assertGreaterEqual(row[count_field], 0)

    def test_pipeline_county_row_has_no_county_name(self) -> None:
        """County rows return county_name=None (counties don't nest inside counties)."""
        client = self._admin_client("gtm-pipeline-countyrow@example.com")
        counties = client.get("/api/admin/gtm/pipeline").json()["counties"]
        self.assertGreater(len(counties), 0)
        for row in counties[:5]:
            self.assertIsNone(row.get("county_name"))

    def test_pipeline_cities_are_type_city(self) -> None:
        client = self._admin_client("gtm-pipeline-citytype@example.com")
        cities = client.get("/api/admin/gtm/pipeline").json()["cities"]
        for city in cities[:10]:
            self.assertEqual(city["jurisdiction_type"], "city")

    def test_pipeline_counties_are_type_county(self) -> None:
        client = self._admin_client("gtm-pipeline-countytype@example.com")
        counties = client.get("/api/admin/gtm/pipeline").json()["counties"]
        for county in counties[:10]:
            self.assertEqual(county["jurisdiction_type"], "county")

    def test_pipeline_active_users_count_is_non_negative(self) -> None:
        client = self._admin_client("gtm-pipeline-users@example.com")
        stats = client.get("/api/admin/gtm/pipeline").json()["stats"]
        self.assertGreaterEqual(stats["total_active_users"], 0)
        self.assertGreaterEqual(stats["total_magic_links_sent"], 0)

    def test_pipeline_magic_links_count_grows_after_request(self) -> None:
        """Issuing a new magic link increments total_magic_links_sent."""
        client = self.create_client()
        email = "gtm-linkcounter@example.com"
        self._login(client, email)
        self._make_admin(email)

        before = client.get("/api/admin/gtm/pipeline").json()["stats"]["total_magic_links_sent"]

        # Issue one more link
        self._issue_magic_link(client, "gtm-linkcounter-extra@example.com")

        after = client.get("/api/admin/gtm/pipeline").json()["stats"]["total_magic_links_sent"]
        self.assertGreater(after, before)


# ===========================================================================
# 3. GET /api/admin/gtm/users
# ===========================================================================


class TestGtmUsers(_AdminBase):
    """Users endpoint returns all registered accounts."""

    def _admin_client(self, email: str) -> TestClient:
        client = self.create_client()
        self._login(client, email)
        self._make_admin(email)
        return client

    def test_users_returns_200(self) -> None:
        client = self._admin_client("gtm-users-200@example.com")
        resp = client.get("/api/admin/gtm/users")
        self.assertEqual(resp.status_code, 200)

    def test_users_has_total_and_list(self) -> None:
        client = self._admin_client("gtm-users-keys@example.com")
        data = client.get("/api/admin/gtm/users").json()
        self.assertIn("total", data)
        self.assertIn("users", data)
        self.assertIsInstance(data["users"], list)

    def test_users_total_matches_list_length(self) -> None:
        client = self._admin_client("gtm-users-totallen@example.com")
        data = client.get("/api/admin/gtm/users").json()
        self.assertEqual(data["total"], len(data["users"]))

    def test_users_total_is_positive(self) -> None:
        """At least the admin user we created must appear."""
        client = self._admin_client("gtm-users-positive@example.com")
        data = client.get("/api/admin/gtm/users").json()
        self.assertGreaterEqual(data["total"], 1)

    def test_users_row_structure(self) -> None:
        client = self._admin_client("gtm-users-rowstruct@example.com")
        users = client.get("/api/admin/gtm/users").json()["users"]
        self.assertGreater(len(users), 0)

        row = users[0]
        for field in ("user_id", "email", "created_at", "status"):
            self.assertIn(field, row, f"User row must include '{field}'")

        # Optional nullable fields present
        for field in ("display_name", "job_title", "organization_name",
                      "jurisdiction_name", "copo", "last_login_at"):
            self.assertIn(field, row)

    def test_users_includes_logged_in_admin(self) -> None:
        email = "gtm-users-self@example.com"
        client = self._admin_client(email)
        users = client.get("/api/admin/gtm/users").json()["users"]
        found = next((u for u in users if u["email"] == email), None)
        self.assertIsNotNone(found, f"{email} must appear in user list")
        self.assertEqual(found["status"], "active")

    def test_users_sorted_by_created_at_descending(self) -> None:
        """The most recently created user should appear first."""
        client = self.create_client()
        # Create admin first (older), then a regular user (newer)
        admin_email = "gtm-users-sort-admin@example.com"
        newer_email = "gtm-users-sort-newer@example.com"
        self._login(client, admin_email)
        self._make_admin(admin_email)
        # Register a newer user
        self._issue_magic_link(client, newer_email)

        users = client.get("/api/admin/gtm/users").json()["users"]
        created_dates = [u["created_at"] for u in users[:10]]
        self.assertEqual(
            created_dates,
            sorted(created_dates, reverse=True),
            "Users should be sorted by created_at descending",
        )


# ===========================================================================
# 4. POST /api/admin/gtm/send-reports
# ===========================================================================


class TestGtmSendReports(_AdminBase):
    """send-reports endpoint enqueues a background email campaign."""

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._send_patcher = patch("app.api.gtm._run_send")
        cls._send_patcher.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._send_patcher.stop()
        super().tearDownClass()

    def _admin_client(self, email: str) -> TestClient:
        client = self.create_client()
        self._login(client, email)
        self._make_admin(email)
        return client

    def test_send_reports_returns_200_and_queued_true(self) -> None:
        client = self._admin_client("gtm-send-200@example.com")
        resp = client.post(
            "/api/admin/gtm/send-reports",
            json={"year": 2026, "month": 3},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("queued", data)
        self.assertTrue(data["queued"])

    def test_send_reports_period_label_content(self) -> None:
        client = self._admin_client("gtm-send-label@example.com")
        data = client.post(
            "/api/admin/gtm/send-reports",
            json={"year": 2026, "month": 3},
        ).json()
        self.assertIn("period", data)
        self.assertIn("2026", data["period"])
        self.assertIn("March", data["period"])

    def test_send_reports_all_months_produce_correct_labels(self) -> None:
        expected = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
        client = self._admin_client("gtm-send-allmonths@example.com")
        for month, month_name in enumerate(expected, start=1):
            with self.subTest(month=month):
                data = client.post(
                    "/api/admin/gtm/send-reports",
                    json={"year": 2025, "month": month},
                ).json()
                self.assertIn(month_name, data["period"])

    def test_send_reports_rejects_month_zero(self) -> None:
        client = self._admin_client("gtm-send-m0@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"year": 2026, "month": 0})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_rejects_month_thirteen(self) -> None:
        client = self._admin_client("gtm-send-m13@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"year": 2026, "month": 13})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_rejects_negative_month(self) -> None:
        client = self._admin_client("gtm-send-mneg@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"year": 2026, "month": -5})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_rejects_year_before_2000(self) -> None:
        client = self._admin_client("gtm-send-y1999@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"year": 1999, "month": 1})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_rejects_year_after_2100(self) -> None:
        client = self._admin_client("gtm-send-y2101@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"year": 2101, "month": 1})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_rejects_missing_month(self) -> None:
        client = self._admin_client("gtm-send-nomonth@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"year": 2026})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_rejects_missing_year(self) -> None:
        client = self._admin_client("gtm-send-noyear@example.com")
        resp = client.post("/api/admin/gtm/send-reports", json={"month": 3})
        self.assertEqual(resp.status_code, 422)

    def test_send_reports_boundary_years_are_valid(self) -> None:
        """Years 2000 and 2100 are valid edge values."""
        client = self._admin_client("gtm-send-boundary@example.com")
        for year in (2000, 2100):
            with self.subTest(year=year):
                resp = client.post(
                    "/api/admin/gtm/send-reports",
                    json={"year": year, "month": 6},
                )
                self.assertEqual(resp.status_code, 200)

    def test_send_reports_boundary_months_are_valid(self) -> None:
        """Months 1 and 12 are valid edge values."""
        client = self._admin_client("gtm-send-mbound@example.com")
        for month in (1, 12):
            with self.subTest(month=month):
                resp = client.post(
                    "/api/admin/gtm/send-reports",
                    json={"year": 2025, "month": month},
                )
                self.assertEqual(resp.status_code, 200)


# ===========================================================================
# 5. is_admin flag in session response
# ===========================================================================


class TestIsAdminSessionFlag(_AdminBase):
    """The /api/auth/session endpoint must expose is_admin correctly."""

    def test_session_includes_is_admin_field(self) -> None:
        client = self.create_client()
        self._login(client, "session-flag-basic@example.com")
        session = client.get("/api/auth/session").json()
        self.assertTrue(session["authenticated"])
        self.assertIn("is_admin", session["user"])

    def test_new_user_has_is_admin_false(self) -> None:
        client = self.create_client()
        self._login(client, "session-flag-false@example.com")
        session = client.get("/api/auth/session").json()
        self.assertFalse(session["user"]["is_admin"])

    def test_promoted_user_has_is_admin_true(self) -> None:
        """After UPDATE is_admin=TRUE in DB and re-login, session shows is_admin=true."""
        client = self.create_client()
        email = "session-flag-promote@example.com"
        self._login(client, email)
        self.assertFalse(client.get("/api/auth/session").json()["user"]["is_admin"])

        self._make_admin(email)
        # Re-login to get a fresh session (new session row reads new DB value)
        self._login(client, email)
        self.assertTrue(client.get("/api/auth/session").json()["user"]["is_admin"])

    def test_unauthenticated_session_has_no_user(self) -> None:
        client = self.create_client()
        session = client.get("/api/auth/session").json()
        self.assertFalse(session["authenticated"])
        self.assertIsNone(session["user"])


if __name__ == "__main__":
    unittest.main()
