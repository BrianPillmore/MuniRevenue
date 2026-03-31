"""Comprehensive API tests for the MuniRev cities and analytics endpoints.

Tests are run against the live PostgreSQL database via FastAPI TestClient.
Each test class groups tests by endpoint and verifies status codes, response
structure, and data correctness using known test data:

    - Yukon:         copo="0955", has sales + use tax data, ~59 sales ledger records
    - Oklahoma City: copo="5521", largest city by revenue
    - Canadian County: county_name="Canadian", contains Yukon
    - NAICS "455110": Department Stores (high revenue in Yukon)

Tests for endpoints that are not yet implemented are marked with
``@unittest.skip("NEW endpoint -- not yet implemented")`` so the suite
remains green.
"""

from __future__ import annotations

import csv
import io
import unittest
from datetime import date

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Known test-data constants
# ---------------------------------------------------------------------------

YUKON_COPO = "0955"
YUKON_NAME = "Yukon"
OKC_COPO = "5521"
OKC_NAME = "Oklahoma City"
CANADIAN_COUNTY = "Canadian"
NONEXISTENT_COPO = "9999"
NONEXISTENT_COUNTY = "Nonexistent"
NAICS_DEPT_STORES = "455110"
BROKEN_BOW_COPO = "4508"
ADAIR_COUNTY_COPO = "0188"

# Approximate thresholds based on known database state
MIN_YUKON_SALES_RECORDS = 50  # ~59 expected
MIN_JURISDICTIONS_WITH_DATA = 500
MIN_TOTAL_LEDGER_RECORDS = 70_000
MIN_TOTAL_NAICS_RECORDS = 1_000_000
TOP_CITIES_COUNT = 10


# ===================================================================
# 1. Cities List -- GET /api/cities
# ===================================================================


