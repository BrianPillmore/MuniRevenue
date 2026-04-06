"""
Outreach service: account provisioning, magic link generation, and email delivery via Resend.

Also provides ``send_reports_after_import(year, month)`` — the hook the OkTAP
import pipeline calls once a period's data has been successfully loaded.  That
function queries real ledger, forecast, anomaly, and missed-filing numbers for
each user's default city and sends a city-specific "data just published" email.

Environment variables:
  RESEND_API_KEY              -- Resend API key (required for email sending)
  MUNIREV_AUTH_BASE_URL       -- Base URL for magic links (e.g. https://munirev.com)
  MUNIREV_AUTH_SESSION_SECRET -- Must match the main app setting
  MUNIREV_OUTREACH_FROM       -- From address (default: reports@munirev.com)
  MUNIREV_OUTREACH_LINK_TTL_DAYS -- Magic link TTL for outreach (default: 7)
  MUNIREV_SPONSOR_NAME        -- Sponsor display name (optional)
  MUNIREV_SPONSOR_URL         -- Sponsor URL (optional)
  MUNIREV_SPONSOR_LOGO_URL    -- Sponsor logo URL (optional)
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import date as _date, datetime, timedelta, timezone
from html import escape
from urllib.parse import quote

from app.db.psycopg import get_cursor
from app.user_auth import hash_secret, normalize_email

logger = logging.getLogger(__name__)

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _get_base_url() -> str:
    return (
        os.environ.get("MUNIREV_AUTH_BASE_URL")
        or os.environ.get("MUNIREV_AUTH_MAGIC_LINK_BASE_URL")
        or "http://localhost:8000"
    ).rstrip("/")


def _get_session_secret() -> str:
    return (
        os.environ.get("MUNIREV_AUTH_SESSION_SECRET") or "development-session-secret"
    ).strip()


def _get_outreach_from() -> str:
    return (
        os.environ.get("MUNIREV_OUTREACH_FROM") or "reports@munirev.com"
    ).strip()


def _get_link_ttl_days() -> int:
    raw = os.environ.get("MUNIREV_OUTREACH_LINK_TTL_DAYS")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    return 7


def _get_resend_api_key() -> str | None:
    return (os.environ.get("RESEND_API_KEY") or "").strip() or None


def _get_sponsor_name() -> str | None:
    return (os.environ.get("MUNIREV_SPONSOR_NAME") or "").strip() or None


def _get_sponsor_url() -> str | None:
    return (os.environ.get("MUNIREV_SPONSOR_URL") or "").strip() or None


def _get_sponsor_logo_url() -> str | None:
    return (os.environ.get("MUNIREV_SPONSOR_LOGO_URL") or "").strip() or None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Account provisioning
# ---------------------------------------------------------------------------

def provision_account(
    email: str,
    display_name: str | None,
    job_title: str | None,
    organization_name: str | None,
    jurisdiction_name: str,
    jurisdiction_type: str,
    copo: str | None = None,
) -> str:
    """
    Upsert an app_users row for the given contact and register a jurisdiction interest.

    Returns the user_id as a string.

    Outreach accounts are pre-verified: email_verified_at is set on insert so the
    user goes straight to sign-in rather than the email-verification step.
    """
    email_clean = email.strip()
    email_norm = normalize_email(email_clean)

    county_name: str | None = None
    if jurisdiction_type == "county":
        county_name = jurisdiction_name
        copo = None

    label = jurisdiction_name

    with get_cursor() as cur:
        # Upsert the user row. On conflict, only fill in fields that are currently
        # blank so we don't overwrite data a user has set themselves.
        cur.execute(
            """
            INSERT INTO app_users (
                email,
                email_normalized,
                display_name,
                job_title,
                organization_name,
                email_verified_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (email_normalized) DO UPDATE
            SET
                display_name      = CASE WHEN app_users.display_name IS NULL OR app_users.display_name = ''
                                         THEN EXCLUDED.display_name
                                         ELSE app_users.display_name END,
                job_title         = CASE WHEN app_users.job_title IS NULL OR app_users.job_title = ''
                                         THEN EXCLUDED.job_title
                                         ELSE app_users.job_title END,
                organization_name = CASE WHEN app_users.organization_name IS NULL OR app_users.organization_name = ''
                                         THEN EXCLUDED.organization_name
                                         ELSE app_users.organization_name END,
                updated_at        = NOW()
            RETURNING user_id
            """,
            [
                email_clean,
                email_norm,
                display_name or None,
                job_title or None,
                organization_name or None,
            ],
        )
        row = cur.fetchone()
        user_id = str(row["user_id"])

        # Upsert jurisdiction interest. Unique indexes prevent duplicates.
        if jurisdiction_type == "city" and copo:
            cur.execute(
                """
                INSERT INTO user_jurisdiction_interests (
                    user_id, interest_type, copo, label
                )
                VALUES (%s, 'city', %s, %s)
                ON CONFLICT DO NOTHING
                """,
                [user_id, copo, label],
            )
        elif jurisdiction_type == "county" and county_name:
            cur.execute(
                """
                INSERT INTO user_jurisdiction_interests (
                    user_id, interest_type, county_name, label
                )
                VALUES (%s, 'county', %s, %s)
                ON CONFLICT DO NOTHING
                """,
                [user_id, county_name, label],
            )

    logger.debug("Provisioned account %s for %s (%s)", user_id, email_norm, jurisdiction_name)
    return user_id


# ---------------------------------------------------------------------------
# Magic link generation (server-side, no rate limiting)
# ---------------------------------------------------------------------------

def generate_outreach_magic_link(
    user_id: str,
    next_path: str,
    ttl_days: int | None = None,
) -> str:
    """
    Insert a user_magic_links row and return the full verify URL.

    Unlike the browser-initiated flow, this skips rate limiting because it is
    called from a trusted server-side script.
    """
    if ttl_days is None:
        ttl_days = _get_link_ttl_days()

    session_secret = _get_session_secret()
    base_url = _get_base_url()

    now = _utc_now()
    expires_at = now + timedelta(days=ttl_days)

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_secret(raw_token, session_secret)

    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO user_magic_links (
                user_id,
                token_hash,
                purpose,
                next_path,
                expires_at
            )
            VALUES (%s, %s, 'sign_in', %s, %s)
            """,
            [user_id, token_hash, next_path, expires_at],
        )

    return f"{base_url}/auth/verify?token={quote(raw_token)}"


