from __future__ import annotations

import unittest
from pathlib import Path

import pandas as pd

from app.services.analysis import build_analysis, canonicalize_tax_data


class AnalysisServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_path = Path(__file__).resolve().parents[1] / "assets" / "sample-data.xlsx"

    def test_canonicalize_tax_data_with_sample_file(self) -> None:
        frame = pd.read_excel(self.sample_path)
        canonical = canonicalize_tax_data(frame)

        self.assertEqual(list(canonical.columns), ["voucher_date", "returned"])
        self.assertEqual(len(canonical), 86)
        self.assertTrue(canonical["voucher_date"].is_monotonic_increasing)

    def test_build_analysis_returns_forecast_and_highlights(self) -> None:
        frame = pd.read_excel(self.sample_path)
        canonical = canonicalize_tax_data(frame)
        result = build_analysis(canonical)

        self.assertGreater(len(result.monthly_changes), 12)
        self.assertEqual(len(result.forecast), 12)
        self.assertGreaterEqual(len(result.highlights), 4)
        self.assertGreater(result.summary.latest_returned, 0)


if __name__ == "__main__":
    unittest.main()
