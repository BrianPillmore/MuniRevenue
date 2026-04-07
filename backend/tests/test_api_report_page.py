"""Tests for GET /api/report/{copo}/{year}/{month} — monthly report page endpoint.

The endpoint returns a single-page-load bundle: city metadata, revenue by
tax type, forecast comparison, missed-filing candidates, anomalies, NAICS
top-10 industries, and a 12-month trend series.

Authentication:
    Requires a valid session (require_feature_access).  Tests use the
    magic-link login flow so they're independent of API auth mode.

Test data:
    Yukon (copo=0955) — has known sales + use tax data.
    Latest period is discovered at class setup by querying the database.
"""

from __future__ import annotations

import os
import unittest
from datetime import date
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.db.psycopg import get_cursor
from app.main import create_app


YUKON_COPO = "0955"
NONEXISTENT_COPO = "9999"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup_user(email: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "DELETE FROM app_users WHERE email_normalized = %s",
            [email.strip().lower()],
        )


def _get_yukon_latest_period() -> tuple[int, int]:
    """Return (year, month) of the most recent Yukon sales ledger record."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                EXTRACT(YEAR  FROM MAX(voucher_date))::int AS year,
                EXTRACT(MONTH FROM MAX(voucher_date))::int AS month
            FROM ledger_records
            WHERE copo = %s
              AND tax_type = 'sales'
            """,
            [YUKON_COPO],
        )
        row = cur.fetchone()
    if not row or not row["year"]:
        raise RuntimeError("No Yukon sales ledger data found — run the import pipeline first.")
    return int(row["year"]), int(row["month"])


