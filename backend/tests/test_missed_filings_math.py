from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import date, datetime, timezone
from unittest.mock import patch

import psycopg2.extras
from fastapi.testclient import TestClient

from app.db.psycopg import get_conn
from app.main import app

client = TestClient(app)


@contextmanager
def patched_feature_auth():
    settings = app.state.security_settings
    original_auth_mode = settings.auth_mode
    original_api_keys = set(settings.api_keys)
    original_token_default_roles = set(settings.token_default_roles)
    original_token_default_scopes = set(settings.token_default_scopes)

    settings.auth_mode = "token"
    settings.api_keys = {"test-read-key"}
    settings.token_default_roles = {"viewer"}
    settings.token_default_scopes = set()
    try:
        yield {"X-API-Key": "test-read-key"}
    finally:
        settings.auth_mode = original_auth_mode
        settings.api_keys = original_api_keys
        settings.token_default_roles = original_token_default_roles
        settings.token_default_scopes = original_token_default_scopes


@contextmanager
def patched_missed_filing_cache(
    rows: list[dict[str, object]],
    meta: dict[str, object],
):
    conn = get_conn()
    conn.autocommit = False

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TEMP TABLE missed_filing_candidates (
                id BIGSERIAL PRIMARY KEY,
                copo VARCHAR(10) NOT NULL,
                city_name TEXT NOT NULL,
                tax_type VARCHAR(10) NOT NULL,
                anomaly_date DATE NOT NULL,
                activity_code VARCHAR(6) NOT NULL,
                activity_description TEXT NOT NULL,
                city_total NUMERIC(14,2) NOT NULL,
                city_prior_year_total NUMERIC(14,2),
                city_trailing_mean_3 NUMERIC(14,2),
                city_trailing_count_3 INTEGER,
                city_trailing_mean_6 NUMERIC(14,2),
                city_trailing_count_6 INTEGER,
                city_trailing_mean_12 NUMERIC(14,2),
                city_trailing_count_12 INTEGER,
                city_trailing_median_12 NUMERIC(14,2),
                city_exp_weighted_avg_12 NUMERIC(14,2),
                prior_year_value NUMERIC(14,2),
                trailing_mean_3 NUMERIC(14,2),
                trailing_count_3 INTEGER,
                trailing_mean_6 NUMERIC(14,2),
                trailing_count_6 INTEGER,
                trailing_mean_12 NUMERIC(14,2),
                trailing_count_12 INTEGER,
                trailing_median_12 NUMERIC(14,2),
                exp_weighted_avg_12 NUMERIC(14,2),
                hybrid_expected_value NUMERIC(14,2),
                hybrid_city_expected_total NUMERIC(14,2),
                hybrid_missing_amount NUMERIC(14,2),
                hybrid_missing_pct NUMERIC(14,2),
                hybrid_baseline_share_pct NUMERIC(14,2),
                hybrid_baseline_months_used INTEGER,
                actual_value NUMERIC(14,2) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            ) ON COMMIT DROP
            """
        )
        cur.execute(
            """
            CREATE TEMP TABLE missed_filing_candidates_refresh_meta (
                singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
                last_refresh_at TIMESTAMPTZ NOT NULL,
                data_min_month DATE,
                data_max_month DATE,
                snapshot_row_count INTEGER NOT NULL,
                refresh_duration_seconds NUMERIC(12,2)
            ) ON COMMIT DROP
            """
        )

        payload = [
            (
                row["copo"],
                row["city_name"],
                row["tax_type"],
                row["anomaly_date"],
                row["activity_code"],
                row["activity_description"],
                row["city_total"],
                row["city_prior_year_total"],
                row["city_trailing_mean_3"],
                row["city_trailing_count_3"],
                row["city_trailing_mean_6"],
                row["city_trailing_count_6"],
                row["city_trailing_mean_12"],
                row["city_trailing_count_12"],
                row["city_trailing_median_12"],
                row["city_exp_weighted_avg_12"],
                row["prior_year_value"],
                row["trailing_mean_3"],
                row["trailing_count_3"],
                row["trailing_mean_6"],
                row["trailing_count_6"],
                row["trailing_mean_12"],
                row["trailing_count_12"],
                row["trailing_median_12"],
                row["exp_weighted_avg_12"],
                row["hybrid_expected_value"],
                row["hybrid_city_expected_total"],
                row["hybrid_missing_amount"],
                row["hybrid_missing_pct"],
                row["hybrid_baseline_share_pct"],
                row["hybrid_baseline_months_used"],
                row["actual_value"],
                row["created_at"],
            )
            for row in rows
        ]
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO missed_filing_candidates (
                copo,
                city_name,
                tax_type,
                anomaly_date,
                activity_code,
                activity_description,
                city_total,
                city_prior_year_total,
                city_trailing_mean_3,
                city_trailing_count_3,
                city_trailing_mean_6,
                city_trailing_count_6,
                city_trailing_mean_12,
                city_trailing_count_12,
                city_trailing_median_12,
                city_exp_weighted_avg_12,
                prior_year_value,
                trailing_mean_3,
                trailing_count_3,
                trailing_mean_6,
                trailing_count_6,
                trailing_mean_12,
                trailing_count_12,
                trailing_median_12,
                exp_weighted_avg_12,
                hybrid_expected_value,
                hybrid_city_expected_total,
                hybrid_missing_amount,
                hybrid_missing_pct,
                hybrid_baseline_share_pct,
                hybrid_baseline_months_used,
                actual_value,
                created_at
            ) VALUES %s
            """,
            payload,
            page_size=100,
        )
        cur.execute(
            """
            INSERT INTO missed_filing_candidates_refresh_meta (
                singleton,
                last_refresh_at,
                data_min_month,
                data_max_month,
                snapshot_row_count,
                refresh_duration_seconds
            ) VALUES (TRUE, %s, %s, %s, %s, %s)
            """,
            (
                meta["last_refresh_at"],
                meta["data_min_month"],
                meta["data_max_month"],
                meta["snapshot_row_count"],
                meta["refresh_duration_seconds"],
            ),
        )

    @contextmanager
    def temp_get_cursor(*, dict_cursor: bool = True):
        cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()

    with patch("app.api.analytics.get_cursor", temp_get_cursor):
        try:
            yield
        finally:
            conn.rollback()
            conn.close()