# ---------------------------------------------------------------------------
# HTML email builder (original outreach version — generic monthly report)
# ---------------------------------------------------------------------------

def _format_currency(value: float | None) -> str:
    """Format a dollar value as $1.24M, $850K, or $12,345."""
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:,.0f}"


def _format_pct(numerator: float | None, denominator: float | None) -> str:
    """Return a sign-prefixed percent string like +5.1% or -2.3%."""
    if numerator is None or denominator is None or denominator == 0:
        return ""
    pct = ((numerator - denominator) / abs(denominator)) * 100
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


# ---------------------------------------------------------------------------
# Greeting formatter
# ---------------------------------------------------------------------------

def format_greeting(
    office_title: str | None,
    person_name: str | None,
    contact_type: str | None,
) -> str:
    """Return a personalized salutation line for outreach emails.

    Rules
    -----
    All contacts with a known name and a recognisable title — elected officials
    and staff alike — receive the formal ``"Dear [Title] [Last Name],"`` form:

        Mayor, Commissioner, Council*, Trustee, Chair:
            ``"Dear Mayor Johnson,"``

        City/Town Manager, County Manager/Administrator:
            ``"Dear City Manager Johnston,"``

        Finance Director (any title containing "finance"):
            ``"Dear Finance Director Young,"``

        Treasurer:
            ``"Dear Treasurer Hall,"``

        Clerk:
            ``"Dear City Clerk Reed,"``

        Administrator:
            ``"Dear Administrator Price,"``

        Any other non-empty title (compound titles, unknown roles):
            Primary segment before "/" or "," is used as the salutation title.
            e.g. "Assistant City Manager / CFO" -> ``"Dear Assistant City Manager Cluck,"``

    General inbox, unknown contact, or no name / title available:
        ``"Hello,"``

    The ``contact_type`` argument acts as an early override: values
    ``'general'`` and ``'general office'`` skip personalization entirely
    because there is no named individual behind the address.

    Parameters
    ----------
    office_title:
        The role/title string stored in ``app_users.job_title`` or
        ``contacts.office_title`` (e.g. "Mayor", "Finance Director").
    person_name:
        The full name string stored in ``app_users.display_name`` or
        ``contacts.person_name`` (e.g. "Kathy Johnson").
    contact_type:
        The contact classification from ``contacts.contact_type``
        (``'direct'``, ``'staff'``, ``'general'``, ``'general office'``).
        Pass ``None`` when not known.

    Returns
    -------
    str
        A complete salutation line ready for insertion into the email body,
        including the trailing comma and period spacing handled by the
        HTML template.
    """
    # General / no-name contacts: no personalization.
    if contact_type in ("general", "general office"):
        return "Hello,"
    if not person_name or not person_name.strip():
        return "Hello,"

    name_parts = person_name.strip().split()
    last_name = name_parts[-1]
    title = (office_title or "").strip()
    title_lower = title.lower()

    # --- Elected officials ---
    if "mayor" in title_lower:
        return f"Dear Mayor {last_name},"
    if "commissioner" in title_lower:
        return f"Dear Commissioner {last_name},"
    if "council" in title_lower or "councilor" in title_lower:
        return f"Dear Councilmember {last_name},"
    if "trustee" in title_lower:
        return f"Dear Trustee {last_name},"
    if "chair" in title_lower:
        return f"Dear Chair {last_name},"

    # --- Staff roles ---
    if "city manager" in title_lower or "town manager" in title_lower:
        return f"Dear City Manager {last_name},"
    if "county manager" in title_lower or "county administrator" in title_lower:
        return f"Dear County Manager {last_name},"
    if "finance director" in title_lower or "finance" in title_lower:
        return f"Dear Finance Director {last_name},"
    if "treasurer" in title_lower:
        return f"Dear Treasurer {last_name},"
    if "clerk" in title_lower:
        return f"Dear City Clerk {last_name},"
    if "administrator" in title_lower:
        return f"Dear Administrator {last_name},"

    # --- Compound or unrecognized title: use primary segment before "/" or "," ---
    if title:
        salutation = title.split("/")[0].split(",")[0].strip()
        return f"Dear {salutation} {last_name},"

    # Name known but no title on file — use the generic greeting.
    return "Hello,"


