"""Post-import email report service for MuniRev.

Builds and sends a jurisdiction-specific HTML revenue summary email after
each OkTAP data import cycle.  Only the tax types that actually exist in
the database for a given jurisdiction are included in the report -- no
empty/placeholder sections for tax types the city does not collect.

Environment variables (shared with the browser-auth SMTP config):
    MUNIREV_EMAIL_MODE      "log" (default) or "smtp"
    MUNIREV_EMAIL_FROM      sender address
    SMTP_HOST               SMTP server hostname
    SMTP_PORT               SMTP server port (default: 587)
    SMTP_USERNAME           SMTP credentials (optional)
    SMTP_PASSWORD           SMTP credentials (optional)
    SMTP_USE_TLS            "true" / "false" (default: true)
    MUNIREV_BASE_URL        Base URL for dashboard links (default: http://localhost:8000)
"""
from __future__ import annotations

import logging
import os
import smtplib
from dataclasses import dataclass, field
from datetime import date
from email.message import EmailMessage
from html import escape
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tax-type display labels
# ---------------------------------------------------------------------------

_TAX_TYPE_LABELS: dict[str, str] = {
    "sales": "Sales Tax",
    "use": "Use Tax",
    "lodging": "Lodging Tax",
}

# Card accent colours (one per known tax type, in display order)
_TAX_TYPE_CARD_COLOURS: dict[str, str] = {
    "sales": "#2f6f74",
    "use": "#a63d40",
    "lodging": "#6b4c8a",
}

# Preferred display order for tax types
_TAX_TYPE_ORDER: list[str] = ["sales", "use", "lodging"]


# ---------------------------------------------------------------------------
# Data-transfer objects
# ---------------------------------------------------------------------------


@dataclass
class TaxTypeSummary:
    """Revenue summary for one tax type within a reporting period."""
    tax_type: str
    current_returned: float
    prior_year_returned: float | None
    yoy_change_pct: float | None
    month_label: str          # e.g. "Feb-25"


@dataclass
class MissedFilingSummary:
    """Brief description of a top missed-filing candidate."""
    tax_type: str
    activity_code: str
    activity_description: str
    missing_amount: float
    severity: str


@dataclass
class AnomalySummary:
    """Brief description of a detected anomaly."""
    tax_type: str
    anomaly_type: str
    severity: str
    actual_value: float | None
    expected_value: float | None
    deviation_pct: float | None
    description: str


@dataclass
class JurisdictionReportData:
    """All data needed to render one jurisdiction's email report."""
    copo: str
    jurisdiction_name: str
    report_month: date
    present_tax_types: list[str]           # ordered, only types with data
    tax_summaries: list[TaxTypeSummary]    # one per present_tax_type
    missed_filings: list[MissedFilingSummary]   # limited to present types
    anomalies: list[AnomalySummary]        # limited to present types
    dashboard_url: str


@dataclass
class EmailSettings:
    """SMTP / delivery settings resolved from environment variables."""
    email_mode: str
    email_from: str
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_use_tls: bool
    base_url: str


# ---------------------------------------------------------------------------
# Settings loader
# ---------------------------------------------------------------------------


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int, *, minimum: int = 1) -> int:
    if value is None:
        return default
    try:
        return max(minimum, int(value))
    except ValueError:
        return default


def load_email_settings() -> EmailSettings:
    email_mode = (os.environ.get("MUNIREV_EMAIL_MODE") or "log").strip().lower()
    if email_mode not in {"log", "smtp"}:
        email_mode = "log"

    return EmailSettings(
        email_mode=email_mode,
        email_from=(os.environ.get("MUNIREV_EMAIL_FROM") or "noreply@munirevenue.com").strip(),
        smtp_host=(os.environ.get("SMTP_HOST") or "").strip() or None,
        smtp_port=_parse_int(os.environ.get("SMTP_PORT"), 587, minimum=1),
        smtp_username=(os.environ.get("SMTP_USERNAME") or "").strip() or None,
        smtp_password=(os.environ.get("SMTP_PASSWORD") or "").strip() or None,
        smtp_use_tls=_parse_bool(os.environ.get("SMTP_USE_TLS"), True),
        base_url=(os.environ.get("MUNIREV_BASE_URL") or "http://localhost:8000").rstrip("/"),
    )


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