def _get_yukon_earliest_period() -> tuple[int, int]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                EXTRACT(YEAR  FROM MIN(voucher_date))::int AS year,
                EXTRACT(MONTH FROM MIN(voucher_date))::int AS month
            FROM ledger_records
            WHERE copo = %s
              AND tax_type = 'sales'
            """,
            [YUKON_COPO],
        )
        row = cur.fetchone()
    return int(row["year"]), int(row["month"])


class _AuthBase(unittest.TestCase):
    """Browser-auth helpers shared across report page test classes."""

    def create_client(self) -> TestClient:
        env = {
            "MUNIREV_API_AUTH_MODE": "off",
            "MUNIREV_AUTH_MAGIC_LINK_ENABLED": "true",
            "MUNIREV_EMAIL_MODE": "log",
            "MUNIREV_AUTH_COOKIE_SECURE": "false",
            "MUNIREV_AUTH_MAGIC_LINK_BASE_URL": "http://testserver",
            "MUNIREV_CSRF_TRUSTED_ORIGINS": "http://testserver",
        }
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

    def _login(self, client: TestClient, email: str) -> None:
        self._prepare_user(email)
        for _ in range(2):
            resp = client.post(
                "/api/auth/magic-link/request",
                json={"email": email, "next_path": "/account"},
            )
            self.assertEqual(resp.status_code, 200)
            link = client.app.state.magic_link_debug_links[email.lower()]
            token = parse_qs(urlparse(link).query)["token"][0]
            client.get(f"/auth/verify?token={token}", follow_redirects=False)


# ===========================================================================
# 1. Authentication guard
# ===========================================================================


class TestReportPageAuth(_AuthBase):
    """The report page requires authentication."""

    def test_unauthenticated_returns_401(self) -> None:
        client = self.create_client()
        resp = client.get(f"/api/report/{YUKON_COPO}/2026/1")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("detail", resp.json())


# ===========================================================================
# 2. Happy-path response shape
# ===========================================================================


class TestReportPageHappyPath(_AuthBase):
    """Valid requests return a fully-populated MonthlyReportResponse."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.year, cls.month = _get_yukon_latest_period()

    def setUp(self) -> None:
        self.client = self.create_client()
        self._login(self.client, "report-happy@example.com")

    def _get(self, copo: str = YUKON_COPO, year: int | None = None, month: int | None = None):
        y = year if year is not None else self.year
        m = month if month is not None else self.month
        return self.client.get(f"/api/report/{copo}/{y}/{m}")

    def test_returns_200(self) -> None:
        resp = self._get()
        self.assertEqual(resp.status_code, 200)

    def test_top_level_fields_present(self) -> None:
        data = self._get().json()
        required = (
            "copo", "city_name", "jurisdiction_type", "county_name", "population",
            "year", "month", "period_label",
            "tax_types", "revenue_by_tax_type",
            "missed_filings", "missed_filing_count",
            "anomalies", "anomaly_count",
            "naics_top_industries", "trend_12mo",
            "yoy_by_tax_type", "latest_data_date",
        )
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field, data)

    def test_identity_fields(self) -> None:
        data = self._get().json()
        self.assertEqual(data["copo"], YUKON_COPO)
        self.assertIn("Yukon", data["city_name"])
        self.assertEqual(data["year"], self.year)
        self.assertEqual(data["month"], self.month)
        self.assertEqual(data["jurisdiction_type"], "city")

    def test_period_label_contains_year(self) -> None:
        data = self._get().json()
        self.assertIn(str(self.year), data["period_label"])
        self.assertIsInstance(data["period_label"], str)
        self.assertGreater(len(data["period_label"]), 4)

    def test_tax_types_includes_sales(self) -> None:
        data = self._get().json()
        self.assertIsInstance(data["tax_types"], list)
        self.assertGreater(len(data["tax_types"]), 0)
        self.assertIn("sales", data["tax_types"])

    def test_revenue_by_tax_type_structure(self) -> None:
        items = self._get().json()["revenue_by_tax_type"]
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)

        sales = next((r for r in items if r["tax_type"] == "sales"), None)
        self.assertIsNotNone(sales, "revenue_by_tax_type must include a 'sales' entry")

        for field in ("tax_type", "actual", "forecast", "prior_year_actual"):
            self.assertIn(field, sales)

    def test_revenue_by_tax_type_one_entry_per_tax_type(self) -> None:
        data = self._get().json()
        self.assertEqual(
            len(data["revenue_by_tax_type"]),
            len(data["tax_types"]),
        )

    def test_missed_filings_list_and_count_consistent(self) -> None:
        data = self._get().json()
        self.assertIsInstance(data["missed_filings"], list)
        self.assertIsInstance(data["missed_filing_count"], int)
        self.assertEqual(data["missed_filing_count"], len(data["missed_filings"]))

    def test_missed_filing_row_structure(self) -> None:
        missed = self._get().json()["missed_filings"]
        for row in missed:
            for field in (
                "activity_code", "anomaly_date",
                "estimated_monthly_value", "expected_value", "actual_value",
                "missing_amount", "missing_pct", "severity",
            ):
                self.assertIn(field, row)
            self.assertIn(row["severity"], ("critical", "high", "medium"))

    def test_anomalies_list_and_count_consistent(self) -> None:
        data = self._get().json()
        self.assertIsInstance(data["anomalies"], list)
        self.assertIsInstance(data["anomaly_count"], int)
        self.assertEqual(data["anomaly_count"], len(data["anomalies"]))

    def test_anomaly_row_structure(self) -> None:
        anomalies = self._get().json()["anomalies"]
        for row in anomalies:
            for field in ("tax_type", "anomaly_type", "deviation_pct", "severity", "description"):
                self.assertIn(field, row)
            self.assertIn(row["severity"], ("critical", "high", "medium"))

    def test_trend_12mo_length_and_last_point(self) -> None:
        trend_dict = self._get().json()["trend_12mo"]
        self.assertIsInstance(trend_dict, dict)
        self.assertIn("sales", trend_dict)
        trend = trend_dict["sales"]
        self.assertIsInstance(trend, list)
        self.assertLessEqual(len(trend), 12)
        self.assertGreater(len(trend), 0, "Trend must have at least one data point")

        # Last point in the series must match the requested period
        last = trend[-1]
        self.assertEqual(last["year"], self.year)
        self.assertEqual(last["month"], self.month)

    def test_trend_12mo_point_structure(self) -> None:
        trend_dict = self._get().json()["trend_12mo"]
        for tax_type, trend in trend_dict.items():
            for point in trend:
                for field in ("year", "month", "actual"):
                    self.assertIn(field, point)
                self.assertIn("forecast", point)  # nullable, but key must exist
                self.assertGreaterEqual(point["actual"], 0)

    def test_trend_12mo_sorted_chronologically(self) -> None:
        trend_dict = self._get().json()["trend_12mo"]
        for tax_type, trend in trend_dict.items():
            dates = [(p["year"], p["month"]) for p in trend]
            self.assertEqual(dates, sorted(dates), f"Trend for {tax_type} must be sorted chronologically")

    def test_yoy_by_tax_type_one_entry_per_tax_type(self) -> None:
        data = self._get().json()
        self.assertEqual(
            len(data["yoy_by_tax_type"]),
            len(data["tax_types"]),
        )

    def test_yoy_row_structure(self) -> None:
        yoy = self._get().json()["yoy_by_tax_type"]
        for row in yoy:
            for field in ("tax_type", "current_year", "prior_year", "yoy_pct"):
                self.assertIn(field, row)

    def test_yoy_pct_is_none_without_prior_year(self) -> None:
        """If prior_year is null, yoy_pct must also be null (not a division error)."""
        yoy = self._get().json()["yoy_by_tax_type"]
        for row in yoy:
            if row["prior_year"] is None or row["prior_year"] == 0:
                self.assertIsNone(row["yoy_pct"],
                    f"yoy_pct must be null when prior_year is absent/zero for {row['tax_type']}")

    def test_naics_top_industries_max_ten(self) -> None:
        industries = self._get().json()["naics_top_industries"]
        self.assertIsInstance(industries, list)
        self.assertLessEqual(len(industries), 10)

    def test_naics_industry_row_structure(self) -> None:
        industries = self._get().json()["naics_top_industries"]
        for row in industries:
            for field in ("activity_code", "current_month"):
                self.assertIn(field, row)
            self.assertGreaterEqual(row["current_month"], 0)
            # yoy_pct is nullable
            self.assertIn("yoy_pct", row)

    def test_naics_sorted_by_revenue_descending(self) -> None:
        industries = self._get().json()["naics_top_industries"]
        if len(industries) < 2:
            self.skipTest("Not enough NAICS industries to test ordering")
        revenues = [r["current_month"] for r in industries]
        self.assertEqual(revenues, sorted(revenues, reverse=True),
                         "NAICS top industries must be sorted by current_month descending")

    def test_latest_data_date_is_valid_iso_string(self) -> None:
        data = self._get().json()
        self.assertIsNotNone(data["latest_data_date"])
        parsed = date.fromisoformat(data["latest_data_date"])
        self.assertGreater(parsed.year, 2000)

    def test_missed_filings_at_most_20(self) -> None:
        """The endpoint caps missed filings at 20."""
        missed = self._get().json()["missed_filings"]
        self.assertLessEqual(len(missed), 20)

    def test_sales_actual_is_positive_for_latest_period(self) -> None:
        """Yukon's latest period should have positive sales revenue."""
        data = self._get().json()
        sales = next(
            (r for r in data["revenue_by_tax_type"] if r["tax_type"] == "sales"),
            None,
        )
        self.assertIsNotNone(sales)
        if sales["actual"] is not None:
            self.assertGreater(sales["actual"], 0)