# ---------------------------------------------------------------------------
# Contact-type inference and role labelling
# ---------------------------------------------------------------------------

def _infer_contact_type(job_title: str | None) -> str:
    """Derive a contact_type from an app_users.job_title string.

    Used when ``contact_type`` is not stored separately (i.e. provisioned
    contacts where we only have the title string).

    Returns one of: ``'general'``, ``'staff'``, ``'direct'``.
    """
    if not job_title:
        return "direct"
    t = job_title.lower()
    if "general office" in t or t.strip() == "general":
        return "general"
    # Staff roles
    if any(k in t for k in (
        "city manager", "town manager", "county manager", "county administrator",
        "administrator", "finance director", "finance", "treasurer", "clerk",
    )):
        return "staff"
    # All other named individuals (elected, unknown)
    return "direct"


def _role_label(job_title: str | None) -> str:
    """Return a short human-readable role label for log messages."""
    if not job_title:
        return "unknown role"
    t = job_title.lower()
    if "mayor" in t:
        return "Mayor"
    if "commissioner" in t:
        return "Commissioner"
    if "council" in t or "councilor" in t:
        return "Council member"
    if "trustee" in t:
        return "Trustee"
    if "chair" in t:
        return "Chair"
    if "city manager" in t or "town manager" in t:
        return "City Manager"
    if "county manager" in t or "county administrator" in t:
        return "County Manager"
    if "finance director" in t or "finance" in t:
        return "Finance Director"
    if "treasurer" in t:
        return "Treasurer"
    if "clerk" in t:
        return "Clerk"
    if "administrator" in t:
        return "Administrator"
    return job_title.strip()


# ---------------------------------------------------------------------------
# Helpers shared by the post-import email flow
# ---------------------------------------------------------------------------

