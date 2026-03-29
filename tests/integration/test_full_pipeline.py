"""Integration tests for the full MuniRev pipeline.

These tests verify the end-to-end flow:
  OkTAP export file -> parser -> API -> (future: DB storage) -> analysis

Run from project root:
    cd backend && .venv/Scripts/python -m pytest ../tests/integration/ -v
"""
from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.services.oktap_parser import (
    detect_report_type,
    parse_ledger_export,
    parse_naics_export,
)
from app.services.analysis import analyze_excel_bytes

FIXTURES_DIR = Path(__file__).parent.parent.parent / "backend" / "tests" / "fixtures"
ASSETS_DIR = Path(__file__).parent.parent.parent / "backend" / "assets"


class FullLedgerPipelineTest(unittest.TestCase):
    """Test: OkTAP ledger export -> parse -> verify data integrity."""

    def test_parse_and_verify_yukon_sales(self) -> None:
        data = (FIXTURES_DIR / "ledger_yukon_sales_2026.xls").read_bytes()

        # Detect type
        report_type = detect_report_type(data)
        self.assertEqual(report_type, "ledger")

        # Parse
        report = parse_ledger_export(data, "sales")
        self.assertEqual(len(report.records), 9)

        # Verify financial totals match the export totals row
        # The export shows total returned = 20,268,738.66
        total_returned = sum(r.returned for r in report.records)
        self.assertEqual(total_returned, Decimal("20268738.66"))

        # Verify date range
        dates = sorted(r.voucher_date for r in report.records)
        self.assertEqual(str(dates[0]), "2025-07-09")
        self.assertEqual(str(dates[-1]), "2026-03-09")

        # Verify all records are for Yukon (0955)
        copos = {r.copo for r in report.records}
        self.assertEqual(copos, {"0955"})


class FullNaicsPipelineTest(unittest.TestCase):
    """Test: OkTAP NAICS export -> parse -> verify industry breakdown."""

    def test_parse_and_verify_yukon_naics(self) -> None:
        data = (FIXTURES_DIR / "naics_yukon_sales_2026_02.xls").read_bytes()

        # Detect type
        report_type = detect_report_type(data)
        self.assertEqual(report_type, "naics")

        # Parse
        report = parse_naics_export(data, "sales", 2026, 2)
        self.assertEqual(len(report.records), 471)

        # Verify sector totals sum to match the export totals row
        # Export shows total sector_total = 1,932,630.17 (approximately)
        total = sum(r.sector_total for r in report.records)
        # Allow for floating-point in the XML totals row
        self.assertAlmostEqual(float(total), 1932630.17, delta=0.01)

        # Verify top industry (department stores)
        top = max(report.records, key=lambda r: r.sector_total)
        self.assertEqual(top.activity_code, "455110")

        # Verify UNCLASSIFIED sector exists
        unclassified = [r for r in report.records if r.sector == "UNCLASSIFIED"]
        self.assertEqual(len(unclassified), 1)

        # Verify unique sector count
        sectors = {r.sector for r in report.records}
        self.assertGreater(len(sectors), 20)


class AnalysisFromSampleTest(unittest.TestCase):
    """Test: Sample xlsx -> analysis engine -> verify outputs."""

    def test_full_analysis_pipeline(self) -> None:
        sample = (ASSETS_DIR / "sample-data.xlsx").read_bytes()
        result = analyze_excel_bytes(sample)

        # Summary
        self.assertEqual(result.summary.records, 86)
        self.assertGreater(result.summary.average_returned, 0)

        # Forecast
        self.assertEqual(len(result.forecast), 12)
        for point in result.forecast:
            self.assertGreater(point.projected_returned, 0)
            self.assertLessEqual(point.lower_bound, point.projected_returned)
            self.assertGreaterEqual(point.upper_bound, point.projected_returned)

        # Seasonality
        self.assertEqual(len(result.seasonality), 12)

        # ANOVA
        self.assertIsNotNone(result.anova.f_statistic)
        self.assertTrue(result.anova.significant)

        # Highlights
        self.assertGreater(len(result.highlights), 3)


if __name__ == "__main__":
    unittest.main()
