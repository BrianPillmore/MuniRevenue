"""Unit tests for the email_report service.

These tests run without a live database by using mock cursor objects.
They verify:
- Dynamic tax-type scoping (only present types in cards/sections)
- HTML email structure and content
- Missed-filing and anomaly sections respect the present-types filter
- Currency and percentage formatting helpers
- SMTP delivery path dispatches correctly
- Log-mode delivery does not raise

Run from project root:
    cd backend && .venv/Scripts/python -m pytest ../tests/integration/test_email_report.py -v
"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "backend"))

from app.services.email_report import (
    AnomalySummary,
    EmailSettings,
    JurisdictionReportData,
    MissedFilingSummary,
    ReportRecipient,
    SendReportsResult,
    TaxTypeSummary,
    _TAX_TYPE_LABELS,
    _fmt_currency,
    _fmt_pct,
    _severity_badge,
    build_email_html,
    build_email_subject,
    build_report_data,
    deliver_report,
    query_anomalies,
    query_missed_filings,
    query_present_tax_types,
    query_tax_summaries,
    send_reports_after_import,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(*, mode: str = "log") -> EmailSettings:
    return EmailSettings(
        email_mode=mode,
        email_from="noreply@munirevenue.com",
        smtp_host="smtp.example.com" if mode == "smtp" else None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        smtp_use_tls=True,
        base_url="https://app.munirevenue.com",
    )


def _make_dict_row(**kwargs):
    """Return a dict that supports dict-style access, mimicking RealDictRow."""
    return dict(**kwargs)


def _mock_cursor(fetchone_returns=None, fetchall_returns=None):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_returns
    cur.fetchall.return_value = fetchall_returns if fetchall_returns is not None else []
    return cur


def _make_report_data(
    present_tax_types: list[str],
    tax_summaries: list[TaxTypeSummary] | None = None,
    missed_filings: list[MissedFilingSummary] | None = None,
    anomalies: list[AnomalySummary] | None = None,
) -> JurisdictionReportData:
    return JurisdictionReportData(
        copo="0955",
        jurisdiction_name="Yukon",
        report_month=date(2026, 3, 1),
        present_tax_types=present_tax_types,
        tax_summaries=tax_summaries or [],
        missed_filings=missed_filings or [],
        anomalies=anomalies or [],
        dashboard_url="https://app.munirevenue.com/city/0955",
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


class TestFormattingHelpers(unittest.TestCase):

    def test_fmt_currency_zero(self):
        self.assertEqual(_fmt_currency(0.0), "$0")

    def test_fmt_currency_large(self):
        self.assertEqual(_fmt_currency(1_234_567.89), "$1,234,568")

    def test_fmt_pct_none(self):
        self.assertEqual(_fmt_pct(None), "N/A")

    def test_fmt_pct_positive(self):
        self.assertTrue(_fmt_pct(12.5).startswith("+"))
        self.assertIn("12.5%", _fmt_pct(12.5))

    def test_fmt_pct_negative(self):
        result = _fmt_pct(-7.3)
        self.assertNotIn("+", result)
        self.assertIn("7.3%", result)

    def test_severity_badge_critical(self):
        badge = _severity_badge("critical")
        self.assertIn("CRITICAL", badge)
        self.assertIn("fbe8e8", badge)

    def test_severity_badge_medium(self):
        badge = _severity_badge("medium")
        self.assertIn("MEDIUM", badge)

    def test_severity_badge_unknown_falls_back(self):
        badge = _severity_badge("info")
        self.assertIn("INFO", badge)


# ---------------------------------------------------------------------------
# query_present_tax_types
# ---------------------------------------------------------------------------


class TestQueryPresentTaxTypes(unittest.TestCase):

    def test_returns_only_types_with_data(self):
        cur = _mock_cursor(
            fetchall_returns=[
                _make_dict_row(tax_type="sales"),
                _make_dict_row(tax_type="use"),
            ]
        )
        result = query_present_tax_types(cur, "0955")
        # Should be in canonical order: sales, use, lodging
        self.assertEqual(result, ["sales", "use"])

    def test_all_three_types(self):
        cur = _mock_cursor(
            fetchall_returns=[
                _make_dict_row(tax_type="lodging"),
                _make_dict_row(tax_type="sales"),
                _make_dict_row(tax_type="use"),
            ]
        )
        result = query_present_tax_types(cur, "0010")
        self.assertEqual(result, ["sales", "use", "lodging"])

    def test_empty_result_when_no_data(self):
        cur = _mock_cursor(fetchall_returns=[])
        result = query_present_tax_types(cur, "9999")
        self.assertEqual(result, [])

    def test_only_lodging(self):
        cur = _mock_cursor(
            fetchall_returns=[_make_dict_row(tax_type="lodging")]
        )
        result = query_present_tax_types(cur, "0010")
        self.assertEqual(result, ["lodging"])


# ---------------------------------------------------------------------------
# query_tax_summaries
# ---------------------------------------------------------------------------


class TestQueryTaxSummaries(unittest.TestCase):

    def test_uses_mv_yoy_view_when_available(self):
        cur = MagicMock()
        cur.fetchone.return_value = _make_dict_row(
            current_returned=500_000,
            prior_year_returned=450_000,
            yoy_change_pct=11.11,
        )
        summaries = query_tax_summaries(
            cur, "0955", date(2026, 3, 1), ["sales"]
        )
        self.assertEqual(len(summaries), 1)
        s = summaries[0]
        self.assertEqual(s.tax_type, "sales")
        self.assertAlmostEqual(s.current_returned, 500_000.0)
        self.assertAlmostEqual(s.prior_year_returned, 450_000.0)
        self.assertAlmostEqual(s.yoy_change_pct, 11.11)

    def test_falls_back_to_ledger_records_when_view_empty(self):
        cur = MagicMock()
        # mv_yoy_comparison returns nothing
        cur.fetchone.side_effect = [None, _make_dict_row(returned=250_000)]
        summaries = query_tax_summaries(
            cur, "0955", date(2026, 3, 1), ["sales"]
        )
        self.assertEqual(len(summaries), 1)
        s = summaries[0]
        self.assertAlmostEqual(s.current_returned, 250_000.0)
        self.assertIsNone(s.prior_year_returned)
        self.assertIsNone(s.yoy_change_pct)

    def test_no_tax_types_returns_empty(self):
        cur = MagicMock()
        summaries = query_tax_summaries(cur, "0955", date(2026, 3, 1), [])
        self.assertEqual(summaries, [])
        cur.execute.assert_not_called()

    def test_multiple_types_queried_independently(self):
        cur = MagicMock()
        cur.fetchone.return_value = _make_dict_row(
            current_returned=100_000,
            prior_year_returned=None,
            yoy_change_pct=None,
        )
        summaries = query_tax_summaries(
            cur, "0955", date(2026, 3, 1), ["sales", "use"]
        )
        self.assertEqual(len(summaries), 2)
        self.assertEqual({s.tax_type for s in summaries}, {"sales", "use"})


# ---------------------------------------------------------------------------
# query_missed_filings
# ---------------------------------------------------------------------------


class TestQueryMissedFilings(unittest.TestCase):

    def test_no_present_types_returns_empty(self):
        cur = MagicMock()
        result = query_missed_filings(cur, "0955", date(2026, 3, 1), [])
        self.assertEqual(result, [])
        cur.execute.assert_not_called()

    def test_returns_candidates_for_present_types_only(self):
        cur = _mock_cursor(
            fetchall_returns=[
                _make_dict_row(
                    tax_type="sales",
                    activity_code="441110",
                    activity_description="Auto Dealers",
                    missing_amount=15_000,
                    severity="high",
                )
            ]
        )
        result = query_missed_filings(
            cur, "0955", date(2026, 3, 1), ["sales", "use"]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].tax_type, "sales")
        self.assertEqual(result[0].severity, "high")
        self.assertAlmostEqual(result[0].missing_amount, 15_000.0)

    def test_placeholders_match_present_type_count(self):
        """The SQL IN clause must have exactly as many placeholders as tax types."""
        cur = _mock_cursor(fetchall_returns=[])
        query_missed_filings(
            cur, "0955", date(2026, 3, 1), ["sales", "use", "lodging"]
        )
        call_args = cur.execute.call_args
        sql, params = call_args[0]
        # Params: copo, anomaly_date, sales, use, lodging, limit
        self.assertEqual(len(params), 6)


# ---------------------------------------------------------------------------
# query_anomalies
# ---------------------------------------------------------------------------


class TestQueryAnomalies(unittest.TestCase):

    def test_no_present_types_returns_empty(self):
        cur = MagicMock()
        result = query_anomalies(cur, "0955", date(2026, 3, 1), [])
        self.assertEqual(result, [])
        cur.execute.assert_not_called()

    def test_returns_anomalies_for_present_types(self):
        cur = _mock_cursor(
            fetchall_returns=[
                _make_dict_row(
                    tax_type="sales",
                    anomaly_type="drop",
                    severity="critical",
                    actual_value=80_000,
                    expected_value=150_000,
                    deviation_pct=-46.67,
                    description="Significant revenue drop detected",
                )
            ]
        )
        result = query_anomalies(
            cur, "0955", date(2026, 3, 1), ["sales"]
        )
        self.assertEqual(len(result), 1)
        a = result[0]
        self.assertEqual(a.tax_type, "sales")
        self.assertEqual(a.severity, "critical")
        self.assertAlmostEqual(a.deviation_pct, -46.67)

    def test_window_start_calculated_correctly(self):
        """Three-month lookback from March 2026 should start at January 2026."""
        cur = _mock_cursor(fetchall_returns=[])
        query_anomalies(
            cur, "0955", date(2026, 3, 1), ["sales"], lookback_months=3
        )
        call_args = cur.execute.call_args
        _sql, params = call_args[0]
        window_start = params[1]
        self.assertEqual(window_start, date(2026, 1, 1))


# ---------------------------------------------------------------------------
# build_email_html -- structure and content
# ---------------------------------------------------------------------------


class TestBuildEmailHtml(unittest.TestCase):

    def _base_summary(self, tax_type: str) -> TaxTypeSummary:
        return TaxTypeSummary(
            tax_type=tax_type,
            current_returned=400_000.0,
            prior_year_returned=370_000.0,
            yoy_change_pct=8.11,
            month_label="Mar-26",
        )

    def test_sales_only_city_has_no_lodging_card(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            tax_summaries=[self._base_summary("sales")],
        )
        html = build_email_html(data)
        self.assertIn("Sales Tax", html)
        self.assertNotIn("Lodging Tax", html)
        self.assertNotIn("Use Tax", html)

    def test_sales_and_use_city(self):
        data = _make_report_data(
            present_tax_types=["sales", "use"],
            tax_summaries=[
                self._base_summary("sales"),
                self._base_summary("use"),
            ],
        )
        html = build_email_html(data)
        self.assertIn("Sales Tax", html)
        self.assertIn("Use Tax", html)
        self.assertNotIn("Lodging Tax", html)

    def test_all_three_types(self):
        data = _make_report_data(
            present_tax_types=["sales", "use", "lodging"],
            tax_summaries=[
                self._base_summary("sales"),
                self._base_summary("use"),
                self._base_summary("lodging"),
            ],
        )
        html = build_email_html(data)
        self.assertIn("Sales Tax", html)
        self.assertIn("Use Tax", html)
        self.assertIn("Lodging Tax", html)

    def test_yoy_positive_shows_up_arrow(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            tax_summaries=[self._base_summary("sales")],
        )
        html = build_email_html(data)
        # Up arrow Unicode HTML entity or character
        self.assertIn("8593", html)  # &#8593;

    def test_no_tax_summaries_shows_fallback_message(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            tax_summaries=[],
        )
        html = build_email_html(data)
        self.assertIn("No revenue data found", html)

    def test_missed_filings_table_rendered(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            missed_filings=[
                MissedFilingSummary(
                    tax_type="sales",
                    activity_code="441110",
                    activity_description="Auto Dealers",
                    missing_amount=12_000.0,
                    severity="high",
                )
            ],
        )
        html = build_email_html(data)
        self.assertIn("441110", html)
        self.assertIn("Auto Dealers", html)
        self.assertIn("12,000", html)
        self.assertIn("HIGH", html)

    def test_no_missed_filings_shows_none_message(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            missed_filings=[],
        )
        html = build_email_html(data)
        self.assertIn("No missed-filing candidates", html)

    def test_anomaly_table_rendered(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            anomalies=[
                AnomalySummary(
                    tax_type="sales",
                    anomaly_type="drop",
                    severity="critical",
                    actual_value=80_000.0,
                    expected_value=150_000.0,
                    deviation_pct=-46.67,
                    description="Significant revenue drop",
                )
            ],
        )
        html = build_email_html(data)
        self.assertIn("CRITICAL", html)
        self.assertIn("80,000", html)
        self.assertIn("150,000", html)
        self.assertIn("Significant revenue drop", html)

    def test_no_anomalies_shows_none_message(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            anomalies=[],
        )
        html = build_email_html(data)
        self.assertIn("No open anomalies", html)

    def test_empty_present_types_shows_no_tax_type_record_message(self):
        data = _make_report_data(present_tax_types=[])
        html = build_email_html(data)
        self.assertIn("No tax types on record", html)

    def test_dashboard_link_in_email(self):
        data = _make_report_data(present_tax_types=["sales"])
        html = build_email_html(data)
        self.assertIn("Open Dashboard", html)
        self.assertIn("0955", html)

    def test_jurisdiction_name_in_title(self):
        data = _make_report_data(present_tax_types=["sales"])
        html = build_email_html(data)
        self.assertIn("Yukon", html)

    def test_report_month_in_html(self):
        data = _make_report_data(present_tax_types=["sales"])
        html = build_email_html(data)
        self.assertIn("March 2026", html)


# ---------------------------------------------------------------------------
# build_email_subject
# ---------------------------------------------------------------------------


class TestBuildEmailSubject(unittest.TestCase):

    def test_subject_contains_name_and_month(self):
        data = _make_report_data(present_tax_types=["sales"])
        subject = build_email_subject(data)
        self.assertIn("Yukon", subject)
        self.assertIn("March 2026", subject)
        self.assertIn("MuniRev", subject)


# ---------------------------------------------------------------------------
# deliver_report
# ---------------------------------------------------------------------------


class TestDeliverReport(unittest.TestCase):

    def test_log_mode_does_not_raise(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            tax_summaries=[
                TaxTypeSummary(
                    tax_type="sales",
                    current_returned=400_000.0,
                    prior_year_returned=None,
                    yoy_change_pct=None,
                    month_label="Mar-26",
                )
            ],
        )
        settings = _make_settings(mode="log")
        # Should not raise; just logs
        deliver_report(settings=settings, recipient="test@city.gov", report_data=data)

    def test_skips_delivery_when_no_present_types(self):
        data = _make_report_data(present_tax_types=[])
        settings = _make_settings(mode="log")
        with patch("app.services.email_report._send_via_smtp") as mock_smtp:
            deliver_report(settings=settings, recipient="test@city.gov", report_data=data)
            mock_smtp.assert_not_called()

    def test_smtp_mode_calls_send_via_smtp(self):
        data = _make_report_data(
            present_tax_types=["sales"],
            tax_summaries=[
                TaxTypeSummary(
                    tax_type="sales",
                    current_returned=400_000.0,
                    prior_year_returned=None,
                    yoy_change_pct=None,
                    month_label="Mar-26",
                )
            ],
        )
        settings = _make_settings(mode="smtp")
        with patch("app.services.email_report._send_via_smtp") as mock_smtp:
            deliver_report(settings=settings, recipient="test@city.gov", report_data=data)
            mock_smtp.assert_called_once()
            _settings, recipient, subject, html = mock_smtp.call_args[0]
            self.assertEqual(recipient, "test@city.gov")
            self.assertIn("Yukon", subject)

    def test_smtp_failure_does_not_propagate(self):
        """SMTP errors are caught and logged; deliver_report does not re-raise."""
        data = _make_report_data(
            present_tax_types=["sales"],
            tax_summaries=[
                TaxTypeSummary(
                    tax_type="sales",
                    current_returned=100_000.0,
                    prior_year_returned=None,
                    yoy_change_pct=None,
                    month_label="Mar-26",
                )
            ],
        )
        settings = _make_settings(mode="smtp")
        with patch(
            "app.services.email_report._send_via_smtp",
            side_effect=ConnectionRefusedError("SMTP unavailable"),
        ):
            # Should not raise
            deliver_report(settings=settings, recipient="test@city.gov", report_data=data)


# ---------------------------------------------------------------------------
# send_reports_after_import -- integration-style
# ---------------------------------------------------------------------------


class TestSendReportsAfterImport(unittest.TestCase):

    def _make_mock_conn(self, present_types: list[str] | None = None):
        """Return a mock psycopg2 connection with a cursor that returns preset data."""
        import psycopg2.extras

        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value = cur

        if present_types is None:
            present_types = ["sales"]

        def fetchall_side_effect():
            # Called for query_present_tax_types
            return [{"tax_type": tt} for tt in present_types]

        def fetchone_side_effect():
            # Called for query_tax_summaries (mv_yoy_comparison path)
            return {
                "current_returned": 500_000,
                "prior_year_returned": 450_000,
                "yoy_change_pct": 11.11,
            }

        cur.fetchall.side_effect = lambda: fetchall_side_effect()
        cur.fetchone.side_effect = lambda: fetchone_side_effect()
        return conn

    def test_sends_report_for_jurisdiction_with_data(self):
        conn = self._make_mock_conn(present_types=["sales"])
        settings = _make_settings(mode="log")
        recipients = [
            ReportRecipient(copo="0955", jurisdiction_name="Yukon", email="mayor@yukon.gov")
        ]
        with patch("app.services.email_report.deliver_report") as mock_deliver:
            result = send_reports_after_import(
                recipients=recipients,
                report_month=date(2026, 3, 1),
                db_conn=conn,
                settings=settings,
            )
        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.sent, 1)
        self.assertEqual(result.skipped_no_data, 0)
        self.assertEqual(result.failed, 0)
        mock_deliver.assert_called_once()

    def test_skips_jurisdiction_with_no_data(self):
        conn = self._make_mock_conn(present_types=[])
        settings = _make_settings(mode="log")
        recipients = [
            ReportRecipient(copo="9999", jurisdiction_name="Ghost Town", email="nobody@ghost.gov")
        ]
        with patch("app.services.email_report.deliver_report") as mock_deliver:
            result = send_reports_after_import(
                recipients=recipients,
                report_month=date(2026, 3, 1),
                db_conn=conn,
                settings=settings,
            )
        self.assertEqual(result.attempted, 1)
        self.assertEqual(result.sent, 0)
        self.assertEqual(result.skipped_no_data, 1)
        mock_deliver.assert_not_called()

    def test_handles_multiple_recipients(self):
        conn = self._make_mock_conn(present_types=["sales", "use"])
        settings = _make_settings(mode="log")
        recipients = [
            ReportRecipient(copo="0955", jurisdiction_name="Yukon", email="a@a.gov"),
            ReportRecipient(copo="0001", jurisdiction_name="OKC", email="b@b.gov"),
        ]
        with patch("app.services.email_report.deliver_report"):
            result = send_reports_after_import(
                recipients=recipients,
                report_month=date(2026, 3, 1),
                db_conn=conn,
                settings=settings,
            )
        self.assertEqual(result.attempted, 2)
        self.assertEqual(result.sent, 2)

    def test_failed_recipient_counted_and_others_continue(self):
        """An exception for one recipient must not abort the rest."""
        conn = self._make_mock_conn(present_types=["sales"])
        settings = _make_settings(mode="log")
        recipients = [
            ReportRecipient(copo="0955", jurisdiction_name="Yukon", email="ok@ok.gov"),
            ReportRecipient(copo="0001", jurisdiction_name="OKC", email="bad@bad.gov"),
        ]

        call_count = 0

        def mock_deliver(*, settings, recipient, report_data):
            nonlocal call_count
            call_count += 1
            if recipient == "bad@bad.gov":
                raise RuntimeError("Simulated delivery failure")

        with patch("app.services.email_report.deliver_report", side_effect=mock_deliver):
            result = send_reports_after_import(
                recipients=recipients,
                report_month=date(2026, 3, 1),
                db_conn=conn,
                settings=settings,
            )

        self.assertEqual(result.attempted, 2)
        self.assertEqual(result.sent, 1)
        self.assertEqual(result.failed, 1)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.errors[0]["copo"], "0001")

    def test_result_report_month_matches_input(self):
        conn = self._make_mock_conn(present_types=["sales"])
        settings = _make_settings(mode="log")
        target_month = date(2026, 2, 1)
        with patch("app.services.email_report.deliver_report"):
            result = send_reports_after_import(
                recipients=[
                    ReportRecipient(copo="0955", jurisdiction_name="Yukon", email="x@x.gov")
                ],
                report_month=target_month,
                db_conn=conn,
                settings=settings,
            )
        self.assertEqual(result.report_month, target_month)


# ---------------------------------------------------------------------------
# Tax-type label mapping completeness
# ---------------------------------------------------------------------------


class TestTaxTypeLabels(unittest.TestCase):

    def test_all_known_types_have_labels(self):
        for tt in ("sales", "use", "lodging"):
            self.assertIn(tt, _TAX_TYPE_LABELS)
            self.assertIsNotNone(_TAX_TYPE_LABELS[tt])


if __name__ == "__main__":
    unittest.main()