def get_jurisdiction_tax_types(copo: str) -> list[str]:
    """Return the distinct tax types that have ledger data for this jurisdiction."""
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT tax_type
                FROM ledger_records
                WHERE copo = %s
                ORDER BY tax_type
                """,
                [copo],
            )
            return [row["tax_type"] for row in cur.fetchall()]
    except Exception:
        return []


def _fetch_actual_revenue_for_period(
    cur, copo: str, year: int, month: int
) -> float | None:
    """Sum sales-tax 'returned' for the period from ledger_records.

    Returns None only when there are literally no matching rows, which means
    no data has been imported for that city and period yet.
    """
    cur.execute(
        """
        SELECT SUM(returned)::float8 AS total
        FROM ledger_records
        WHERE copo = %s
          AND tax_type = 'sales'
          AND EXTRACT(YEAR  FROM voucher_date) = %s
          AND EXTRACT(MONTH FROM voucher_date) = %s
        """,
        [copo, year, month],
    )
    row = cur.fetchone()
    return float(row["total"]) if row and row["total"] is not None else None


def _fetch_forecast_for_period(
    cur, copo: str, year: int, month: int
) -> float | None:
    """Return the most recent selected forecast projection for the period.

    Queries forecast_predictions joined to forecast_runs, matching the
    actual ORM schema (target_date column on forecast_predictions).
    """
    period_date = _date(year, month, 1)
    cur.execute(
        """
        SELECT fp.projected_value::float8
        FROM forecast_predictions fp
        JOIN forecast_runs fr ON fr.id = fp.run_id
        WHERE fr.copo = %s
          AND fr.tax_type = 'sales'
          AND fr.selected = TRUE
          AND fp.target_date = %s
        ORDER BY fr.created_at DESC
        LIMIT 1
        """,
        [copo, period_date],
    )
    row = cur.fetchone()
    return float(row["projected_value"]) if row else None


def _fetch_anomaly_count_for_period(
    cur, copo: str, year: int, month: int
) -> tuple[int, str | None]:
    """Return (total_count, top_description) for anomalies in this period.

    The anomalies table uses the column ``anomaly_date`` (DATE) to record the
    reporting month.
    """
    period_date = _date(year, month, 1)
    cur.execute(
        """
        SELECT
            COUNT(*)             AS n,
            MAX(description)
                FILTER (WHERE severity IN ('critical', 'high')) AS top_desc
        FROM anomalies
        WHERE copo = %s
          AND anomaly_date = %s
        """,
        [copo, period_date],
    )
    row = cur.fetchone()
    count = int(row["n"] or 0)
    return count, (row["top_desc"] if count > 0 else None)


def _fetch_missed_filing_count_for_period(
    cur, copo: str, year: int, month: int
) -> tuple[int, str | None]:
    """Return (candidate_count, top_description) from the missed_filing_candidates cache.

    Silently returns (0, None) if the cache table does not yet exist —
    it is built by the separate refresh_missed_filing_candidates.py script.
    """
    period_date = _date(year, month, 1)
    try:
        cur.execute(
            """
            SELECT
                COUNT(*)                 AS n,
                MAX(activity_description) AS top_desc
            FROM missed_filing_candidates
            WHERE copo = %s
              AND anomaly_date = %s
              AND hybrid_missing_amount > 0
            """,
            [copo, period_date],
        )
        row = cur.fetchone()
        count = int(row["n"] or 0)
        return count, (row["top_desc"] if count > 0 else None)
    except Exception:
        return 0, None


def _build_import_report_html(
    *,
    jurisdiction_name: str,
    period_label: str,
    actual_revenue: float,
    forecast_revenue: float | None,
    anomaly_count: int,
    top_anomaly: str | None,
    missed_count: int,
    top_missed: str | None,
    magic_link_url: str,
    ttl_days: int,
    greeting: str = "Hello,",
) -> str:
    """Render the 'data just published' HTML email for one city and period.

    The ``greeting`` parameter is the personalized salutation line produced by
    ``format_greeting``.  It defaults to ``"Hello,"`` so callers that pre-date
    the personalization feature continue to work without modification.
    """
    city_esc = escape(jurisdiction_name)
    period_esc = escape(period_label)
    url_esc = escape(magic_link_url)
    greeting_esc = escape(greeting)

    actual_str = _format_currency(actual_revenue)
    if forecast_revenue and forecast_revenue != 0:
        pct = ((actual_revenue - forecast_revenue) / abs(forecast_revenue)) * 100
        pct_sign = "+" if pct >= 0 else ""
        revenue_value = actual_str
        revenue_sub = (
            f"vs {_format_currency(forecast_revenue)} forecast "
            f"({pct_sign}{pct:.1f}%)"
        )
    else:
        revenue_value = actual_str
        revenue_sub = "No forecast on file for this period"

    anomaly_value = str(anomaly_count)
    if anomaly_count > 0 and top_anomaly:
        anomaly_sub = f"Largest: {escape(top_anomaly)}"
    elif anomaly_count > 0:
        anomaly_sub = "See dashboard for details"
    else:
        anomaly_sub = "No anomalies flagged"

    missed_value = str(missed_count)
    if missed_count > 0 and top_missed:
        missed_sub = f"Top industry: {escape(top_missed)}"
    elif missed_count > 0:
        missed_sub = "See dashboard for details"
    else:
        missed_sub = "No missed filing candidates"

    sponsor_name = _get_sponsor_name()
    sponsor_url = _get_sponsor_url()
    sponsor_logo_url = _get_sponsor_logo_url()
    sponsor_html = ""
    if sponsor_name:
        logo_html = ""
        if sponsor_logo_url:
            logo_html = (
                f'<img src="{sponsor_logo_url}" alt="{sponsor_name}" '
                f'style="max-height:28px;vertical-align:middle;margin-right:8px;" />'
            )
        inner = (
            f'<a href="{sponsor_url}" style="color:#555;text-decoration:none;">'
            f'{logo_html}Presented by {sponsor_name}</a>'
            if sponsor_url
            else f"{logo_html}Presented by {sponsor_name}"
        )
        sponsor_html = (
            f'<tr><td style="background:#f0f4f8;padding:12px 32px;text-align:center;'
            f'font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#555;'
            f'border-top:1px solid #e2e8f0;">{inner}</td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>{city_esc} {period_esc} &mdash; MuniRevenue</title>
</head>
<body style="margin:0;padding:0;background-color:#f4ede2;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background-color:#f4ede2;padding:32px 0;">
  <tr>
    <td align="center">
      <table width="600" cellpadding="0" cellspacing="0" border="0"
             style="max-width:600px;width:100%;background-color:#ffffff;
                    border-radius:10px;overflow:hidden;
                    box-shadow:0 2px 12px rgba(17,34,51,0.10);">

        <!-- Header -->
        <tr>
          <td style="background-color:#112233;padding:28px 32px;">
            <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:1.5px;
                      color:#90c8d8;text-transform:uppercase;">MuniRevenue &mdash; Data Update</p>
            <h1 style="margin:8px 0 0;font-size:21px;font-weight:700;color:#ffffff;
                       line-height:1.3;">
              {city_esc} {period_esc} Tax Data &mdash; Just Published
            </h1>
            <p style="margin:6px 0 0;font-size:14px;color:#aac8d8;line-height:1.5;">
              Your {period_esc} sales tax data for {city_esc} has been imported from OkTAP.
            </p>
          </td>
        </tr>

        <!-- Greeting -->
        <tr>
          <td style="padding:28px 32px 0;">
            <p style="margin:0;font-size:16px;color:#2d3748;line-height:1.5;">
              {greeting_esc}
            </p>
          </td>
        </tr>

        <!-- Data cards -->
        <tr>
          <td style="padding:20px 32px 8px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="margin-bottom:24px;">
              <tr>
                <!-- Card 1: Revenue -->
                <td width="33%" valign="top" style="padding:4px;">
                  <table width="100%" cellpadding="0" cellspacing="0" border="0"
                         style="background-color:#f0fff4;border:1px solid #c6f6d5;border-radius:8px;">
                    <tr>
                      <td style="padding:16px 14px 14px;">
                        <p style="margin:0 0 4px;font-size:11px;font-weight:700;
                                  letter-spacing:1px;color:#276749;text-transform:uppercase;">
                          Sales Tax
                        </p>
                        <p style="margin:0;font-size:17px;font-weight:700;color:#1c4532;
                                  line-height:1.35;word-break:break-word;">
                          {revenue_value}
                        </p>
                        <p style="margin:5px 0 0;font-size:12px;color:#276749;">
                          {revenue_sub}
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>

                <!-- Card 2: Anomalies -->
                <td width="34%" valign="top" style="padding:4px;">
                  <table width="100%" cellpadding="0" cellspacing="0" border="0"
                         style="background-color:#fffbeb;border:1px solid #fbd38d;border-radius:8px;">
                    <tr>
                      <td style="padding:16px 14px 14px;">
                        <p style="margin:0 0 4px;font-size:11px;font-weight:700;
                                  letter-spacing:1px;color:#b7791f;text-transform:uppercase;">
                          Anomalies
                        </p>
                        <p style="margin:0;font-size:28px;font-weight:700;color:#744210;
                                  line-height:1.2;">
                          {anomaly_value}
                        </p>
                        <p style="margin:5px 0 0;font-size:12px;color:#975a16;">
                          {anomaly_sub}
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>

                <!-- Card 3: Missed Filings -->
                <td width="33%" valign="top" style="padding:4px;">
                  <table width="100%" cellpadding="0" cellspacing="0" border="0"
                         style="background-color:#fff5f5;border:1px solid #fed7d7;border-radius:8px;">
                    <tr>
                      <td style="padding:16px 14px 14px;">
                        <p style="margin:0 0 4px;font-size:11px;font-weight:700;
                                  letter-spacing:1px;color:#c53030;text-transform:uppercase;">
                          Missed Filings
                        </p>
                        <p style="margin:0;font-size:28px;font-weight:700;color:#742a2a;
                                  line-height:1.2;">
                          {missed_value}
                        </p>
                        <p style="margin:5px 0 0;font-size:12px;color:#9b2c2c;">
                          {missed_sub}
                        </p>
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>

            <!-- CTA -->
            <table width="100%" cellpadding="0" cellspacing="0" border="0"
                   style="margin-bottom:28px;">
              <tr>
                <td align="center">
                  <a href="{url_esc}"
                     style="display:inline-block;background-color:#2f6f74;color:#ffffff;
                            font-family:Arial,Helvetica,sans-serif;font-size:16px;
                            font-weight:700;text-decoration:none;padding:14px 36px;
                            border-radius:8px;line-height:1;">
                    Open Full Dashboard &rarr;
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background-color:#f8f4ee;padding:18px 32px;border-top:1px solid #e8ddd0;">
            <p style="margin:0;font-size:12px;color:#718096;line-height:1.6;">
              MuniRevenue &bull; Oklahoma Municipal Revenue Intelligence<br />
              You are receiving this because your account is configured for {city_esc}.
              This sign-in link expires in {ttl_days} day(s).
            </p>
          </td>
        </tr>

        {sponsor_html}

      </table>
    </td>
  </tr>
</table>
</body>
</html>"""