# ===========================================================================
# 3. Period with no data (returns 200 with null actuals)
# ===========================================================================


class TestReportPageNullPeriod(_AuthBase):
    """Requests for a valid city but with no data for that specific period
    return 200 with null actual values (not 404)."""

    def setUp(self) -> None:
        self.client = self.create_client()
        self._login(self.client, "report-nullperiod@example.com")

    def test_future_period_returns_200_with_null_actual(self) -> None:
        """A valid copo with no data for year 2099 returns 200, not 404."""
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2099/1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        # Tax types are populated from all-time history
        self.assertIn("sales", data["tax_types"])
        # But actual revenue for this future month is null
        sales = next(r for r in data["revenue_by_tax_type"] if r["tax_type"] == "sales")
        self.assertIsNone(sales["actual"])

    def test_future_period_has_empty_trend(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2099/1")
        data = resp.json()
        # Trend should have no points for a far-future period with no actuals
        for tax_type, points in data["trend_12mo"].items():
            for point in points:
                self.assertIsNotNone(point["actual"], f"trend_12mo[{tax_type}] only includes months with actuals")


# ===========================================================================
# 4. Error cases (404, 422)
# ===========================================================================


class TestReportPageErrors(_AuthBase):
    """Invalid requests return appropriate error codes."""

    def setUp(self) -> None:
        self.client = self.create_client()
        self._login(self.client, "report-errors@example.com")

    def test_nonexistent_copo_returns_404(self) -> None:
        resp = self.client.get(f"/api/report/{NONEXISTENT_COPO}/2026/1")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.json())
        self.assertIn(NONEXISTENT_COPO, resp.json()["detail"])

    def test_month_zero_returns_422(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2026/0")
        self.assertEqual(resp.status_code, 422)

    def test_month_thirteen_returns_422(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2026/13")
        self.assertEqual(resp.status_code, 422)

    def test_year_1999_returns_422(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/1999/1")
        self.assertEqual(resp.status_code, 422)

    def test_year_2101_returns_422(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2101/1")
        self.assertEqual(resp.status_code, 422)

    def test_boundary_year_2000_is_valid(self) -> None:
        """Year 2000 is within bounds (422 won't be raised for the year itself)."""
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2000/1")
        # 404 if no data, or 200 if data exists — either is valid; just not 422
        self.assertNotEqual(resp.status_code, 422)

    def test_boundary_year_2100_is_valid(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2100/1")
        self.assertNotEqual(resp.status_code, 422)

    def test_boundary_month_1_is_valid(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2026/1")
        self.assertNotEqual(resp.status_code, 422)

    def test_boundary_month_12_is_valid(self) -> None:
        resp = self.client.get(f"/api/report/{YUKON_COPO}/2026/12")
        self.assertNotEqual(resp.status_code, 422)


# ===========================================================================
# 5. Consistency checks across known periods
# ===========================================================================


class TestReportPageConsistency(_AuthBase):
    """Cross-period and cross-city consistency invariants."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.latest_year, cls.latest_month = _get_yukon_latest_period()
        cls.earliest_year, cls.earliest_month = _get_yukon_earliest_period()

    def setUp(self) -> None:
        self.client = self.create_client()
        self._login(self.client, "report-consistency@example.com")

    def test_earliest_and_latest_period_both_return_200(self) -> None:
        for year, month in (
            (self.earliest_year, self.earliest_month),
            (self.latest_year, self.latest_month),
        ):
            with self.subTest(year=year, month=month):
                resp = self.client.get(f"/api/report/{YUKON_COPO}/{year}/{month}")
                self.assertEqual(resp.status_code, 200)

    def test_latest_data_date_is_same_across_periods(self) -> None:
        """latest_data_date reflects the max available date, not the requested period."""
        resp_latest = self.client.get(
            f"/api/report/{YUKON_COPO}/{self.latest_year}/{self.latest_month}"
        ).json()
        resp_earliest = self.client.get(
            f"/api/report/{YUKON_COPO}/{self.earliest_year}/{self.earliest_month}"
        ).json()
        self.assertEqual(
            resp_latest["latest_data_date"],
            resp_earliest["latest_data_date"],
            "latest_data_date must be the global max, not the requested period",
        )

    def test_revenue_by_tax_type_tax_types_match_tax_types_list(self) -> None:
        data = self.client.get(
            f"/api/report/{YUKON_COPO}/{self.latest_year}/{self.latest_month}"
        ).json()
        revenue_tax_types = {r["tax_type"] for r in data["revenue_by_tax_type"]}
        self.assertEqual(set(data["tax_types"]), revenue_tax_types)

    def test_yoy_by_tax_type_tax_types_match_tax_types_list(self) -> None:
        data = self.client.get(
            f"/api/report/{YUKON_COPO}/{self.latest_year}/{self.latest_month}"
        ).json()
        yoy_tax_types = {r["tax_type"] for r in data["yoy_by_tax_type"]}
        self.assertEqual(set(data["tax_types"]), yoy_tax_types)

    def test_trend_12mo_actual_matches_revenue_by_tax_type_for_sales(self) -> None:
        """The last trend point's actual should match revenue_by_tax_type sales actual."""
        data = self.client.get(
            f"/api/report/{YUKON_COPO}/{self.latest_year}/{self.latest_month}"
        ).json()
        trend = data["trend_12mo"].get("sales", [])
        if not trend:
            self.skipTest("No trend data available")

        last_point = trend[-1]
        sales_revenue = next(
            (r for r in data["revenue_by_tax_type"] if r["tax_type"] == "sales"),
            None,
        )
        if sales_revenue and sales_revenue["actual"] is not None:
            self.assertAlmostEqual(
                last_point["actual"],
                sales_revenue["actual"],
                places=0,
                msg="Last trend point actual must match sales revenue for the period",
            )


if __name__ == "__main__":
    unittest.main()