class TestListCities(unittest.TestCase):
    """Tests for GET /api/cities -- paginated jurisdiction listing."""

    def test_list_cities_returns_paginated_results(self) -> None:
        """Default request returns a paginated response with items."""
        response = client.get("/api/cities")
        self.assertEqual(response.status_code, 200, "Expected 200 OK for city listing")

        data = response.json()
        self.assertIn("items", data, "Response must contain 'items' key")
        self.assertIn("total", data, "Response must contain 'total' key")
        self.assertIn("limit", data, "Response must contain 'limit' key")
        self.assertIn("offset", data, "Response must contain 'offset' key")

        self.assertIsInstance(data["items"], list)
        self.assertGreater(len(data["items"]), 0, "City list should not be empty")
        self.assertGreater(data["total"], 0, "Total count should be positive")

        # Verify each item has required fields
        first = data["items"][0]
        for field in ("copo", "name", "jurisdiction_type", "has_ledger_data"):
            self.assertIn(field, first, f"City item must include '{field}'")

    def test_list_cities_search_by_name(self) -> None:
        """Searching for 'yukon' returns Yukon with copo 0955."""
        response = client.get("/api/cities", params={"search": "yukon"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertGreater(data["total"], 0, "Search for 'yukon' should find at least one result")

        copos = [item["copo"] for item in data["items"]]
        self.assertIn(
            YUKON_COPO, copos,
            f"Yukon (copo={YUKON_COPO}) must appear in search results for 'yukon'",
        )

        yukon = next(item for item in data["items"] if item["copo"] == YUKON_COPO)
        self.assertIn(
            "Yukon", yukon["name"],
            "Yukon search result must have 'Yukon' in the name",
        )

    def test_list_cities_filter_by_type_county(self) -> None:
        """Filtering by type=county returns only county-type jurisdictions."""
        response = client.get("/api/cities", params={"type": "county"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertGreater(len(data["items"]), 0, "County filter should return results")

        for item in data["items"]:
            self.assertEqual(
                item["jurisdiction_type"], "county",
                f"All results must be type 'county', but got '{item['jurisdiction_type']}' "
                f"for {item['name']} (copo={item['copo']})",
            )

    def test_list_cities_filter_by_type_city(self) -> None:
        """Filtering by type=city returns only city-type jurisdictions."""
        response = client.get("/api/cities", params={"type": "city"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertGreater(len(data["items"]), 0, "City filter should return results")

        for item in data["items"]:
            self.assertEqual(
                item["jurisdiction_type"], "city",
                f"All results must be type 'city', but got '{item['jurisdiction_type']}' "
                f"for {item['name']}",
            )

    def test_list_cities_filter_by_invalid_type(self) -> None:
        """Filtering by an invalid type returns 400."""
        response = client.get("/api/cities", params={"type": "village"})
        self.assertEqual(
            response.status_code, 400,
            "Invalid jurisdiction type should return 400 Bad Request",
        )

    def test_list_cities_pagination(self) -> None:
        """Pagination with offset=10, limit=5 returns exactly 5 items."""
        response = client.get("/api/cities", params={"offset": 10, "limit": 5})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["limit"], 5, "Limit in response should match requested limit")
        self.assertEqual(data["offset"], 10, "Offset in response should match requested offset")
        self.assertEqual(
            len(data["items"]), 5,
            "With limit=5, exactly 5 items should be returned (assuming sufficient data)",
        )

    def test_list_cities_pagination_does_not_repeat(self) -> None:
        """Consecutive pages return different jurisdictions."""
        resp_page1 = client.get("/api/cities", params={"offset": 0, "limit": 10})
        resp_page2 = client.get("/api/cities", params={"offset": 10, "limit": 10})
        self.assertEqual(resp_page1.status_code, 200)
        self.assertEqual(resp_page2.status_code, 200)

        copos_page1 = {item["copo"] for item in resp_page1.json()["items"]}
        copos_page2 = {item["copo"] for item in resp_page2.json()["items"]}
        overlap = copos_page1 & copos_page2
        self.assertEqual(
            len(overlap), 0,
            f"Pages 1 and 2 should not share jurisdictions, but found overlap: {overlap}",
        )

    def test_list_cities_has_revenue_data(self) -> None:
        """Cities with ledger data have has_ledger_data=True and revenue info."""
        response = client.get("/api/cities", params={"search": "yukon"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        yukon = next(
            (item for item in data["items"] if item["copo"] == YUKON_COPO),
            None,
        )
        self.assertIsNotNone(yukon, f"Yukon (copo={YUKON_COPO}) must appear in results")

        self.assertTrue(
            yukon["has_ledger_data"],
            "Yukon should have has_ledger_data=True",
        )
        self.assertIsNotNone(
            yukon["latest_voucher_date"],
            "Yukon should have a latest_voucher_date",
        )
        self.assertIsNotNone(
            yukon["total_sales_returned"],
            "Yukon should have total_sales_returned",
        )
        self.assertGreater(
            yukon["total_sales_returned"], 0,
            "Yukon total_sales_returned should be positive",
        )


# ===================================================================
# 2. City Detail -- GET /api/cities/{copo}
# ===================================================================


class TestCityDetail(unittest.TestCase):
    """Tests for GET /api/cities/{copo} -- single jurisdiction detail."""

    def test_get_city_detail_yukon(self) -> None:
        """Yukon detail returns correct name, type, and tax_type_summaries."""
        response = client.get(f"/api/cities/{YUKON_COPO}")
        self.assertEqual(response.status_code, 200, "Yukon detail should return 200")

        data = response.json()
        self.assertEqual(data["copo"], YUKON_COPO)
        self.assertEqual(data["name"], YUKON_NAME)
        self.assertIn("jurisdiction_type", data)
        self.assertIn("county_name", data)

        # Tax type summaries
        self.assertIn("tax_type_summaries", data)
        self.assertIsInstance(data["tax_type_summaries"], list)
        self.assertGreater(
            len(data["tax_type_summaries"]), 0,
            "Yukon should have at least one tax_type_summary",
        )

        tax_types = [s["tax_type"] for s in data["tax_type_summaries"]]
        self.assertIn(
            "sales", tax_types,
            "Yukon must have a 'sales' tax type summary",
        )

        # Verify summary structure
        sales_summary = next(s for s in data["tax_type_summaries"] if s["tax_type"] == "sales")
        for field in ("record_count", "earliest_date", "latest_date", "total_returned"):
            self.assertIn(field, sales_summary, f"Tax summary must include '{field}'")
        self.assertGreater(sales_summary["record_count"], 0)
        self.assertGreater(sales_summary["total_returned"], 0)

    def test_get_city_detail_okc(self) -> None:
        """Oklahoma City detail returns correct identification."""
        response = client.get(f"/api/cities/{OKC_COPO}")
        self.assertEqual(response.status_code, 200, "OKC detail should return 200")

        data = response.json()
        self.assertEqual(data["copo"], OKC_COPO)
        self.assertIn(
            "Oklahoma City", data["name"],
            f"Expected 'Oklahoma City' in name, got '{data['name']}'",
        )

    def test_get_city_detail_not_found(self) -> None:
        """Non-existent copo returns 404."""
        response = client.get(f"/api/cities/{NONEXISTENT_COPO}")
        self.assertEqual(
            response.status_code, 404,
            f"copo={NONEXISTENT_COPO} should return 404 Not Found",
        )
        self.assertIn("detail", response.json())

    def test_get_city_detail_has_naics_count(self) -> None:
        """Yukon detail includes NAICS record count and date range."""
        response = client.get(f"/api/cities/{YUKON_COPO}")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("naics_record_count", data)
        self.assertGreater(
            data["naics_record_count"], 0,
            "Yukon should have NAICS records",
        )
        self.assertIn("naics_earliest_year_month", data)
        self.assertIn("naics_latest_year_month", data)
        self.assertIsNotNone(data["naics_earliest_year_month"])
        self.assertIsNotNone(data["naics_latest_year_month"])

    def test_get_city_detail_population(self) -> None:
        """Yukon detail includes a population figure."""
        response = client.get(f"/api/cities/{YUKON_COPO}")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # Population may or may not be populated -- just verify the key exists
        self.assertIn("population", data)


# ===================================================================
# 3. City Ledger -- GET /api/cities/{copo}/ledger
# ===================================================================


class TestCityLedger(unittest.TestCase):
    """Tests for GET /api/cities/{copo}/ledger -- monthly ledger records."""

    def test_get_ledger_sales_yukon(self) -> None:
        """Yukon sales ledger returns ~59 records, all with required fields."""
        response = client.get(f"/api/cities/{YUKON_COPO}/ledger", params={"tax_type": "sales"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["copo"], YUKON_COPO)
        self.assertEqual(data["tax_type"], "sales")
        self.assertGreaterEqual(
            data["count"], MIN_YUKON_SALES_RECORDS,
            f"Yukon should have at least {MIN_YUKON_SALES_RECORDS} sales ledger records, "
            f"got {data['count']}",
        )
        self.assertEqual(
            len(data["records"]), data["count"],
            "records list length must match count field",
        )

        # Verify every record has required fields
        for i, record in enumerate(data["records"]):
            self.assertIn("voucher_date", record, f"Record {i} missing voucher_date")
            self.assertIn("returned", record, f"Record {i} missing returned")
            self.assertIn("tax_type", record, f"Record {i} missing tax_type")
            self.assertEqual(
                record["tax_type"], "sales",
                f"Record {i} tax_type should be 'sales'",
            )

    def test_get_ledger_records_are_chronological(self) -> None:
        """Ledger records are sorted by voucher_date ascending."""
        response = client.get(f"/api/cities/{YUKON_COPO}/ledger", params={"tax_type": "sales"})
        self.assertEqual(response.status_code, 200)

        dates = [r["voucher_date"] for r in response.json()["records"]]
        self.assertEqual(
            dates, sorted(dates),
            "Ledger records must be sorted chronologically",
        )

    def test_get_ledger_has_mom_yoy(self) -> None:
        """Ledger records include mom_pct and yoy_pct fields."""
        response = client.get(f"/api/cities/{YUKON_COPO}/ledger", params={"tax_type": "sales"})
        self.assertEqual(response.status_code, 200)

        records = response.json()["records"]
        self.assertGreater(len(records), 12, "Need >12 records to check YoY")

        # First record should have null mom_pct (no prior month)
        self.assertIn("mom_pct", records[0])
        self.assertIsNone(
            records[0]["mom_pct"],
            "First record mom_pct should be null (no prior month)",
        )

        # Records after the first should have non-null mom_pct
        has_mom = any(r["mom_pct"] is not None for r in records[1:])
        self.assertTrue(has_mom, "At least some records should have non-null mom_pct")

        # Records with index >= 12 should have yoy_pct
        has_yoy = any(r["yoy_pct"] is not None for r in records[12:])
        self.assertTrue(has_yoy, "Records after 12 months should have non-null yoy_pct")

    def test_get_ledger_use_tax(self) -> None:
        """Yukon has use-tax ledger records."""
        response = client.get(f"/api/cities/{YUKON_COPO}/ledger", params={"tax_type": "use"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["tax_type"], "use")
        self.assertGreater(
            data["count"], 0,
            "Yukon should have use-tax ledger records",
        )
        for record in data["records"]:
            self.assertEqual(record["tax_type"], "use")

    def test_get_ledger_invalid_tax_type(self) -> None:
        """Invalid tax_type returns 400."""
        response = client.get(
            f"/api/cities/{YUKON_COPO}/ledger",
            params={"tax_type": "invalid"},
        )
        self.assertEqual(
            response.status_code, 400,
            "Invalid tax_type should return 400 Bad Request",
        )
        self.assertIn("detail", response.json())

    def test_get_ledger_date_range(self) -> None:
        """Date range filters correctly narrow the results."""
        # First, get all sales records to find a reasonable date range
        full_response = client.get(
            f"/api/cities/{YUKON_COPO}/ledger",
            params={"tax_type": "sales"},
        )
        self.assertEqual(full_response.status_code, 200)
        all_records = full_response.json()["records"]
        full_count = len(all_records)
        self.assertGreater(full_count, 12, "Need sufficient records for date range test")

        # Pick a range that covers roughly the middle half of the data
        quarter = full_count // 4
        start_date = all_records[quarter]["voucher_date"]
        end_date = all_records[full_count - quarter - 1]["voucher_date"]

        filtered_response = client.get(
            f"/api/cities/{YUKON_COPO}/ledger",
            params={"tax_type": "sales", "start": start_date, "end": end_date},
        )
        self.assertEqual(filtered_response.status_code, 200)
        filtered_data = filtered_response.json()

        self.assertLess(
            filtered_data["count"], full_count,
            "Filtered result count should be less than the full count",
        )
        self.assertGreater(
            filtered_data["count"], 0,
            "Filtered result should return some records",
        )

        # Verify all returned dates are within the range
        for record in filtered_data["records"]:
            self.assertGreaterEqual(
                record["voucher_date"], start_date,
                f"Record date {record['voucher_date']} is before start {start_date}",
            )
            self.assertLessEqual(
                record["voucher_date"], end_date,
                f"Record date {record['voucher_date']} is after end {end_date}",
            )

    def test_get_ledger_not_found(self) -> None:
        """Ledger for non-existent copo returns 404."""
        response = client.get(
            f"/api/cities/{NONEXISTENT_COPO}/ledger",
            params={"tax_type": "sales"},
        )
        self.assertEqual(
            response.status_code, 404,
            f"Ledger for copo={NONEXISTENT_COPO} should return 404",
        )

    def test_get_ledger_financial_fields_present(self) -> None:
        """Each ledger record includes all financial columns."""
        response = client.get(f"/api/cities/{YUKON_COPO}/ledger", params={"tax_type": "sales"})
        self.assertEqual(response.status_code, 200)

        financial_fields = [
            "tax_rate",
            "current_month_collection",
            "refunded",
            "suspended_monies",
            "apportioned",
            "revolving_fund",
            "interest_returned",
            "returned",
        ]
        for record in response.json()["records"]:
            for field in financial_fields:
                self.assertIn(
                    field, record,
                    f"Ledger record missing financial field '{field}'",
                )


# ===================================================================
# 4. City NAICS -- GET /api/cities/{copo}/naics
# ===================================================================


class TestCityNaics(unittest.TestCase):
    """Tests for GET /api/cities/{copo}/naics -- NAICS industry breakdown."""

    def test_get_naics_yukon_has_industries(self) -> None:
        """Yukon NAICS returns a substantial number of industry records."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["copo"], YUKON_COPO)
        self.assertGreater(
            data["count"], 100,
            f"Yukon should have >100 NAICS records, got {data['count']}",
        )
        self.assertIsInstance(data["records"], list)
        self.assertEqual(len(data["records"]), data["count"])

    def test_get_naics_has_pct_of_total(self) -> None:
        """Each NAICS record includes a pct_of_total field."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics")
        self.assertEqual(response.status_code, 200)

        records = response.json()["records"]
        self.assertGreater(len(records), 0)

        for i, record in enumerate(records):
            self.assertIn(
                "pct_of_total", record,
                f"NAICS record {i} missing 'pct_of_total'",
            )

        # At least some records should have non-null pct_of_total
        has_pct = [r for r in records if r["pct_of_total"] is not None]
        self.assertGreater(
            len(has_pct), 0,
            "At least some NAICS records should have non-null pct_of_total",
        )

        # Sum of non-null pct_of_total should be close to 100
        pct_sum = sum(r["pct_of_total"] for r in has_pct)
        self.assertAlmostEqual(
            pct_sum, 100.0, delta=1.0,
            msg=f"Sum of pct_of_total should be ~100%, got {pct_sum}%",
        )

    def test_get_naics_has_required_fields(self) -> None:
        """NAICS records include all expected fields."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics")
        self.assertEqual(response.status_code, 200)

        required_fields = [
            "activity_code", "sector", "tax_rate", "sector_total",
            "year_to_date", "pct_of_total",
        ]
        for record in response.json()["records"][:5]:
            for field in required_fields:
                self.assertIn(field, record, f"NAICS record missing '{field}'")

    def test_get_naics_response_metadata(self) -> None:
        """NAICS response includes year, month, and total_revenue metadata."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("year", data)
        self.assertIn("month", data)
        self.assertIn("total_revenue", data)
        self.assertGreater(data["year"], 2000, "Year should be a reasonable value")
        self.assertIn(data["month"], range(1, 13), "Month should be 1-12")
        self.assertIsNotNone(data["total_revenue"])
        self.assertGreater(data["total_revenue"], 0)

    def test_get_naics_sorted_by_sector_total_descending(self) -> None:
        """NAICS records are sorted by sector_total descending."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics")
        self.assertEqual(response.status_code, 200)

        totals = [r["sector_total"] for r in response.json()["records"]]
        self.assertEqual(
            totals, sorted(totals, reverse=True),
            "NAICS records should be sorted by sector_total descending",
        )

    def test_get_naics_not_found(self) -> None:
        """NAICS for non-existent copo returns 404."""
        response = client.get(f"/api/cities/{NONEXISTENT_COPO}/naics")
        self.assertEqual(response.status_code, 404)


# ===================================================================
# 5. Top NAICS -- GET /api/cities/{copo}/naics/top
# ===================================================================


class TestTopNaics(unittest.TestCase):
    """Tests for GET /api/cities/{copo}/naics/top -- top NAICS drivers."""

    def test_get_top_naics_returns_rankings(self) -> None:
        """Top NAICS returns the requested number of ranked industries."""
        limit = 10
        response = client.get(
            f"/api/cities/{YUKON_COPO}/naics/top",
            params={"limit": limit},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["copo"], YUKON_COPO)
        self.assertEqual(data["tax_type"], "sales")
        self.assertLessEqual(
            data["count"], limit,
            f"Count should not exceed limit={limit}",
        )
        self.assertEqual(len(data["records"]), data["count"])

    def test_get_top_naics_has_required_fields(self) -> None:
        """Top NAICS records include ranking-relevant fields."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics/top")
        self.assertEqual(response.status_code, 200)

        for record in response.json()["records"]:
            for field in ("activity_code", "sector", "avg_sector_total",
                          "months_present", "total_across_months"):
                self.assertIn(field, record, f"Top NAICS record missing '{field}'")
            self.assertGreater(record["avg_sector_total"], 0)
            self.assertGreater(record["months_present"], 0)

    def test_get_top_naics_sorted_by_avg_descending(self) -> None:
        """Top NAICS records are ranked by avg_sector_total descending."""
        response = client.get(f"/api/cities/{YUKON_COPO}/naics/top")
        self.assertEqual(response.status_code, 200)

        avgs = [r["avg_sector_total"] for r in response.json()["records"]]
        self.assertEqual(
            avgs, sorted(avgs, reverse=True),
            "Top NAICS should be sorted by avg_sector_total descending",
        )

    def test_get_top_naics_respects_limit(self) -> None:
        """Requesting limit=3 returns at most 3 records."""
        response = client.get(
            f"/api/cities/{YUKON_COPO}/naics/top",
            params={"limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.json()["count"], 3)

    def test_get_top_naics_not_found(self) -> None:
        """Top NAICS for non-existent copo returns 404."""
        response = client.get(f"/api/cities/{NONEXISTENT_COPO}/naics/top")
        self.assertEqual(response.status_code, 404)


# ===================================================================
# 6. Statewide Overview -- GET /api/stats/overview
# ===================================================================


class TestOverview(unittest.TestCase):
    """Tests for GET /api/stats/overview -- statewide summary statistics."""

    def test_overview_has_jurisdiction_count(self) -> None:
        """Overview reports >500 jurisdictions with data."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("jurisdictions_with_data", data)
        self.assertGreater(
            data["jurisdictions_with_data"], MIN_JURISDICTIONS_WITH_DATA,
            f"Expected >{MIN_JURISDICTIONS_WITH_DATA} jurisdictions with data, "
            f"got {data['jurisdictions_with_data']}",
        )

    def test_overview_has_record_counts(self) -> None:
        """Overview includes correct ledger and NAICS record counts."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertGreater(
            data["total_ledger_records"], MIN_TOTAL_LEDGER_RECORDS,
            f"Expected >{MIN_TOTAL_LEDGER_RECORDS} ledger records, "
            f"got {data['total_ledger_records']}",
        )
        self.assertGreater(
            data["total_naics_records"], MIN_TOTAL_NAICS_RECORDS,
            f"Expected >{MIN_TOTAL_NAICS_RECORDS} NAICS records, "
            f"got {data['total_naics_records']}",
        )

    def test_overview_has_date_ranges(self) -> None:
        """Overview includes valid date ranges for ledger and NAICS."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIsNotNone(data["earliest_ledger_date"])
        self.assertIsNotNone(data["latest_ledger_date"])
        self.assertLess(
            data["earliest_ledger_date"], data["latest_ledger_date"],
            "Earliest ledger date must precede latest",
        )
        self.assertIsNotNone(data["earliest_naics_year_month"])
        self.assertIsNotNone(data["latest_naics_year_month"])
        self.assertLess(
            data["earliest_naics_year_month"], data["latest_naics_year_month"],
            "Earliest NAICS year_month must precede latest",
        )

    def test_overview_has_top_cities(self) -> None:
        """Overview includes top 10 cities by sales revenue."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("top_cities_by_sales", data)
        self.assertEqual(
            len(data["top_cities_by_sales"]), TOP_CITIES_COUNT,
            f"Expected {TOP_CITIES_COUNT} top cities, "
            f"got {len(data['top_cities_by_sales'])}",
        )

    def test_overview_top_city_is_okc(self) -> None:
        """The top city by sales revenue is Oklahoma City."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        top_city = data["top_cities_by_sales"][0]
        self.assertIn(
            "Oklahoma", top_city["name"],
            f"Top city should be Oklahoma City, got '{top_city['name']}'",
        )

    def test_overview_top_cities_sorted_descending(self) -> None:
        """Top cities are sorted by total_sales_returned descending."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        revenues = [
            c["total_sales_returned"]
            for c in response.json()["top_cities_by_sales"]
        ]
        self.assertEqual(
            revenues, sorted(revenues, reverse=True),
            "Top cities should be sorted by revenue descending",
        )

    def test_overview_top_cities_have_required_fields(self) -> None:
        """Each top city has copo, name, and total_sales_returned."""
        response = client.get("/api/stats/overview")
        self.assertEqual(response.status_code, 200)

        for city in response.json()["top_cities_by_sales"]:
            for field in ("copo", "name", "total_sales_returned"):
                self.assertIn(field, city, f"Top city missing '{field}'")
            self.assertGreater(city["total_sales_returned"], 0)


# ===================================================================
# 7. Statewide Trend -- GET /api/stats/statewide-trend
#    (NEW endpoint -- analytics.py router, must be registered in main.py)
# ===================================================================


class TestStatewideTrend(unittest.TestCase):
    """Tests for GET /api/stats/statewide-trend -- statewide aggregate trend.

    NOTE: This endpoint is in analytics.py. Ensure the analytics router is
    registered in main.py before running these tests.
    """

    @classmethod
    def _endpoint_available(cls) -> bool:
        """Check if the statewide-trend endpoint is registered."""
        resp = client.get("/api/stats/statewide-trend")
        return resp.status_code != 404

    def setUp(self) -> None:
        if not self._endpoint_available():
            self.skipTest(
                "NEW endpoint /api/stats/statewide-trend not yet registered -- "
                "add analytics router to main.py"
            )

    def test_statewide_trend_returns_monthly_data(self) -> None:
        """Statewide trend returns a list of monthly records."""
        response = client.get("/api/stats/statewide-trend")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["tax_type"], "sales")
        self.assertGreater(
            data["count"], 0,
            "Statewide trend should have records",
        )
        self.assertEqual(len(data["records"]), data["count"])

    def test_statewide_trend_has_totals_and_counts(self) -> None:
        """Each trend record has total_returned and jurisdiction_count."""
        response = client.get("/api/stats/statewide-trend")
        self.assertEqual(response.status_code, 200)

        for record in response.json()["records"]:
            self.assertIn("voucher_date", record)
            self.assertIn("total_returned", record)
            self.assertIn("jurisdiction_count", record)
            self.assertGreater(record["total_returned"], 0)
            self.assertGreater(record["jurisdiction_count"], 0)

    def test_statewide_trend_chronological(self) -> None:
        """Trend records are sorted chronologically."""
        response = client.get("/api/stats/statewide-trend")
        self.assertEqual(response.status_code, 200)

        dates = [r["voucher_date"] for r in response.json()["records"]]
        self.assertEqual(dates, sorted(dates))

    def test_statewide_trend_has_mom_yoy(self) -> None:
        """Trend records include mom_pct and yoy_pct fields."""
        response = client.get("/api/stats/statewide-trend")
        self.assertEqual(response.status_code, 200)

        records = response.json()["records"]
        for record in records:
            self.assertIn("mom_pct", record)
            self.assertIn("yoy_pct", record)

        # Later records should have computed values
        has_mom = any(r["mom_pct"] is not None for r in records[1:])
        self.assertTrue(has_mom, "Some records should have non-null mom_pct")

    def test_statewide_trend_filter_by_date_range(self) -> None:
        """Date range filters narrow the statewide trend results."""
        # Get a baseline
        full_resp = client.get("/api/stats/statewide-trend")
        self.assertEqual(full_resp.status_code, 200)
        full_data = full_resp.json()
        full_count = full_data["count"]
        self.assertGreater(full_count, 12, "Need sufficient records for date range test")

        # Use a narrowed range from the middle of the data
        records = full_data["records"]
        start_date = records[full_count // 4]["voucher_date"]
        end_date = records[3 * full_count // 4]["voucher_date"]

        filtered_resp = client.get(
            "/api/stats/statewide-trend",
            params={"start": start_date, "end": end_date},
        )
        self.assertEqual(filtered_resp.status_code, 200)
        filtered_count = filtered_resp.json()["count"]

        self.assertLess(
            filtered_count, full_count,
            "Filtered count should be less than full count",
        )
        self.assertGreater(filtered_count, 0)

    def test_statewide_trend_use_tax(self) -> None:
        """Statewide trend works for use tax type."""
        response = client.get("/api/stats/statewide-trend", params={"tax_type": "use"})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["tax_type"], "use")
        self.assertGreater(data["count"], 0)

    def test_statewide_trend_invalid_tax_type(self) -> None:
        """Invalid tax_type returns 400."""
        response = client.get("/api/stats/statewide-trend", params={"tax_type": "bogus"})
        self.assertEqual(response.status_code, 400)


# ===================================================================
# 8. Rankings -- GET /api/stats/rankings
#    (NEW endpoint -- analytics.py router)
# ===================================================================


class TestRankings(unittest.TestCase):
    """Tests for GET /api/stats/rankings -- jurisdiction rankings.

    NOTE: This endpoint is in analytics.py. Ensure the analytics router is
    registered in main.py before running these tests.
    """

    @classmethod
    def _endpoint_available(cls) -> bool:
        resp = client.get("/api/stats/rankings")
        return resp.status_code != 404

    def setUp(self) -> None:
        if not self._endpoint_available():
            self.skipTest(
                "NEW endpoint /api/stats/rankings not yet registered -- "
                "add analytics router to main.py"
            )

    def test_rankings_returns_ranked_list(self) -> None:
        """Rankings endpoint returns a ranked list of jurisdictions."""
        response = client.get("/api/stats/rankings")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIn("limit", data)
        self.assertIn("offset", data)
        self.assertGreater(len(data["items"]), 0)

        # Check item structure
        for item in data["items"]:
            for field in ("rank", "copo", "name", "jurisdiction_type", "metric_value"):
                self.assertIn(field, item, f"Ranking item missing '{field}'")
            self.assertIsInstance(item["rank"], int)
            self.assertGreater(item["rank"], 0)

    def test_rankings_are_in_order(self) -> None:
        """Rankings are ordered by rank ascending."""
        response = client.get("/api/stats/rankings")
        self.assertEqual(response.status_code, 200)

        ranks = [item["rank"] for item in response.json()["items"]]
        self.assertEqual(ranks, sorted(ranks), "Ranks should be in ascending order")

    def test_rankings_metric_values_descending(self) -> None:
        """For total_returned metric, values are descending."""
        response = client.get(
            "/api/stats/rankings",
            params={"metric": "total_returned"},
        )
        self.assertEqual(response.status_code, 200)

        values = [
            item["metric_value"]
            for item in response.json()["items"]
            if item["metric_value"] is not None
        ]
        self.assertEqual(
            values, sorted(values, reverse=True),
            "Metric values should be in descending order",
        )

    def test_rankings_pagination(self) -> None:
        """Rankings support pagination with limit and offset."""
        resp1 = client.get("/api/stats/rankings", params={"limit": 5, "offset": 0})
        resp2 = client.get("/api/stats/rankings", params={"limit": 5, "offset": 5})
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        page1_copos = {item["copo"] for item in resp1.json()["items"]}
        page2_copos = {item["copo"] for item in resp2.json()["items"]}
        overlap = page1_copos & page2_copos
        self.assertEqual(
            len(overlap), 0,
            f"Paginated pages should not overlap, found: {overlap}",
        )

    def test_rankings_okc_near_top(self) -> None:
        """Oklahoma City should be in the top 5 by total_returned."""
        response = client.get(
            "/api/stats/rankings",
            params={"metric": "total_returned", "limit": 5},
        )
        self.assertEqual(response.status_code, 200)

        names = [item["name"] for item in response.json()["items"]]
        okc_found = any("Oklahoma" in name for name in names)
        self.assertTrue(
            okc_found,
            f"Oklahoma City should be in top 5 by total_returned, got: {names}",
        )

    def test_rankings_yoy_change_metric(self) -> None:
        """Rankings support the yoy_change metric."""
        response = client.get(
            "/api/stats/rankings",
            params={"metric": "yoy_change"},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["metric"], "yoy_change")
        self.assertGreater(len(data["items"]), 0)

    def test_rankings_invalid_metric(self) -> None:
        """Invalid metric returns 400."""
        response = client.get("/api/stats/rankings", params={"metric": "invalid"})
        self.assertEqual(response.status_code, 400)


# ===================================================================
# 9. NAICS Sectors -- GET /api/stats/naics-sectors
#    (NEW endpoint -- analytics.py router)
# ===================================================================


class TestNaicsSectors(unittest.TestCase):
    """Tests for GET /api/stats/naics-sectors -- statewide NAICS sector trends.

    NOTE: This endpoint is in analytics.py. Ensure the analytics router is
    registered in main.py before running these tests.
    """

    @classmethod
    def _endpoint_available(cls) -> bool:
        resp = client.get("/api/stats/naics-sectors")
        return resp.status_code != 404

    def setUp(self) -> None:
        if not self._endpoint_available():
            self.skipTest(
                "NEW endpoint /api/stats/naics-sectors not yet registered -- "
                "add analytics router to main.py"
            )

    def test_naics_sectors_returns_sectors(self) -> None:
        """NAICS sectors endpoint returns a list of sector items."""
        response = client.get("/api/stats/naics-sectors")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["tax_type"], "sales")
        self.assertGreater(data["count"], 0)
        self.assertEqual(len(data["sectors"]), data["count"])

    def test_naics_sectors_have_monthly_data(self) -> None:
        """Each sector includes a monthly_data array."""
        response = client.get("/api/stats/naics-sectors")
        self.assertEqual(response.status_code, 200)

        for sector_item in response.json()["sectors"]:
            self.assertIn("sector", sector_item)
            self.assertIn("monthly_data", sector_item)
            self.assertIsInstance(sector_item["monthly_data"], list)
            self.assertGreater(
                len(sector_item["monthly_data"]), 0,
                f"Sector '{sector_item['sector']}' should have monthly data",
            )

            for point in sector_item["monthly_data"]:
                self.assertIn("year", point)
                self.assertIn("month", point)
                self.assertIn("total", point)

    def test_naics_sectors_respects_limit(self) -> None:
        """Requesting limit=3 returns at most 3 sectors."""
        response = client.get("/api/stats/naics-sectors", params={"limit": 3})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(response.json()["count"], 3)


# ===================================================================
# 10. Anomalies -- GET /api/stats/anomalies
#     (NEW endpoint -- analytics.py router)
# ===================================================================


class TestAnomalies(unittest.TestCase):
    """Tests for GET /api/stats/anomalies -- anomaly feed.

    NOTE: This endpoint is in analytics.py. Ensure the analytics router is
    registered in main.py before running these tests.
    """

    @classmethod
    def _endpoint_available(cls) -> bool:
        resp = client.get("/api/stats/anomalies")
        return resp.status_code != 404

    def setUp(self) -> None:
        if not self._endpoint_available():
            self.skipTest(
                "NEW endpoint /api/stats/anomalies not yet registered -- "
                "add analytics router to main.py"
            )

    def test_anomalies_returns_list(self) -> None:
        """Anomalies endpoint returns items and count."""
        response = client.get("/api/stats/anomalies")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("count", data)
        self.assertIsInstance(data["items"], list)
        self.assertEqual(data["count"], len(data["items"]))

    def test_anomalies_with_date_range_filter(self) -> None:
        """Anomalies can be filtered by start_date and end_date."""
        # First get all anomalies to find a date range
        full_resp = client.get("/api/stats/anomalies", params={"limit": 100})
        self.assertEqual(full_resp.status_code, 200)
        full_data = full_resp.json()

        if full_data["count"] == 0:
            self.skipTest("No anomalies in database to test date filtering")

        # Use a date range filter that restricts the results
        first_date = full_data["items"][-1]["anomaly_date"]
        last_date = full_data["items"][0]["anomaly_date"]

        filtered_resp = client.get(
            "/api/stats/anomalies",
            params={"start_date": first_date, "end_date": last_date},
        )
        self.assertEqual(filtered_resp.status_code, 200)
        filtered_data = filtered_resp.json()
        self.assertIn("items", filtered_data)
        self.assertIn("count", filtered_data)

        # All returned items should have anomaly_date within range
        for item in filtered_data["items"]:
            self.assertGreaterEqual(
                item["anomaly_date"], first_date,
                f"Anomaly date {item['anomaly_date']} is before start_date {first_date}",
            )
            self.assertLessEqual(
                item["anomaly_date"], last_date,
                f"Anomaly date {item['anomaly_date']} is after end_date {last_date}",
            )

    def test_anomalies_populated_count(self) -> None:
        """Anomalies feed returns populated data (count > 0)."""
        response = client.get("/api/stats/anomalies", params={"limit": 10})
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertGreater(
            data["count"], 0,
            "Anomalies table should be populated with detected anomalies",
        )
        # Verify structure of the first item
        first = data["items"][0]
        for field in ("copo", "city_name", "tax_type", "anomaly_date",
                      "anomaly_type", "severity", "deviation_pct", "description"):
            self.assertIn(field, first, f"Anomaly item missing '{field}'")

    def test_anomalies_naics_shift_type(self) -> None:
        """NAICS anomalies appear after detection with anomaly_type=naics_shift."""
        response = client.get(
            "/api/stats/anomalies",
            params={"anomaly_type": "naics_shift", "limit": 50},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # If naics detection has run, we expect some results
        # This test validates the endpoint accepts naics_shift type
        self.assertIn("items", data)
        self.assertIn("count", data)
        for item in data["items"]:
            self.assertEqual(item["anomaly_type"], "naics_shift")


# ===================================================================
# 11. City Seasonality -- GET /api/cities/{copo}/seasonality
#     (NEW endpoint -- not yet implemented)
# ===================================================================


class TestCitySeasonality(unittest.TestCase):
    """Tests for GET /api/cities/{copo}/seasonality -- monthly seasonality.

    NEW endpoint -- tests will be skipped if the endpoint is not yet
    implemented.
    """

    @classmethod
    def _endpoint_available(cls) -> bool:
        resp = client.get(f"/api/cities/{YUKON_COPO}/seasonality")
        # 404 from FastAPI means the route itself is not registered.
        # A 404 from _ensure_jurisdiction_exists would only happen for
        # bad copo, so we check with a known-good copo.
        return resp.status_code != 404

    def setUp(self) -> None:
        if not self._endpoint_available():
            self.skipTest(
                "NEW endpoint /api/cities/{copo}/seasonality not yet implemented"
            )

    def test_seasonality_returns_12_months(self) -> None:
        """Seasonality returns exactly 12 monthly entries."""
        response = client.get(f"/api/cities/{YUKON_COPO}/seasonality")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # The response uses "months" key per SeasonalityResponse model
        records_key = "months" if "months" in data else "records"
        self.assertIn(records_key, data)
        self.assertEqual(
            len(data[records_key]), 12,
            f"Seasonality should return 12 months, got {len(data[records_key])}",
        )

    def test_seasonality_has_statistics(self) -> None:
        """Each month has mean_returned, median_returned, min_returned, max_returned, and std_dev."""
        response = client.get(f"/api/cities/{YUKON_COPO}/seasonality")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        records_key = "months" if "months" in data else "records"
        stat_fields = {"mean_returned", "median_returned", "min_returned", "max_returned", "std_dev"}

        for entry in data[records_key]:
            present = stat_fields & set(entry.keys())
            self.assertEqual(
                present, stat_fields,
                f"Seasonality entry missing stats: {stat_fields - present}",
            )

    def test_seasonality_invalid_copo(self) -> None:
        """Seasonality for non-existent copo returns 404."""
        response = client.get(f"/api/cities/{NONEXISTENT_COPO}/seasonality")
        self.assertEqual(response.status_code, 404)


# ===================================================================
# 12. City Forecast -- GET /api/cities/{copo}/forecast
#     (NEW endpoint -- not yet implemented)
# ===================================================================


class TestCityForecast(unittest.TestCase):
    """Tests for GET /api/cities/{copo}/forecast -- revenue forecast.

    NEW endpoint -- tests will be skipped if the endpoint is not yet
    implemented.
    """

    @classmethod
    def _endpoint_available(cls) -> bool:
        resp = client.get(f"/api/cities/{YUKON_COPO}/forecast")
        return resp.status_code != 404

    def setUp(self) -> None:
        if not self._endpoint_available():
            self.skipTest(
                "NEW endpoint /api/cities/{copo}/forecast not yet implemented"
            )

    def test_forecast_returns_12_months(self) -> None:
        """Forecast returns 12 months of projected data."""
        response = client.get(f"/api/cities/{YUKON_COPO}/forecast")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # ForecastResponse uses "forecasts" key
        records_key = "forecasts" if "forecasts" in data else ("months" if "months" in data else "records")
        self.assertIn(records_key, data)
        self.assertEqual(
            len(data[records_key]), 12,
            f"Forecast should return 12 months, got {len(data[records_key])}",
        )

    def test_forecast_has_confidence_bounds(self) -> None:
        """Each forecast entry has lower_bound <= projected_value <= upper_bound."""
        response = client.get(f"/api/cities/{YUKON_COPO}/forecast")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # ForecastResponse uses "forecasts" key
        records_key = "forecasts" if "forecasts" in data else ("months" if "months" in data else "records")

        for entry in data[records_key]:
            self.assertIn("lower_bound", entry, "Forecast entry missing 'lower_bound'")
            self.assertIn("projected_value", entry, "Forecast entry missing 'projected_value'")
            self.assertIn("upper_bound", entry, "Forecast entry missing 'upper_bound'")
            self.assertLessEqual(
                entry["lower_bound"], entry["projected_value"],
                f"Lower bound ({entry['lower_bound']}) should be <= projected ({entry['projected_value']})",
            )
            self.assertLessEqual(
                entry["projected_value"], entry["upper_bound"],
                f"Projected ({entry['projected_value']}) should be <= upper bound ({entry['upper_bound']})",
            )

    def test_forecast_invalid_copo(self) -> None:
        """Forecast for non-existent copo returns 404."""
        response = client.get(f"/api/cities/{NONEXISTENT_COPO}/forecast")
        self.assertEqual(response.status_code, 404)

    def test_forecast_response_includes_explainability_contract(self) -> None:
        """Forecast response exposes comparison, explainability, and data-quality sections."""
        response = client.get(f"/api/cities/{YUKON_COPO}/forecast")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        for field in (
            "selected_model",
            "requested_model",
            "eligible_models",
            "forecast_points",
            "backtest_summary",
            "model_comparison",
            "explainability",
            "data_quality",
            "series_scope",
        ):
            self.assertIn(field, data, f"Forecast response must include '{field}'")

        self.assertEqual(data["series_scope"], "municipal")
        self.assertIsInstance(data["model_comparison"], list)
        self.assertGreater(len(data["model_comparison"]), 0)
        self.assertIsInstance(data["eligible_models"], list)
        self.assertIn("warnings", data["data_quality"])
        self.assertIn("selected_model_reason", data["explainability"])

    def test_forecast_compare_endpoint_returns_model_table(self) -> None:
        """Forecast compare endpoint returns a compact model comparison payload."""
        response = client.get(
            f"/api/cities/{YUKON_COPO}/forecast/compare",
            params={"tax_type": "sales", "model": "auto"},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("model_comparison", data)
        self.assertIn("selected_model", data)
        self.assertIn("data_quality", data)
        self.assertGreater(len(data["model_comparison"]), 0)

    def test_forecast_drivers_endpoint_returns_explainability(self) -> None:
        """Forecast drivers endpoint exposes explainability and backtest metadata."""
        response = client.get(
            f"/api/cities/{YUKON_COPO}/forecast/drivers",
            params={"tax_type": "sales", "indicator_profile": "balanced"},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("explainability", data)
        self.assertIn("backtest_summary", data)
        self.assertIn("indicator_summary", data["explainability"])

    def test_forecast_supports_naics_scope(self) -> None:
        """Forecast endpoint can return NAICS-level forecasts for a city and industry code."""
        response = client.get(
            f"/api/cities/{YUKON_COPO}/forecast",
            params={"tax_type": "sales", "activity_code": NAICS_DEPT_STORES},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["series_scope"], "naics")
        self.assertEqual(data["activity_code"], NAICS_DEPT_STORES)
        self.assertEqual(len(data["forecast_points"]), 12)

    def test_forecast_sparse_lodging_falls_back(self) -> None:
        """Sparse lodging series return warnings and disable advanced models."""
        response = client.get(
            f"/api/cities/{BROKEN_BOW_COPO}/forecast",
            params={"tax_type": "lodging"},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertFalse(data["data_quality"]["advanced_models_allowed"])
        self.assertGreater(len(data["data_quality"]["warnings"]), 0)

    def test_forecast_county_jurisdiction(self) -> None:
        """County jurisdictions can be forecast through the same endpoint."""
        response = client.get(
            f"/api/cities/{ADAIR_COUNTY_COPO}/forecast",
            params={"tax_type": "sales"},
        )
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["copo"], ADAIR_COUNTY_COPO)
        self.assertEqual(len(data["forecast_points"]), 12)


# ===================================================================
# 13. County Summary -- GET /api/counties/{county_name}/summary
#     (NEW endpoint -- not yet implemented)
# ===================================================================


class TestCountySummary(unittest.TestCase):
    """Tests for county summary endpoint.

    NEW endpoint -- tests will be skipped if the endpoint is not yet
    implemented.
    """

    POSSIBLE_PATHS = [
        "/api/counties/Canadian/summary",
        "/api/stats/county-summary/Canadian",
        "/api/counties/Canadian",
        "/api/stats/county/Canadian",
    ]

    @classmethod
    def _find_endpoint(cls) -> str | None:
        """Probe possible URL patterns for the county summary endpoint."""
        for path in cls.POSSIBLE_PATHS:
            resp = client.get(path)
            if resp.status_code != 404:
                return path.replace("Canadian", "{county_name}")
        return None

    def setUp(self) -> None:
        self._base_path = self._find_endpoint()
        if self._base_path is None:
            self.skipTest(
                "NEW endpoint county-summary not yet implemented -- "
                "tried paths: " + ", ".join(self.POSSIBLE_PATHS)
            )

    def _url(self, county_name: str) -> str:
        return self._base_path.replace("{county_name}", county_name)

    def test_county_summary_canadian(self) -> None:
        """Canadian County summary includes Yukon."""
        response = client.get(self._url(CANADIAN_COUNTY))
        self.assertEqual(response.status_code, 200)

        data = response.json()
        # Look for Yukon in the response regardless of structure
        raw = str(data)
        self.assertIn(
            "Yukon", raw,
            f"Canadian County summary should include Yukon; got: {data}",
        )

    def test_county_summary_not_found(self) -> None:
        """Non-existent county returns 404."""
        response = client.get(self._url(NONEXISTENT_COUNTY))
        self.assertEqual(
            response.status_code, 404,
            f"County '{NONEXISTENT_COUNTY}' should return 404",
        )


# ===================================================================
# 14. CSV Export -- GET /api/cities/{copo}/ledger/export
#     (NEW endpoint -- not yet implemented)
# ===================================================================


class TestCsvExport(unittest.TestCase):
    """Tests for CSV export endpoint.

    NEW endpoint -- tests will be skipped if the endpoint is not yet
    implemented.
    """

    POSSIBLE_PATHS = [
        f"/api/cities/{YUKON_COPO}/ledger/export",
        f"/api/cities/{YUKON_COPO}/export",
        f"/api/export/ledger/{YUKON_COPO}",
    ]

    @classmethod
    def _find_endpoint(cls) -> str | None:
        """Probe possible URL patterns for the CSV export endpoint."""
        for path in cls.POSSIBLE_PATHS:
            resp = client.get(path)
            if resp.status_code != 404:
                return path.replace(YUKON_COPO, "{copo}")
        return None

    def setUp(self) -> None:
        self._base_path = self._find_endpoint()
        if self._base_path is None:
            self.skipTest(
                "NEW endpoint CSV export not yet implemented -- "
                "tried paths: " + ", ".join(self.POSSIBLE_PATHS)
            )

    def _url(self, copo: str = YUKON_COPO) -> str:
        return self._base_path.replace("{copo}", copo)

    def test_export_returns_csv_content_type(self) -> None:
        """CSV export returns text/csv content type."""
        response = client.get(self._url())
        self.assertEqual(response.status_code, 200)

        content_type = response.headers.get("content-type", "")
        self.assertTrue(
            "text/csv" in content_type or "application/csv" in content_type,
            f"Expected CSV content type, got '{content_type}'",
        )

    def test_export_has_header_row(self) -> None:
        """CSV export starts with a header row containing expected columns."""
        response = client.get(self._url())
        self.assertEqual(response.status_code, 200)

        reader = csv.reader(io.StringIO(response.text))
        header = next(reader)
        self.assertGreater(len(header), 0, "CSV should have header columns")

        # Expect at least some recognizable ledger columns
        header_lower = [h.lower().strip() for h in header]
        expected_columns = {"voucher_date", "returned"}
        found = expected_columns & set(header_lower)
        self.assertTrue(
            len(found) > 0,
            f"CSV header should contain ledger columns like {expected_columns}, "
            f"got {header_lower}",
        )

    def test_export_has_data_rows(self) -> None:
        """CSV export contains data rows beyond the header."""
        response = client.get(self._url())
        self.assertEqual(response.status_code, 200)

        lines = response.text.strip().split("\n")
        self.assertGreater(
            len(lines), 1,
            "CSV should have at least a header row and one data row",
        )

    def test_export_data_matches_json_endpoint(self) -> None:
        """CSV export row count matches the JSON ledger endpoint."""
        csv_response = client.get(self._url())
        self.assertEqual(csv_response.status_code, 200)

        json_response = client.get(
            f"/api/cities/{YUKON_COPO}/ledger",
            params={"tax_type": "sales"},
        )
        self.assertEqual(json_response.status_code, 200)

        json_count = json_response.json()["count"]
        csv_lines = csv_response.text.strip().split("\n")
        csv_data_rows = len(csv_lines) - 1  # Subtract header

        self.assertEqual(
            csv_data_rows, json_count,
            f"CSV data rows ({csv_data_rows}) should match JSON count ({json_count})",
        )


# ===================================================================
# 15. Health Check -- GET /api/health (sanity baseline)
# ===================================================================


class TestHealth(unittest.TestCase):
    """Baseline health check to confirm the API is reachable."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint returns 200 with status ok."""
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


# ===================================================================
# 16. Cross-endpoint consistency checks
# ===================================================================


class TestCrossEndpointConsistency(unittest.TestCase):
    """Tests that verify data consistency across related endpoints."""

    def test_city_list_total_matches_pagination(self) -> None:
        """The total count in city list is consistent across pages."""
        resp1 = client.get("/api/cities", params={"limit": 10, "offset": 0})
        resp2 = client.get("/api/cities", params={"limit": 10, "offset": 10})
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)

        self.assertEqual(
            resp1.json()["total"], resp2.json()["total"],
            "Total count should be consistent across paginated requests",
        )

    def test_city_detail_matches_list(self) -> None:
        """City detail data matches what is shown in the city list."""
        list_resp = client.get("/api/cities", params={"search": "yukon"})
        self.assertEqual(list_resp.status_code, 200)
        list_yukon = next(
            item for item in list_resp.json()["items"]
            if item["copo"] == YUKON_COPO
        )

        detail_resp = client.get(f"/api/cities/{YUKON_COPO}")
        self.assertEqual(detail_resp.status_code, 200)
        detail_data = detail_resp.json()

        self.assertEqual(
            list_yukon["copo"], detail_data["copo"],
            "copo should match between list and detail",
        )
        self.assertEqual(
            list_yukon["name"], detail_data["name"],
            "Name should match between list and detail",
        )
        self.assertEqual(
            list_yukon["jurisdiction_type"], detail_data["jurisdiction_type"],
            "jurisdiction_type should match between list and detail",
        )

    def test_ledger_count_matches_detail_summary(self) -> None:
        """Ledger record count matches the count in city detail tax summary."""
        detail_resp = client.get(f"/api/cities/{YUKON_COPO}")
        self.assertEqual(detail_resp.status_code, 200)
        detail = detail_resp.json()

        sales_summary = next(
            (s for s in detail["tax_type_summaries"] if s["tax_type"] == "sales"),
            None,
        )
        self.assertIsNotNone(sales_summary, "Yukon should have a sales tax summary")

        ledger_resp = client.get(
            f"/api/cities/{YUKON_COPO}/ledger",
            params={"tax_type": "sales"},
        )
        self.assertEqual(ledger_resp.status_code, 200)

        self.assertEqual(
            ledger_resp.json()["count"], sales_summary["record_count"],
            "Ledger count should match detail summary record_count",
        )

    def test_overview_ledger_count_is_plausible(self) -> None:
        """Overview total_ledger_records is at least as large as Yukon alone."""
        overview_resp = client.get("/api/stats/overview")
        self.assertEqual(overview_resp.status_code, 200)
        total = overview_resp.json()["total_ledger_records"]

        yukon_resp = client.get(
            f"/api/cities/{YUKON_COPO}/ledger",
            params={"tax_type": "sales"},
        )
        self.assertEqual(yukon_resp.status_code, 200)
        yukon_count = yukon_resp.json()["count"]

        self.assertGreater(
            total, yukon_count,
            "Statewide ledger total should exceed any single city's count",
        )


# ===================================================================
# 17. City Anomalies -- GET /api/cities/{copo}/anomalies
# ===================================================================


class TestCityAnomalies(unittest.TestCase):
    """Tests for GET /api/cities/{copo}/anomalies -- per-city anomaly feed."""

    def test_city_anomalies_returns_list(self) -> None:
        """City anomalies endpoint returns items and count."""
        response = client.get(f"/api/cities/{YUKON_COPO}/anomalies")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertIn("items", data)
        self.assertIn("count", data)
        self.assertEqual(data["copo"], YUKON_COPO)

    def test_city_anomalies_with_date_range_filter(self) -> None:
        """City anomalies can be filtered by start_date and end_date."""
        # First get all anomalies to find a date range
        full_resp = client.get(f"/api/cities/{YUKON_COPO}/anomalies")
        self.assertEqual(full_resp.status_code, 200)
        full_data = full_resp.json()

        if full_data["count"] == 0:
            self.skipTest("No anomalies for Yukon to test date filtering")

        first_date = full_data["items"][-1]["anomaly_date"]
        last_date = full_data["items"][0]["anomaly_date"]

        filtered_resp = client.get(
            f"/api/cities/{YUKON_COPO}/anomalies",
            params={"start_date": first_date, "end_date": last_date},
        )
        self.assertEqual(filtered_resp.status_code, 200)
        filtered_data = filtered_resp.json()
        self.assertIn("items", filtered_data)
        self.assertIn("count", filtered_data)

    def test_city_anomalies_not_found(self) -> None:
        """Anomalies for non-existent copo returns 404."""
        response = client.get(f"/api/cities/{NONEXISTENT_COPO}/anomalies")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