def query_present_tax_types(cur: Any, copo: str) -> list[str]:
    """Return tax types that have at least one ledger record for this jurisdiction.

    Results are returned in canonical display order (sales, use, lodging).
    """
    cur.execute(
        """
        SELECT DISTINCT tax_type
        FROM ledger_records
        WHERE copo = %s
        ORDER BY tax_type
        """,
        (copo,),
    )
    rows = cur.fetchall()
    present = {row["tax_type"] for row in rows}
    return [tt for tt in _TAX_TYPE_ORDER if tt in present]


def query_tax_summaries(
    cur: Any,
    copo: str,
    report_month: date,
    present_tax_types: list[str],
) -> list[TaxTypeSummary]:
    """Return revenue summary rows for each present tax type for the report month.

    Uses the mv_yoy_comparison view when populated; falls back to ledger_records
    directly for cities where the view has not yet been refreshed.
    """
    if not present_tax_types:
        return []

    month_label = report_month.strftime("%b-%y")
    summaries: list[TaxTypeSummary] = []

    for tax_type in present_tax_types:
        # Prefer the materialized view (contains YoY data)
        cur.execute(
            """
            SELECT
                current_returned,
                prior_year_returned,
                yoy_change_pct
            FROM mv_yoy_comparison
            WHERE copo = %s
              AND tax_type = %s
              AND voucher_date = %s
            """,
            (copo, tax_type, report_month),
        )
        row = cur.fetchone()

        if row is not None:
            summaries.append(TaxTypeSummary(
                tax_type=tax_type,
                current_returned=float(row["current_returned"] or 0),
                prior_year_returned=float(row["prior_year_returned"]) if row["prior_year_returned"] is not None else None,
                yoy_change_pct=float(row["yoy_change_pct"]) if row["yoy_change_pct"] is not None else None,
                month_label=month_label,
            ))
        else:
            # Fallback: pull from ledger_records directly
            cur.execute(
                """
                SELECT returned
                FROM ledger_records
                WHERE copo = %s
                  AND tax_type = %s
                  AND voucher_date = %s
                """,
                (copo, tax_type, report_month),
            )
            ledger_row = cur.fetchone()
            if ledger_row is not None:
                summaries.append(TaxTypeSummary(
                    tax_type=tax_type,
                    current_returned=float(ledger_row["returned"] or 0),
                    prior_year_returned=None,
                    yoy_change_pct=None,
                    month_label=month_label,
                ))

    return summaries


def query_missed_filings(
    cur: Any,
    copo: str,
    report_month: date,
    present_tax_types: list[str],
    *,
    limit: int = 5,
) -> list[MissedFilingSummary]:
    """Return the top missed-filing candidates for this jurisdiction and month.

    Only returns rows for tax types that actually exist for this jurisdiction.
    Uses the hybrid baseline method (same as the platform default).
    """
    if not present_tax_types:
        return []

    placeholders = ", ".join(["%s"] * len(present_tax_types))
    cur.execute(
        f"""
        SELECT
            tax_type,
            activity_code,
            activity_description,
            COALESCE(hybrid_missing_amount,
                (COALESCE(prior_year_value, trailing_mean_12) - actual_value)
            )                               AS missing_amount,
            CASE
                WHEN COALESCE(hybrid_missing_amount,
                         COALESCE(prior_year_value, trailing_mean_12) - actual_value
                     ) >= 25000
                  OR COALESCE(hybrid_missing_pct,
                         ((COALESCE(prior_year_value, trailing_mean_12) - actual_value)
                          / NULLIF(ABS(COALESCE(prior_year_value, trailing_mean_12)), 0) * 100)
                     ) >= 85
                    THEN 'critical'
                WHEN COALESCE(hybrid_missing_amount,
                         COALESCE(prior_year_value, trailing_mean_12) - actual_value
                     ) >= 10000
                  OR COALESCE(hybrid_missing_pct,
                         ((COALESCE(prior_year_value, trailing_mean_12) - actual_value)
                          / NULLIF(ABS(COALESCE(prior_year_value, trailing_mean_12)), 0) * 100)
                     ) >= 60
                    THEN 'high'
                ELSE 'medium'
            END                             AS severity
        FROM missed_filing_candidates
        WHERE copo = %s
          AND anomaly_date = %s
          AND tax_type IN ({placeholders})
          AND COALESCE(hybrid_missing_amount,
                  COALESCE(prior_year_value, trailing_mean_12) - actual_value
              ) > 0
        ORDER BY missing_amount DESC NULLS LAST
        LIMIT %s
        """,
        (copo, report_month, *present_tax_types, limit),
    )
    rows = cur.fetchall()
    return [
        MissedFilingSummary(
            tax_type=row["tax_type"],
            activity_code=row["activity_code"],
            activity_description=row["activity_description"],
            missing_amount=float(row["missing_amount"] or 0),
            severity=row["severity"],
        )
        for row in rows
    ]


