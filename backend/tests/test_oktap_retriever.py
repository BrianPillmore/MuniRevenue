"""Tests for OkTAP automated retrieval.

These tests hit the live OkTAP website. They are slow and should
only be run intentionally, not in CI.

Run with:
    cd backend && .venv/Scripts/python -m pytest tests/test_oktap_retriever.py -v -k "test_" --timeout=120
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from app.services.oktap_retriever import fetch_ledger, fetch_naics


@unittest.skipUnless(
    __name__ == "__main__",
    "Live OkTAP tests — run directly, not in CI",
)
class LiveLedgerRetrievalTests(unittest.TestCase):
    """Live tests against OkTAP. Only run manually."""

    def test_fetch_yukon_sales_2026(self) -> None:
        result = fetch_ledger("sales", 2026, copo="0955")
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.record_count, 0)
        self.assertIsNotNone(result.parsed_ledger)

        # Verify all records are Yukon
        for r in result.parsed_ledger.records:
            self.assertEqual(r.copo, "0955")

    def test_fetch_all_cities_sales_2026(self) -> None:
        result = fetch_ledger("sales", 2026, copo="")
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.record_count, 1000)  # Hundreds of cities

        # Multiple copo codes should be present
        copos = {r.copo for r in result.parsed_ledger.records}
        self.assertGreater(len(copos), 100)

    def test_fetch_counties_sales_2026(self) -> None:
        result = fetch_ledger("sales", 2026, copo="", city_or_county="County")
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.record_count, 0)


@unittest.skipUnless(
    __name__ == "__main__",
    "Live OkTAP tests — run directly, not in CI",
)
class LiveNaicsRetrievalTests(unittest.TestCase):
    """Live NAICS tests against OkTAP."""

    def test_fetch_yukon_naics_sales(self) -> None:
        result = fetch_naics("sales", 2026, 1, copo="0955")
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.record_count, 100)  # ~470 NAICS codes
        self.assertIsNotNone(result.parsed_naics)

    def test_fetch_all_cities_naics_sales(self) -> None:
        result = fetch_naics("sales", 2025, 12, copo="")
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.record_count, 10000)


if __name__ == "__main__":
    unittest.main()