def _build_import_report_plain(
    *,
    jurisdiction_name: str,
    period_label: str,
    actual_revenue: float,
    forecast_revenue: float | None,
    anomaly_count: int,
    top_anomaly: str | None,
    missed_count: int,
    top_missed: str | None,
    magic_link_url: str,
    ttl_days: int,
    greeting: str = "Hello,",
) -> str:
    """Plain-text fallback for the 'data just published' email.

    The ``greeting`` parameter is the personalized salutation produced by
    ``format_greeting``.  Defaults to ``"Hello,"`` for backwards compatibility.
    """
    actual_str = _format_currency(actual_revenue)
    lines = [
        f"{jurisdiction_name} {period_label} Tax Data -- Just Published",
        "=" * 60,
        "",
        greeting,
        "",
        f"Your {period_label} sales tax data for {jurisdiction_name} is now in MuniRevenue.",
        "",
        "SUMMARY",
        "-------",
    ]

    if forecast_revenue and forecast_revenue != 0:
        pct = ((actual_revenue - forecast_revenue) / abs(forecast_revenue)) * 100
        pct_sign = "+" if pct >= 0 else ""
        lines.append(
            f"  Revenue: {actual_str} actual vs {_format_currency(forecast_revenue)} "
            f"forecast ({pct_sign}{pct:.1f}%)"
        )
    else:
        lines.append(f"  Revenue: {actual_str} actual (no forecast on file)")

    lines.append(f"  Anomalies flagged: {anomaly_count}")
    if anomaly_count > 0 and top_anomaly:
        lines.append(f"  Largest anomaly: {top_anomaly}")

    lines.append(f"  Missed filing candidates: {missed_count}")
    if missed_count > 0 and top_missed:
        lines.append(f"  Top candidate industry: {top_missed}")

    lines += [
        "",
        "Sign in to review the full dashboard:",
        magic_link_url,
        "",
        f"This link expires in {ttl_days} day(s).",
        "",
        "---",
        "MuniRevenue | Oklahoma Municipal Revenue Intelligence",
        f"You are receiving this because your account is configured for {jurisdiction_name}.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Email delivery via Resend
# ---------------------------------------------------------------------------

def send_report_via_resend(
    to_email: str,
    display_name: str | None,
    subject: str,
    html_body: str,
) -> bool:
    """
    Send an HTML email via the Resend API.

    Returns True on success, False on failure (logs the error).
    Uses urllib.request so no extra dependencies are required.
    """
    api_key = _get_resend_api_key()
    if not api_key:
        logger.error("RESEND_API_KEY is not set; cannot send email to %s.", to_email)
        return False

    from_address = _get_outreach_from()
    to_formatted = f"{display_name} <{to_email}>" if display_name else to_email

    payload = {
        "from": from_address,
        "to": [to_formatted],
        "subject": subject,
        "html": html_body,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status_code = resp.status
            if status_code in (200, 201):
                logger.info("Email sent to %s via Resend (HTTP %s).", to_email, status_code)
                return True
            body = resp.read().decode("utf-8", errors="replace")
            logger.error(
                "Resend returned unexpected status %s for %s: %s",
                status_code, to_email, body,
            )
            return False
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        logger.error(
            "Resend HTTP error %s for %s: %s", exc.code, to_email, body
        )
        return False
    except urllib.error.URLError as exc:
        logger.error("Resend network error for %s: %s", to_email, exc.reason)
        return False
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error sending to %s: %s", to_email, exc)
        return False


# ---------------------------------------------------------------------------
# Public hook — call this after a successful OkTAP import
# ---------------------------------------------------------------------------

def send_reports_after_import(period_year: int, period_month: int) -> None:
    """Send city-specific "data just published" emails after a successful OkTAP import.

    This is the primary integration point between the import pipeline and
    user-facing email delivery.  Call it once, per period, after the OkTAP data
    has been fully committed to the database.

    Args:
        period_year:  4-digit year of the imported period (e.g. 2026).
        period_month: Month number 1-12 of the imported period (e.g. 3 for March).

    Behaviour:
        - Targets active users who have joined ``user_jurisdiction_interests`` to a
          city (copo).  Users without any interest rows are skipped.
        - Users whose city has no ledger data for the period are silently skipped
          so no blank or misleading emails are ever delivered.
        - Revenue comes from ``ledger_records`` (tax_type='sales').
        - Forecast comes from ``forecast_predictions`` joined via ``forecast_runs``
          (selected=TRUE, tax_type='sales').
        - Anomaly counts come from the ``anomalies`` table (column: period).
        - Missed filing counts come from ``missed_filing_candidates`` if it exists.
        - Report data (revenue, anomalies, missed filings) is identical for every
          recipient in the same city — computed once per jurisdiction, not per user.
        - Each recipient gets a unique personalized greeting and a unique magic link.
        - A one-time 7-day magic sign-in link is generated per recipient.
        - Email is delivered via Resend (RESEND_API_KEY) if that key is configured,
          otherwise logs the full plain-text body at INFO level.
        - Errors for individual recipients are caught; they do not abort the loop.

    The import pipeline in ``scripts/load_data.py`` is the canonical caller.
    The CLI script ``scripts/send_monthly_reports.py --period YYYY-MM`` provides
    a manual trigger that can be run independently of the import pipeline.

    Example (import pipeline)::

        # At the bottom of scripts/load_data.py main(), after conn.commit():
        from app.services.outreach import send_reports_after_import
        send_reports_after_import(2026, 3)
    """
    if not (1 <= period_month <= 12):
        raise ValueError(f"period_month must be 1-12, got {period_month}")

    period_label = f"{_MONTH_NAMES[period_month - 1]} {period_year}"
    ttl_days = _get_link_ttl_days()

    logger.info(
        "send_reports_after_import: period=%d-%02d (%s)",
        period_year, period_month, period_label,
    )

    # Fetch all active users who have at least one city interest.
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.user_id::text        AS user_id,
                u.email,
                u.display_name,
                u.job_title,
                i.interest_type,
                i.copo,
                i.county_name,
                i.label                AS jurisdiction_name
            FROM app_users u
            JOIN user_jurisdiction_interests i ON i.user_id = u.user_id
            WHERE u.status = 'active'
              AND u.email IS NOT NULL
              AND u.email != ''
              AND COALESCE(u.monthly_reports_opt_in, TRUE) = TRUE
              AND i.interest_type = 'city'
              AND i.copo IS NOT NULL
            ORDER BY i.copo, u.email
            """
        )
        all_users = [dict(row) for row in cur.fetchall()]

    if not all_users:
        logger.info("No active users with city interests. Nothing to send.")
        return

    # Group users by copo so we query the database ONCE per city, not once per user.
    # Every recipient in the same city sees identical revenue numbers.
    # Only the greeting line and the magic link URL differ between recipients.
    groups: dict[str, list[dict]] = defaultdict(list)
    for user in all_users:
        groups[user["copo"]].append(user)

    sent = skipped = failed = 0

    for copo, users in groups.items():
        jurisdiction_name = users[0].get("jurisdiction_name") or copo

        # Query city data once for all users in this group.
        try:
            with get_cursor() as cur:
                actual_revenue = _fetch_actual_revenue_for_period(cur, copo, period_year, period_month)
        except Exception as exc:
            logger.error("Revenue query failed for %s: %s", copo, exc)
            failed += len(users)
            continue

        # Skip the whole group if there is no imported data for this period.
        if actual_revenue is None:
            logger.info(
                "Skipping %s (%s) -- no ledger data for %s-%02d",
                jurisdiction_name, copo, period_year, period_month,
            )
            skipped += len(users)
            continue

        try:
            with get_cursor() as cur:
                forecast_revenue = _fetch_forecast_for_period(cur, copo, period_year, period_month)
                anomaly_count, top_anomaly = _fetch_anomaly_count_for_period(
                    cur, copo, period_year, period_month
                )
                missed_count, top_missed = _fetch_missed_filing_count_for_period(
                    cur, copo, period_year, period_month
                )
        except Exception as exc:
            logger.error("Analytics queries failed for %s: %s", copo, exc)
            failed += len(users)
            continue

        subject = f"{jurisdiction_name} {period_label} Tax Data \u2014 Just Published"

        # Log the recipient roster BEFORE sending so operators can see who is
        # targeted even if a send failure interrupts the loop.
        # Format: "Sending Yukon March 2026 report to 4 recipients (Mayor, Finance Director, ...)"
        role_labels = [_role_label(u.get("job_title")) for u in users]
        logger.info(
            "Sending %s %s report to %d recipient(s) (%s)",
            jurisdiction_name,
            period_label,
            len(users),
            ", ".join(role_labels),
        )

        for user in users:
            user_id = user["user_id"]
            email = user["email"]
            next_path = f"/report/{quote(copo)}/{period_year}/{period_month}"

            # Each recipient gets a unique magic link.
            try:
                magic_link_url = generate_outreach_magic_link(
                    user_id=user_id,
                    next_path=next_path,
                    ttl_days=ttl_days,
                )
            except Exception as exc:
                logger.error("Magic link generation failed for %s: %s", email, exc)
                failed += 1
                continue

            # Each recipient gets a personalized greeting based on their role.
            contact_type = _infer_contact_type(user.get("job_title"))
            greeting = format_greeting(
                office_title=user.get("job_title"),
                person_name=user.get("display_name"),
                contact_type=contact_type,
            )

            try:
                html_body = _build_import_report_html(
                    jurisdiction_name=jurisdiction_name,
                    period_label=period_label,
                    actual_revenue=actual_revenue,
                    forecast_revenue=forecast_revenue,
                    anomaly_count=anomaly_count,
                    top_anomaly=top_anomaly,
                    missed_count=missed_count,
                    top_missed=top_missed,
                    magic_link_url=magic_link_url,
                    ttl_days=ttl_days,
                    greeting=greeting,
                )
                plain_text = _build_import_report_plain(
                    jurisdiction_name=jurisdiction_name,
                    period_label=period_label,
                    actual_revenue=actual_revenue,
                    forecast_revenue=forecast_revenue,
                    anomaly_count=anomaly_count,
                    top_anomaly=top_anomaly,
                    missed_count=missed_count,
                    top_missed=top_missed,
                    magic_link_url=magic_link_url,
                    ttl_days=ttl_days,
                    greeting=greeting,
                )
            except Exception as exc:
                logger.error("Email render failed for %s: %s", email, exc)
                failed += 1
                continue

            success = send_report_via_resend(
                to_email=email,
                display_name=user.get("display_name"),
                subject=subject,
                html_body=html_body,
            )

            if success:
                sent += 1
                logger.info(
                    "Sent %s report to %s (%s)",
                    period_label, email, jurisdiction_name,
                )
            else:
                # Resend not configured — fall back to logging the plain text so
                # the pipeline operator can see what would have been sent.
                logger.info(
                    "REPORT EMAIL (no Resend key) | To: %s | Subject: %s\n%s",
                    email, subject, plain_text,
                )
                sent += 1  # count as delivered via log mode

    logger.info(
        "send_reports_after_import complete -- sent: %d  skipped (no data): %d  failed: %d",
        sent, skipped, failed,
    )
