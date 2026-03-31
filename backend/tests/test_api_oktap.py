"""API-level tests for OkTAP import endpoints.

Uses FastAPI TestClient against the real application.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"

client = TestClient(app)


class HealthTests(unittest.TestCase):
    def test_health_returns_ok(self) -> None:
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class OkTAPReportTypesTests(unittest.TestCase):
    def test_returns_two_report_types(self) -> None:
        response = client.get("/api/oktap/report-types")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["report_types"]), 2)
        names = {rt["name"] for rt in data["report_types"]}
        self.assertEqual(names, {"ledger", "naics"})


class LedgerImportTests(unittest.TestCase):
    def test_import_ledger_success(self) -> None:
        file_path = FIXTURES_DIR / "ledger_yukon_sales_2026.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/ledger",
                files={"file": ("ledger.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_type"], "ledger")
        self.assertEqual(data["tax_type"], "sales")
        self.assertEqual(data["record_count"], 9)
        self.assertEqual(data["copo"], "0955")

    def test_import_ledger_invalid_tax_type(self) -> None:
        file_path = FIXTURES_DIR / "ledger_yukon_sales_2026.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/ledger",
                files={"file": ("ledger.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "invalid"},
            )
        self.assertEqual(response.status_code, 400)

    def test_import_ledger_wrong_extension(self) -> None:
        response = client.post(
            "/api/oktap/import/ledger",
            files={"file": ("data.xlsx", b"fake", "application/octet-stream")},
            data={"tax_type": "sales"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(".xls", response.json()["detail"])

    def test_import_ledger_bad_xml(self) -> None:
        response = client.post(
            "/api/oktap/import/ledger",
            files={"file": ("bad.xls", b"not xml", "application/vnd.ms-excel")},
            data={"tax_type": "sales"},
        )
        self.assertEqual(response.status_code, 400)


class NaicsImportTests(unittest.TestCase):
    def test_import_naics_success(self) -> None:
        file_path = FIXTURES_DIR / "naics_yukon_sales_2026_02.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/naics",
                files={"file": ("naics.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales", "year": "2026", "month": "2"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["report_type"], "naics")
        self.assertEqual(data["record_count"], 471)
        self.assertEqual(data["copo"], "0955")

    def test_import_naics_missing_year(self) -> None:
        file_path = FIXTURES_DIR / "naics_yukon_sales_2026_02.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/naics",
                files={"file": ("naics.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales", "month": "2"},
            )
        self.assertEqual(response.status_code, 422)  # FastAPI validation error

    def test_import_naics_invalid_month(self) -> None:
        file_path = FIXTURES_DIR / "naics_yukon_sales_2026_02.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/naics",
                files={"file": ("naics.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales", "year": "2026", "month": "13"},
            )
        self.assertEqual(response.status_code, 400)


class AutoDetectTests(unittest.TestCase):
    def test_auto_detect_ledger(self) -> None:
        file_path = FIXTURES_DIR / "ledger_yukon_sales_2026.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/auto",
                files={"file": ("data.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report_type"], "ledger")

    def test_auto_detect_naics_requires_year_month(self) -> None:
        file_path = FIXTURES_DIR / "naics_yukon_sales_2026_02.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/auto",
                files={"file": ("data.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales"},
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("year and month", response.json()["detail"])

    def test_auto_detect_naics_with_year_month(self) -> None:
        file_path = FIXTURES_DIR / "naics_yukon_sales_2026_02.xls"
        with open(file_path, "rb") as f:
            response = client.post(
                "/api/oktap/import/auto",
                files={"file": ("data.xls", f, "application/vnd.ms-excel")},
                data={"tax_type": "sales", "year": "2026", "month": "2"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["report_type"], "naics")


class BulkImportTests(unittest.TestCase):
    def test_bulk_import_two_files(self) -> None:
        ledger = FIXTURES_DIR / "ledger_yukon_sales_2026.xls"
        naics = FIXTURES_DIR / "naics_yukon_sales_2026_02.xls"
        with open(ledger, "rb") as f1, open(naics, "rb") as f2:
            response = client.post(
                "/api/oktap/import/bulk",
                files=[
                    ("files", ("ledger.xls", f1, "application/vnd.ms-excel")),
                    ("files", ("naics.xls", f2, "application/vnd.ms-excel")),
                ],
                data={"tax_type": "sales", "year": "2026", "month": "2"},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_files"], 2)
        self.assertEqual(data["successful"], 2)
        self.assertEqual(data["failed"], 0)


class AnalyzeEndpointTests(unittest.TestCase):
    def test_analyze_sample_data(self) -> None:
        sample = Path(__file__).parent.parent / "assets" / "sample-data.xlsx"
        with open(sample, "rb") as f:
            response = client.post(
                "/api/analyze",
                files={"file": ("sample.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["summary"]["records"], 86)
        self.assertEqual(len(data["forecast"]), 12)
        self.assertGreater(len(data["highlights"]), 0)

    def test_analyze_rejects_non_xlsx(self) -> None:
        response = client.post(
            "/api/analyze",
            files={"file": ("bad.txt", b"not excel", "text/plain")},
        )
        self.assertEqual(response.status_code, 400)


class ReportEndpointTests(unittest.TestCase):
    def test_report_returns_html(self) -> None:
        sample = Path(__file__).parent.parent / "assets" / "sample-data.xlsx"
        with open(sample, "rb") as f:
            response = client.post(
                "/api/report",
                files={"file": ("sample.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("MuniRev", response.text)


if __name__ == "__main__":
    unittest.main()