def make_cache_row(**overrides: object) -> dict[str, object]:
    row = {
        "copo": "TST001",
        "city_name": "Testville",
        "tax_type": "sales",
        "anomaly_date": date(2026, 1, 1),
        "activity_code": "111111",
        "activity_description": "Widget Stores",
        "city_total": 9000.0,
        "city_prior_year_total": 10000.0,
        "city_trailing_mean_3": 9200.0,
        "city_trailing_count_3": 3,
        "city_trailing_mean_6": 9100.0,
        "city_trailing_count_6": 6,
        "city_trailing_mean_12": 9050.0,
        "city_trailing_count_12": 12,
        "city_trailing_median_12": 9000.0,
        "city_exp_weighted_avg_12": 9100.0,
        "prior_year_value": 1000.0,
        "trailing_mean_3": 550.0,
        "trailing_count_3": 3,
        "trailing_mean_6": 500.0,
        "trailing_count_6": 6,
        "trailing_mean_12": 480.0,
        "trailing_count_12": 12,
        "trailing_median_12": 500.0,
        "exp_weighted_avg_12": 490.0,
        "hybrid_expected_value": 800.0,
        "hybrid_city_expected_total": 9600.0,
        "hybrid_missing_amount": 700.0,
        "hybrid_missing_pct": 87.5,
        "hybrid_baseline_share_pct": 8.33,
        "hybrid_baseline_months_used": 13,
        "actual_value": 100.0,
        "created_at": datetime(2026, 4, 1, 12, 0, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return row


class TestMissedFilingsMath(unittest.TestCase):
    def test_hybrid_run_rate_and_severity_are_deterministic(self) -> None:
        meta = {
            "last_refresh_at": datetime(2026, 4, 1, 12, 30, tzinfo=timezone.utc),
            "data_min_month": date(2024, 5, 1),
            "data_max_month": date(2026, 1, 1),
            "snapshot_row_count": 1,
            "refresh_duration_seconds": 123.45,
        }
        with patched_missed_filing_cache([make_cache_row()], meta):
            with patched_feature_auth() as headers:
                response = client.get(
                    "/api/stats/missed-filings",
                    params={
                        "run_rate_method": "hybrid",
                        "min_expected_value": 0,
                        "min_missing_amount": 0,
                        "min_missing_pct": 0,
                        "min_baseline_share_pct": 0,
                        "high_missing_amount": 600,
                        "high_missing_pct": 70,
                        "critical_missing_amount": 900,
                        "critical_missing_pct": 90,
                        "limit": 10,
                    },
                    headers=headers,
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        item = data["items"][0]

        self.assertEqual(item["baseline_method"], "hybrid")
        self.assertEqual(item["baseline_months_used"], 13)
        self.assertAlmostEqual(item["expected_value"], 800.0, places=2)
        self.assertAlmostEqual(item["actual_value"], 100.0, places=2)
        self.assertAlmostEqual(item["missing_amount"], 700.0, places=2)
        self.assertAlmostEqual(item["missing_pct"], 87.5, places=2)
        self.assertAlmostEqual(item["baseline_share_pct"], 8.33, places=2)
        self.assertEqual(item["severity"], "high")

        refresh_info = data["refresh_info"]
        self.assertEqual(refresh_info["data_min_month"], "2024-05-01")
        self.assertEqual(refresh_info["data_max_month"], "2026-01-01")
        self.assertEqual(refresh_info["snapshot_row_count"], 1)
        self.assertAlmostEqual(refresh_info["refresh_duration_seconds"], 123.45, places=2)

    def test_trailing_mean_method_respects_baseline_sufficiency(self) -> None:
        weak_row = make_cache_row(
            copo="TST002",
            activity_code="222222",
            activity_description="Weak History",
            prior_year_value=None,
            trailing_mean_3=300.0,
            trailing_count_3=1,
            trailing_mean_6=300.0,
            trailing_count_6=1,
            trailing_mean_12=300.0,
            trailing_count_12=1,
            trailing_median_12=300.0,
            exp_weighted_avg_12=300.0,
            hybrid_expected_value=None,
            hybrid_city_expected_total=9600.0,
            hybrid_missing_amount=None,
            hybrid_missing_pct=None,
            hybrid_baseline_share_pct=None,
            hybrid_baseline_months_used=0,
            actual_value=50.0,
        )
        strong_row = make_cache_row(
            copo="TST003",
            activity_code="333333",
            activity_description="Strong History",
            prior_year_value=None,
            trailing_mean_3=300.0,
            trailing_count_3=3,
            trailing_mean_6=320.0,
            trailing_count_6=6,
            trailing_mean_12=340.0,
            trailing_count_12=12,
            trailing_median_12=330.0,
            exp_weighted_avg_12=335.0,
            hybrid_expected_value=330.0,
            hybrid_city_expected_total=9600.0,
            hybrid_missing_amount=210.0,
            hybrid_missing_pct=63.64,
            hybrid_baseline_share_pct=3.44,
            hybrid_baseline_months_used=12,
            actual_value=120.0,
        )
        meta = {
            "last_refresh_at": datetime(2026, 4, 1, 13, 0, tzinfo=timezone.utc),
            "data_min_month": date(2024, 5, 1),
            "data_max_month": date(2026, 1, 1),
            "snapshot_row_count": 2,
            "refresh_duration_seconds": 99.0,
        }

        with patched_missed_filing_cache([weak_row, strong_row], meta):
            with patched_feature_auth() as headers:
                response = client.get(
                    "/api/stats/missed-filings",
                    params={
                        "run_rate_method": "trailing_mean_3",
                        "min_expected_value": 0,
                        "min_missing_amount": 0,
                        "min_missing_pct": 0,
                        "min_baseline_share_pct": 0,
                        "limit": 10,
                    },
                    headers=headers,
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        item = data["items"][0]
        self.assertEqual(item["copo"], "TST003")
        self.assertEqual(item["baseline_method"], "trailing_mean_3")
        self.assertEqual(item["baseline_months_used"], 3)
        self.assertAlmostEqual(item["expected_value"], 300.0, places=2)
        self.assertAlmostEqual(item["missing_amount"], 180.0, places=2)

    def test_trailing_mean_default_threshold_path_is_deterministic(self) -> None:
        row = make_cache_row(
            copo="TST004",
            activity_code="444444",
            activity_description="Fast Path History",
            city_trailing_mean_3=15000.0,
            city_trailing_count_3=3,
            city_trailing_mean_6=15000.0,
            city_trailing_count_6=6,
            city_trailing_mean_12=15000.0,
            city_trailing_count_12=12,
            city_trailing_median_12=15000.0,
            city_exp_weighted_avg_12=15000.0,
            prior_year_value=None,
            trailing_mean_3=6000.0,
            trailing_count_3=3,
            trailing_mean_6=6100.0,
            trailing_count_6=6,
            trailing_mean_12=6200.0,
            trailing_count_12=12,
            trailing_median_12=6150.0,
            exp_weighted_avg_12=6180.0,
            hybrid_expected_value=6150.0,
            hybrid_city_expected_total=15000.0,
            hybrid_missing_amount=4150.0,
            hybrid_missing_pct=67.48,
            hybrid_baseline_share_pct=41.0,
            hybrid_baseline_months_used=12,
            actual_value=2000.0,
        )
        meta = {
            "last_refresh_at": datetime(2026, 4, 2, 9, 0, tzinfo=timezone.utc),
            "data_min_month": date(2024, 5, 1),
            "data_max_month": date(2026, 1, 1),
            "snapshot_row_count": 1,
            "refresh_duration_seconds": 88.0,
        }

        with patched_missed_filing_cache([row], meta):
            with patched_feature_auth() as headers:
                response = client.get(
                    "/api/stats/missed-filings",
                    params={
                        "run_rate_method": "trailing_mean_3",
                        "limit": 10,
                    },
                    headers=headers,
                )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 1)
        item = data["items"][0]
        self.assertEqual(item["baseline_method"], "trailing_mean_3")
        self.assertEqual(item["baseline_months_used"], 3)
        self.assertAlmostEqual(item["expected_value"], 6000.0, places=2)
        self.assertAlmostEqual(item["missing_amount"], 4000.0, places=2)
        self.assertAlmostEqual(item["missing_pct"], 66.67, places=2)
        self.assertAlmostEqual(item["baseline_share_pct"], 40.0, places=2)
        self.assertEqual(item["severity"], "high")
