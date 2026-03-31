"""Tests for the OkTAP XML SpreadsheetML parser.

Uses real exported files from OkTAP as fixtures.
"""
from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path

from app.services.oktap_parser import (
    OkTAPParseError,
    detect_report_type,
    parse_ledger_export,
    parse_naics_export,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class DetectReportTypeTests(unittest.TestCase):
    def test_detects_ledger(self) -> None:
        data = (FIXTURES_DIR / "ledger_yukon_sales_2026.xls").read_bytes()
        self.assertEqual(detect_report_type(data), "ledger")

    def test_detects_naics(self) -> None:
        data = (FIXTURES_DIR / "naics_yukon_sales_2026_02.xls").read_bytes()
        self.assertEqual(detect_report_type(data), "naics")

    def test_rejects_garbage(self) -> None:
        with self.assertRaises(OkTAPParseError):
            detect_report_type(b"not xml at all")


class LedgerParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data = (FIXTURES_DIR / "ledger_yukon_sales_2026.xls").read_bytes()
        cls.report = parse_ledger_export(data, "sales", filename="test.xls")

    def test_record_count(self) -> None:
        self.assertEqual(len(self.report.records), 9)

    def test_tax_type(self) -> None:
        self.assertEqual(self.report.tax_type, "sales")

    def test_copo_is_yukon(self) -> None:
        for record in self.report.records:
            self.assertEqual(record.copo, "0955")

    def test_returned_values_are_decimal(self) -> None:
        for record in self.report.records:
            self.assertIsInstance(record.returned, Decimal)

    def test_first_record_values(self) -> None:
        first = self.report.records[0]
        self.assertEqual(str(first.voucher_date), "2025-07-09")
        self.assertEqual(first.returned, Decimal("2292935.43"))
        self.assertEqual(first.tax_rate, Decimal("0.04"))

    def test_totals_row_excluded(self) -> None:
        """The last row in the export has empty Copo (totals) and should be skipped."""
        for record in self.report.records:
            self.assertNotEqual(record.copo, "")

    def test_filename_preserved(self) -> None:
        self.assertEqual(self.report.filename, "test.xls")


class NaicsParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        data = (FIXTURES_DIR / "naics_yukon_sales_2026_02.xls").read_bytes()
        cls.report = parse_naics_export(data, "sales", 2026, 2, filename="naics.xls")

    def test_record_count(self) -> None:
        self.assertEqual(len(self.report.records), 471)

    def test_tax_type_and_period(self) -> None:
        self.assertEqual(self.report.tax_type, "sales")
        self.assertEqual(self.report.year, 2026)
        self.assertEqual(self.report.month, 2)

    def test_copo_is_yukon(self) -> None:
        for record in self.report.records:
            self.assertEqual(record.copo, "0955")

    def test_sector_total_is_decimal(self) -> None:
        for record in self.report.records:
            self.assertIsInstance(record.sector_total, Decimal)

    def test_department_stores_value(self) -> None:
        dept_stores = [r for r in self.report.records if r.activity_code == "455110"]
        self.assertEqual(len(dept_stores), 1)
        self.assertEqual(dept_stores[0].sector_total, Decimal("444512.39"))

    def test_unclassified_sector_included(self) -> None:
        unclassified = [r for r in self.report.records if r.sector == "UNCLASSIFIED"]
        self.assertEqual(len(unclassified), 1)
        self.assertIsNone(unclassified[0].activity_code)

    def test_totals_row_excluded(self) -> None:
        for record in self.report.records:
            self.assertNotEqual(record.copo, "")

    def test_invalid_month_raises(self) -> None:
        data = (FIXTURES_DIR / "naics_yukon_sales_2026_02.xls").read_bytes()
        with self.assertRaises(OkTAPParseError):
            parse_naics_export(data, "sales", 2026, 13)


if __name__ == "__main__":
    unittest.main()
