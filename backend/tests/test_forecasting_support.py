from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from app.db.psycopg import get_cursor
from app.services.forecasting import assess_series_quality, build_forecast_package, calendarize_series, ensure_forecast_schema

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.load_data import parse_ledger_filename  # noqa: E402


class TestForecastingSupport(unittest.TestCase):
    def test_calendarize_and_quality_detect_gap(self) -> None:
        series = calendarize_series(
            [
                (pd.Timestamp("2024-01-31").date(), 100.0),
                (pd.Timestamp("2024-03-31").date(), 130.0),
            ]
        )
        quality = assess_series_quality(series, "sales", current_period=pd.Timestamp("2024-03-31"))

        self.assertEqual(quality["observation_count"], 2)
        self.assertEqual(quality["missing_month_count"], 1)
        self.assertTrue(quality["has_unresolved_gaps"])
        self.assertFalse(quality["advanced_models_allowed"])

    def test_dense_sales_history_allows_advanced_models(self) -> None:
        points = []
        value = 100.0
        for timestamp in pd.date_range("2021-01-31", periods=36, freq="ME"):
            points.append((timestamp.date(), value))
            value += 5.0

        series = calendarize_series(points)
        quality = assess_series_quality(series, "sales", current_period=pd.Timestamp("2023-12-31"))

        self.assertEqual(quality["observation_count"], 36)
        self.assertEqual(quality["missing_month_count"], 0)
        self.assertTrue(quality["advanced_models_allowed"])

    def test_parse_ledger_filename_supports_supplemental_month_files(self) -> None:
        self.assertEqual(
            parse_ledger_filename("ledger_sales_2025_m05_city.xls"),
            ("sales", 2025, 5, "city"),
        )
        self.assertEqual(
            parse_ledger_filename("ledger_use_2024_m06_county.xls"),
            ("use", 2024, 6, "county"),
        )
        self.assertEqual(
            parse_ledger_filename("ledger_lodging_2025_city.xls"),
            ("lodging", 2025, None, "city"),
        )

    def test_build_forecast_package_reuses_cached_payload_for_identical_inputs(self) -> None:
        with get_cursor() as cur:
            ensure_forecast_schema(cur)
            cur.execute(
                """
                DELETE FROM forecast_runs
                WHERE copo = %s
                  AND tax_type = %s
                  AND requested_model = %s
                  AND horizon_months = %s
                  AND lookback_months = %s
                  AND confidence_level = %s
                  AND indicator_profile = %s
                  AND activity_code IS NULL
                """,
                ("0955", "sales", "auto", 9, 24, 0.9, "balanced"),
            )

        with get_cursor() as cur:
            first = build_forecast_package(
                cur,
                copo="0955",
                tax_type="sales",
                requested_model="auto",
                horizon_months=9,
                lookback_months=24,
                confidence_level=0.9,
                indicator_profile="balanced",
                activity_code=None,
                persist=True,
            )

        with patch("app.services.forecasting._evaluate_models", side_effect=AssertionError("cache should bypass model evaluation")):
            with get_cursor() as cur:
                second = build_forecast_package(
                    cur,
                    copo="0955",
                    tax_type="sales",
                    requested_model="auto",
                    horizon_months=9,
                    lookback_months=24,
                    confidence_level=0.9,
                    indicator_profile="balanced",
                    activity_code=None,
                    persist=True,
                )

        self.assertIsNotNone(first.get("run_id"))
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["forecast_points"], second["forecast_points"])
        self.assertEqual(first["historical_points"], second["historical_points"])


if __name__ == "__main__":
    unittest.main()
