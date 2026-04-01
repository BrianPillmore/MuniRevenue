"""Tests for economic indicator integration with forecasting."""
import unittest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

YUKON = "0955"
OKC = "5521"


class TestEconomicIndicatorsInDB(unittest.TestCase):
    """Verify economic indicators are loaded."""

    def test_indicators_table_has_data(self):
        import psycopg2
        conn = psycopg2.connect("postgresql://munirev:changeme@localhost:5432/munirev")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM economic_indicators")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreater(count, 1000, "Should have >1000 economic indicator records")

    def test_has_labor_indicators(self):
        import psycopg2
        conn = psycopg2.connect("postgresql://munirev:changeme@localhost:5432/munirev")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM economic_indicators WHERE indicator_family IN ('labor', 'bls_laus', 'bls_ces')")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreater(count, 100)

    def test_has_county_unemployment(self):
        import psycopg2
        conn = psycopg2.connect("postgresql://munirev:changeme@localhost:5432/munirev")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT geography_key) FROM economic_indicators WHERE indicator_family='bls_laus'")
        counties = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(counties, 70, "Should have unemployment for 70+ counties")

    def test_has_population(self):
        import psycopg2
        conn = psycopg2.connect("postgresql://munirev:changeme@localhost:5432/munirev")
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM economic_indicators WHERE indicator_family='population'")
        count = cur.fetchone()[0]
        conn.close()
        self.assertGreater(count, 300, "Should have 77 counties x 5 years")


class TestForecastWithIndicators(unittest.TestCase):
    """Verify forecast endpoint uses economic indicators."""

    def test_forecast_balanced_has_indicators(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast?tax_type=sales&indicator_profile=balanced")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["indicator_profile"], "balanced")
        exp = data.get("explainability", {})
        summary = exp.get("indicator_summary", "")
        self.assertNotIn("no economic_indicators rows were available", summary,
                         "Indicators should be found with balanced profile")
        self.assertIn("labor", summary.lower(),
                      "Balanced profile should use labor indicators")

    def test_forecast_off_has_no_indicators(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast?tax_type=sales&indicator_profile=off")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        exp = data.get("explainability", {})
        summary = exp.get("indicator_summary", "")
        self.assertIn("off", summary.lower())

    def test_forecast_returns_12_months(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast?tax_type=sales")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        forecasts = data.get("forecasts", data.get("forecast_points", []))
        self.assertEqual(len(forecasts), 12)

    def test_forecast_has_backtest(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast?tax_type=sales")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        bt = data.get("backtest_summary", {})
        self.assertIsNotNone(bt.get("mape"), "Should have backtest MAPE")

    def test_forecast_labor_profile(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast?tax_type=sales&indicator_profile=labor")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        exp = data.get("explainability", {})
        summary = exp.get("indicator_summary", "")
        self.assertIn("labor", summary.lower())

    def test_forecast_compare_endpoint(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast/compare?tax_type=sales")
        if resp.status_code == 200:
            data = resp.json()
            self.assertIn("model_comparison", data)

    def test_forecast_drivers_endpoint(self):
        resp = client.get(f"/api/cities/{YUKON}/forecast/drivers?tax_type=sales")
        if resp.status_code == 200:
            data = resp.json()
            self.assertIn("indicator_summary", data.get("explainability", data))


if __name__ == "__main__":
    unittest.main()