def query_anomalies(
    cur: Any,
    copo: str,
    report_month: date,
    present_tax_types: list[str],
    *,
    lookback_months: int = 3,
) -> list[AnomalySummary]:
    """Return recent anomalies for this jurisdiction scoped to present tax types.

    Looks back `lookback_months` to catch anomalies from the current import
    cycle even if they span slightly different voucher dates.
    """
    if not present_tax_types:
        return []

    from datetime import date as _date
    # Compute start of the lookback window
    zm = (report_month.year * 12 + (report_month.month - 1)) - (lookback_months - 1)
    window_start = _date(zm // 12, (zm % 12) + 1, 1)

    placeholders = ", ".join(["%s"] * len(present_tax_types))
    cur.execute(
        f"""
        SELECT
            a.tax_type,
            a.anomaly_type,
            a.severity,
            a.actual_value,
            a.expected_value,
            a.deviation_pct,
            COALESCE(a.description, a.anomaly_type) AS description
        FROM anomalies a
        WHERE a.copo = %s
          AND a.anomaly_date >= %s
          AND a.anomaly_date <= %s
          AND a.tax_type IN ({placeholders})
          AND a.status NOT IN ('dismissed', 'resolved')
        ORDER BY
            CASE a.severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                ELSE 4
            END,
            a.anomaly_date DESC
        LIMIT 10
        """,
        (copo, window_start, report_month, *present_tax_types),
    )
    rows = cur.fetchall()
    return [
        AnomalySummary(
            tax_type=row["tax_type"],
            anomaly_type=row["anomaly_type"],
            severity=row["severity"],
            actual_value=float(row["actual_value"]) if row["actual_value"] is not None else None,
            expected_value=float(row["expected_value"]) if row["expected_value"] is not None else None,
            deviation_pct=float(row["deviation_pct"]) if row["deviation_pct"] is not None else None,
            description=row["description"] or "",
        )
        for row in rows
    ]


def build_report_data(
    cur: Any,
    copo: str,
    jurisdiction_name: str,
    report_month: date,
    base_url: str,
) -> JurisdictionReportData:
    """Assemble all data needed for a jurisdiction's email report.

    Determines which tax types are present, then queries only for those.
    """
    present_tax_types = query_present_tax_types(cur, copo)
    tax_summaries = query_tax_summaries(cur, copo, report_month, present_tax_types)
    missed_filings = query_missed_filings(cur, copo, report_month, present_tax_types)
    anomalies = query_anomalies(cur, copo, report_month, present_tax_types)

    dashboard_url = f"{base_url}/city/{copo}"

    return JurisdictionReportData(
        copo=copo,
        jurisdiction_name=jurisdiction_name,
        report_month=report_month,
        present_tax_types=present_tax_types,
        tax_summaries=tax_summaries,
        missed_filings=missed_filings,
        anomalies=anomalies,
        dashboard_url=dashboard_url,
    )


# ---------------------------------------------------------------------------
# HTML email builder
# ---------------------------------------------------------------------------


def _fmt_currency(value: float) -> str:
    return f"${value:,.0f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.1f}%"


def _severity_badge(severity: str) -> str:
    colours = {
        "critical": ("#7b1a1a", "#fbe8e8"),
        "high": ("#7a4500", "#fdf0e0"),
        "medium": ("#3a5700", "#eef5e0"),
        "low": ("#1a3d5c", "#e8f0f8"),
    }
    text_colour, bg_colour = colours.get(severity.lower(), ("#333", "#eee"))
    label = severity.upper()
    return (
        f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
        f"background:{bg_colour};color:{text_colour};font-size:0.78rem;"
        f"font-weight:700;letter-spacing:0.06em'>{escape(label)}</span>"
    )


def _render_tax_card(summary: TaxTypeSummary) -> str:
    label = _TAX_TYPE_LABELS.get(summary.tax_type, summary.tax_type.title())
    accent = _TAX_TYPE_CARD_COLOURS.get(summary.tax_type, "#2f6f74")
    yoy_html = ""
    if summary.yoy_change_pct is not None:
        arrow = "&#8593;" if summary.yoy_change_pct >= 0 else "&#8595;"
        yoy_colour = "#2a6a2a" if summary.yoy_change_pct >= 0 else "#8a1a1a"
        yoy_html = (
            f"<div style='margin-top:6px;font-size:0.82rem;color:{yoy_colour};font-weight:600'>"
            f"{arrow} {_fmt_pct(summary.yoy_change_pct)} vs prior year"
            f"</div>"
        )
    prior_html = ""
    if summary.prior_year_returned is not None:
        prior_html = (
            f"<div style='margin-top:4px;font-size:0.78rem;color:#5f6f7a'>"
            f"Prior year: {_fmt_currency(summary.prior_year_returned)}"
            f"</div>"
        )

    return f"""
    <div style='background:linear-gradient(180deg,#ffffff,#fff7ec);border:1px solid #d8d2c8;
                border-radius:16px;padding:18px 20px;min-width:160px;flex:1'>
      <div style='font-size:0.72rem;text-transform:uppercase;letter-spacing:0.08em;
                  color:#5f6f7a;font-weight:600'>{escape(label)}</div>
      <div style='margin-top:10px;font-size:1.6rem;font-weight:800;color:{accent}'>
        {_fmt_currency(summary.current_returned)}
      </div>
      <div style='font-size:0.8rem;color:#5f6f7a;margin-top:2px'>{escape(summary.month_label)}</div>
      {yoy_html}
      {prior_html}
    </div>
    """


def _render_missed_filings_rows(items: list[MissedFilingSummary]) -> str:
    if not items:
        return "<p style='color:#5f6f7a;font-size:0.9rem'>No missed-filing candidates detected for this period.</p>"

    rows = []
    for item in items:
        tax_label = _TAX_TYPE_LABELS.get(item.tax_type, item.tax_type.title())
        rows.append(
            f"<tr>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.88rem'>"
            f"  {escape(item.activity_code)}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.88rem'>"
            f"  {escape(item.activity_description)}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.88rem'>"
            f"  {escape(tax_label)}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.88rem;"
            f"           text-align:right'>"
            f"  {_fmt_currency(item.missing_amount)}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;text-align:center'>"
            f"  {_severity_badge(item.severity)}"
            f"</td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)
    return f"""
    <table style='width:100%;border-collapse:collapse'>
      <thead>
        <tr style='background:#f5e8d8'>
          <th style='padding:8px 10px;text-align:left;font-size:0.8rem;font-weight:700'>Code</th>
          <th style='padding:8px 10px;text-align:left;font-size:0.8rem;font-weight:700'>Industry</th>
          <th style='padding:8px 10px;text-align:left;font-size:0.8rem;font-weight:700'>Tax Type</th>
          <th style='padding:8px 10px;text-align:right;font-size:0.8rem;font-weight:700'>Est. Missing</th>
          <th style='padding:8px 10px;text-align:center;font-size:0.8rem;font-weight:700'>Severity</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def _render_anomaly_rows(items: list[AnomalySummary]) -> str:
    if not items:
        return "<p style='color:#5f6f7a;font-size:0.9rem'>No open anomalies detected for this period.</p>"

    rows = []
    for item in items:
        tax_label = _TAX_TYPE_LABELS.get(item.tax_type, item.tax_type.title())
        actual_str = _fmt_currency(item.actual_value) if item.actual_value is not None else "N/A"
        expected_str = _fmt_currency(item.expected_value) if item.expected_value is not None else "N/A"
        dev_str = _fmt_pct(item.deviation_pct)
        rows.append(
            f"<tr>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.88rem'>"
            f"  {escape(tax_label)}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.88rem'>"
            f"  {escape(item.anomaly_type.replace('_', ' ').title())}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;text-align:center'>"
            f"  {_severity_badge(item.severity)}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;text-align:right;font-size:0.88rem'>"
            f"  {actual_str}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;text-align:right;font-size:0.88rem'>"
            f"  {expected_str}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;text-align:right;font-size:0.88rem'>"
            f"  {dev_str}"
            f"</td>"
            f"<td style='padding:8px 10px;border-bottom:1px solid #ece7df;font-size:0.85rem;color:#5f6f7a'>"
            f"  {escape(item.description)}"
            f"</td>"
            f"</tr>"
        )
    rows_html = "\n".join(rows)
    return f"""
    <table style='width:100%;border-collapse:collapse'>
      <thead>
        <tr style='background:#f5e8d8'>
          <th style='padding:8px 10px;text-align:left;font-size:0.8rem;font-weight:700'>Tax Type</th>
          <th style='padding:8px 10px;text-align:left;font-size:0.8rem;font-weight:700'>Type</th>
          <th style='padding:8px 10px;text-align:center;font-size:0.8rem;font-weight:700'>Severity</th>
          <th style='padding:8px 10px;text-align:right;font-size:0.8rem;font-weight:700'>Actual</th>
          <th style='padding:8px 10px;text-align:right;font-size:0.8rem;font-weight:700'>Expected</th>
          <th style='padding:8px 10px;text-align:right;font-size:0.8rem;font-weight:700'>Deviation</th>
          <th style='padding:8px 10px;text-align:left;font-size:0.8rem;font-weight:700'>Note</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
    """


def build_email_html(data: JurisdictionReportData) -> str:
    """Render the full HTML email for one jurisdiction.

    Revenue cards, missed filings, and anomaly sections are all scoped to
    the tax types that are actually present in the database for this city.
    Tax types with no data are silently omitted.
    """
    month_title = data.report_month.strftime("%B %Y")

    # Revenue cards -- one per present tax type, in canonical order
    cards_html = "\n".join(_render_tax_card(s) for s in data.tax_summaries)
    if not cards_html:
        cards_html = "<p style='color:#5f6f7a'>No revenue data found for this period.</p>"

    # Tax-type context note (e.g. "Sales Tax and Use Tax")
    type_labels = [_TAX_TYPE_LABELS.get(tt, tt.title()) for tt in data.present_tax_types]
    if len(type_labels) > 1:
        types_sentence = ", ".join(type_labels[:-1]) + f" and {type_labels[-1]}"
    elif type_labels:
        types_sentence = type_labels[0]
    else:
        types_sentence = "No tax types on record"

    missed_html = _render_missed_filings_rows(data.missed_filings)
    anomaly_html = _render_anomaly_rows(data.anomalies)

    missed_section_title = "Missed Filing Candidates"
    anomaly_section_title = "Revenue Anomalies"

    # Show/hide section headers based on whether there is anything to show
    missed_count = len(data.missed_filings)
    anomaly_count = len(data.anomalies)

    missed_badge = (
        f" <span style='background:#a63d40;color:white;border-radius:999px;padding:1px 7px;"
        f"font-size:0.75rem;font-weight:700'>{missed_count}</span>"
        if missed_count else ""
    )
    anomaly_badge = (
        f" <span style='background:#a63d40;color:white;border-radius:999px;padding:1px 7px;"
        f"font-size:0.75rem;font-weight:700'>{anomaly_count}</span>"
        if anomaly_count else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MuniRev Revenue Report — {escape(data.jurisdiction_name)}</title>
</head>
<body style="margin:0;padding:0;background:#f4ede1;font-family:'Trebuchet MS','Gill Sans',sans-serif;color:#112233">
  <div style="max-width:680px;margin:32px auto;padding:0 16px 48px">

    <!-- Header -->
    <div style="background:white;border:1px solid #d8d2c8;border-radius:20px;padding:28px 32px;
                box-shadow:0 12px 32px rgba(17,34,51,0.08)">
      <div style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.1em;color:#5f6f7a;
                  font-weight:700">MuniRev Monthly Report</div>
      <h1 style="margin:8px 0 4px;font-family:Georgia,'Times New Roman',serif;font-size:1.9rem;
                 color:#112233">{escape(data.jurisdiction_name)}</h1>
      <div style="color:#5f6f7a;font-size:0.9rem">{escape(month_title)} &mdash; {escape(types_sentence)}</div>

      <!-- Revenue cards -->
      <div style="display:flex;flex-wrap:wrap;gap:14px;margin-top:24px">
        {cards_html}
      </div>
    </div>

    <!-- Missed Filings -->
    <div style="background:white;border:1px solid #d8d2c8;border-radius:20px;
                padding:24px 28px;margin-top:20px;box-shadow:0 6px 20px rgba(17,34,51,0.05)">
      <h2 style="margin:0 0 16px;font-family:Georgia,'Times New Roman',serif;font-size:1.25rem;
                 color:#112233">{escape(missed_section_title)}{missed_badge}</h2>
      {missed_html}
    </div>

    <!-- Anomalies -->
    <div style="background:white;border:1px solid #d8d2c8;border-radius:20px;
                padding:24px 28px;margin-top:20px;box-shadow:0 6px 20px rgba(17,34,51,0.05)">
      <h2 style="margin:0 0 16px;font-family:Georgia,'Times New Roman',serif;font-size:1.25rem;
                 color:#112233">{escape(anomaly_section_title)}{anomaly_badge}</h2>
      {anomaly_html}
    </div>

    <!-- Dashboard link -->
    <div style="text-align:center;margin-top:28px">
      <a href="{escape(data.dashboard_url)}"
         style="display:inline-block;background:#2f6f74;color:white;text-decoration:none;
                padding:12px 28px;border-radius:999px;font-weight:700;font-size:0.95rem;
                letter-spacing:0.04em">
        Open Dashboard
      </a>
    </div>

    <!-- Footer -->
    <div style="margin-top:32px;text-align:center;color:#8a9aaa;font-size:0.78rem;line-height:1.6">
      This report was generated automatically by MuniRev after the latest OkTAP data import.<br />
      Revenue figures reflect amounts returned to {escape(data.jurisdiction_name)} for {escape(month_title)}.<br />
      Missed-filing candidates and anomalies are directional signals for analyst review.
    </div>

  </div>
</body>
</html>"""


def build_email_subject(data: JurisdictionReportData) -> str:
    month_str = data.report_month.strftime("%B %Y")
    return f"MuniRev Report: {data.jurisdiction_name} — {month_str}"


# ---------------------------------------------------------------------------
# SMTP delivery
# ---------------------------------------------------------------------------


def _send_via_smtp(
    settings: EmailSettings,
    recipient: str,
    subject: str,
    html_body: str,
) -> None:
    if not settings.smtp_host:
        raise RuntimeError(
            "SMTP_HOST must be configured when MUNIREV_EMAIL_MODE=smtp."
        )
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content("This report requires an HTML-capable email client.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)
        server.send_message(msg)


def deliver_report(
    *,
    settings: EmailSettings,
    recipient: str,
    report_data: JurisdictionReportData,
) -> None:
    """Build and deliver (or log) a jurisdiction report email.

    When email_mode is "log", the rendered HTML subject is logged at INFO
    level and delivery is skipped.  When email_mode is "smtp", the email
    is sent via the configured SMTP server.
    """
    if not report_data.present_tax_types:
        logger.info(
            "Skipping report for %s (%s): no tax types present in database.",
            report_data.jurisdiction_name,
            report_data.copo,
        )
        return

    subject = build_email_subject(report_data)
    html_body = build_email_html(report_data)

    if settings.email_mode == "smtp":
        try:
            _send_via_smtp(settings, recipient, subject, html_body)
            logger.info(
                "Sent report email to %s for %s (%s).",
                recipient,
                report_data.jurisdiction_name,
                report_data.copo,
            )
        except Exception:
            logger.exception(
                "Failed to send report email to %s for %s (%s).",
                recipient,
                report_data.jurisdiction_name,
                report_data.copo,
            )
    else:
        logger.info(
            "[email_mode=log] Report for %s (%s) to %s — subject: %s",
            report_data.jurisdiction_name,
            report_data.copo,
            recipient,
            subject,
        )


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------


@dataclass
class ReportRecipient:
    """One jurisdiction-to-email mapping for the report dispatch."""
    copo: str
    jurisdiction_name: str
    email: str


@dataclass
class SendReportsResult:
    """Aggregate outcome of a report dispatch run."""
    report_month: date
    attempted: int = 0
    sent: int = 0
    skipped_no_data: int = 0
    failed: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)


def send_reports_after_import(
    *,
    recipients: list[ReportRecipient],
    report_month: date,
    db_conn: Any,
    settings: EmailSettings | None = None,
) -> SendReportsResult:
    """Dispatch post-import revenue reports to a list of jurisdiction contacts.

    For each recipient:
    1. Query which tax types actually exist for that jurisdiction.
    2. Pull revenue summaries, missed filings, and anomalies scoped to
       those tax types only.
    3. Build and deliver the HTML email (or log it in development mode).

    Args:
        recipients:    List of (copo, jurisdiction_name, email) records.
        report_month:  The most recently imported voucher month (DATE, day=1).
        db_conn:       An open psycopg2 connection (caller owns lifecycle).
        settings:      Email delivery settings; loaded from env if omitted.

    Returns:
        A SendReportsResult with per-run counts and any per-recipient errors.
    """
    if settings is None:
        settings = load_email_settings()

    result = SendReportsResult(report_month=report_month)

    cur = db_conn.cursor(cursor_factory=_get_dict_cursor_factory())

    for recipient in recipients:
        result.attempted += 1
        try:
            report_data = build_report_data(
                cur=cur,
                copo=recipient.copo,
                jurisdiction_name=recipient.jurisdiction_name,
                report_month=report_month,
                base_url=settings.base_url,
            )

            if not report_data.present_tax_types:
                result.skipped_no_data += 1
                logger.info(
                    "Skipped report for %s (%s): no ledger data.",
                    recipient.jurisdiction_name,
                    recipient.copo,
                )
                continue

            deliver_report(
                settings=settings,
                recipient=recipient.email,
                report_data=report_data,
            )
            result.sent += 1

        except Exception as exc:
            result.failed += 1
            result.errors.append({
                "copo": recipient.copo,
                "email": recipient.email,
                "error": str(exc),
            })
            logger.exception(
                "Error preparing report for %s (%s) to %s.",
                recipient.jurisdiction_name,
                recipient.copo,
                recipient.email,
            )

    cur.close()

    logger.info(
        "Report dispatch complete for %s: %d sent, %d skipped (no data), %d failed of %d attempted.",
        report_month.isoformat(),
        result.sent,
        result.skipped_no_data,
        result.failed,
        result.attempted,
    )
    return result


def _get_dict_cursor_factory():
    """Return the psycopg2 RealDictCursor factory."""
    import psycopg2.extras
    return psycopg2.extras.RealDictCursor
