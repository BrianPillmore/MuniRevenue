from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

from app.services.forecasting import assess_series_quality, calendarize_series

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


if __name__ == "__main__":
    unittest.main()
