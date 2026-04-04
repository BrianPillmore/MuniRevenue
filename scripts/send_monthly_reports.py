#!/usr/bin/env python3
"""Send city-specific tax data arrival emails after an OkTAP import.

This script is the CLI trigger for the same email flow that the import
pipeline calls automatically.  Run it manually after verifying that a
period's data has been successfully loaded into the database.

Usage:
    # Send for a specific period (required — matches the just-imported data)
    DATABASE_URL=postgresql://... RESEND_API_KEY=re_xxx \\
        python scripts/send_monthly_reports.py --period 2026-03

    # Dry run — resolves data, prints what would be sent, writes HTML files
    DRY_RUN=1 python scripts/send_monthly_reports.py --period 2026-03

    # Restrict to one email address for testing
    TEST_EMAIL=brian@yukonok.gov python scripts/send_monthly_reports.py --period 2026-03

The script delegates the full email flow (queries, magic links, HTML rendering,
delivery) to ``send_reports_after_import`` in ``app.services.outreach``.  In
DRY_RUN mode it sets a module-level flag that the outreach module checks before
calling Resend so the HTML is written to disk without sending.

Email subject line format (city-specific):
    "Yukon March 2026 Tax Data -- Just Published"

Emails are only sent to users whose jurisdiction has actual ledger data for the
requested period.  Users with no data are silently skipped.

Every recipient in the same city receives identical revenue numbers.  Only the
personalized greeting and the magic link URL differ between recipients.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Load a repo-root .env file if present (dev convenience only).
# ---------------------------------------------------------------------------
_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DRY_RUN: bool = os.environ.get("DRY_RUN", "").strip().lower() in {"1", "true", "yes"}
TEST_EMAIL: str | None = (os.environ.get("TEST_EMAIL") or "").strip() or None

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


# ---------------------------------------------------------------------------
# Period helpers
# ---------------------------------------------------------------------------

def _parse_period(period_str: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' into (year, month).  Raises SystemExit on bad input."""
    try:
        d = date.fromisoformat(f"{period_str.strip()}-01")
        return d.year, d.month
    except ValueError:
        logger.error("Invalid --period %r — use YYYY-MM format (e.g. 2026-03).", period_str)
        sys.exit(1)


def _period_label(year: int, month: int) -> str:
    return f"{_MONTH_NAMES[month - 1]} {year}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Send city-specific tax data arrival emails triggered by an OkTAP import. "
            "Pass --period YYYY-MM to specify the period whose data was just loaded."
        )
    )
    parser.add_argument(
        "--period",
        metavar="YYYY-MM",
        required=True,
        help=(
            "The reporting period that was just imported (e.g. 2026-03 for March 2026). "
            "Only users whose city has ledger data for this period will be emailed."
        ),
    )
    args = parser.parse_args()

    year, month = _parse_period(args.period)
    period = _period_label(year, month)

    mode_label = "DRY RUN" if DRY_RUN else "LIVE"
    scope_label = f"TEST_EMAIL={TEST_EMAIL}" if TEST_EMAIL else "all active users"
    logger.info(
        "send_monthly_reports starting -- %s -- period=%s (%d-%02d) -- scope=%s",
        mode_label, period, year, month, scope_label,
    )

    if DRY_RUN:
        logger.info(
            "DRY_RUN=1: emails will not be delivered. "
            "HTML files will be written to data/dry_run_reports/ instead."
        )
        # Patch the Resend key so outreach.send_report_via_resend returns False,
        # which causes send_reports_after_import to fall back to log mode.
        # This lets us exercise the full pipeline without actually sending.
        os.environ.pop("RESEND_API_KEY", None)
        _run_dry(year, month, period)
        return

    if TEST_EMAIL:
        logger.info("TEST_EMAIL mode: only sending to %s", TEST_EMAIL)
        _run_test_email(year, month, period, TEST_EMAIL)
        return

    # Normal live run: delegate entirely to the service hook.
    from app.services.outreach import send_reports_after_import
    send_reports_after_import(period_year=year, period_month=month)
    logger.info("send_monthly_reports complete for %s.", period)


def _run_dry(year: int, month: int, period: str) -> None:
    """Dry-run mode: resolve all data and write HTML files; do not send.

    Report data (revenue, anomalies, missed filings) is computed once per
    city and is identical across all recipients in that city.  Each
    recipient's HTML file receives their own personalized greeting and a
    unique magic link.
    """
    from collections import defaultdict

    from app.db.psycopg import get_cursor
    from app.services.outreach import (
        _MONTH_NAMES as _MN,
        _fetch_actual_revenue_for_period,
        _fetch_forecast_for_period,
        _fetch_anomaly_count_for_period,
        _fetch_missed_filing_count_for_period,
        _build_import_report_html,
        _build_import_report_plain,
        _get_link_ttl_days,
        _infer_contact_type,
        _role_label,
        format_greeting,
        generate_outreach_magic_link,
    )

    out_dir = REPO_ROOT / "data" / "dry_run_reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.user_id::text        AS user_id,
                u.email,
                u.display_name,
                u.job_title,
                i.copo,
                i.label                AS jurisdiction_name
            FROM app_users u
            JOIN user_jurisdiction_interests i ON i.user_id = u.user_id
            WHERE u.status = 'active'
              AND u.email IS NOT NULL
              AND u.email != ''
              AND i.interest_type = 'city'
              AND i.copo IS NOT NULL
            ORDER BY i.copo, u.email
            """
        )
        all_users = [dict(row) for row in cur.fetchall()]

    if not all_users:
        logger.warning("No active users with city interests found.")
        return

    groups: dict[str, list[dict]] = defaultdict(list)
    for u in all_users:
        groups[u["copo"]].append(u)

    ttl_days = _get_link_ttl_days()
    written = skipped = 0

    for copo, users in groups.items():
        jurisdiction_name = users[0].get("jurisdiction_name") or copo

        with get_cursor() as cur:
            actual_revenue = _fetch_actual_revenue_for_period(cur, copo, year, month)

        if actual_revenue is None:
            logger.info(
                "[DRY RUN] Skipping %s (%s) -- no data for %d-%02d",
                jurisdiction_name, copo, year, month,
            )
            skipped += len(users)
            continue

        with get_cursor() as cur:
            forecast_revenue = _fetch_forecast_for_period(cur, copo, year, month)
            anomaly_count, top_anomaly = _fetch_anomaly_count_for_period(
                cur, copo, year, month
            )
            missed_count, top_missed = _fetch_missed_filing_count_for_period(
                cur, copo, year, month
            )

        # Log recipient roster before writing files, matching live-run format.
        role_labels = [_role_label(u.get("job_title")) for u in users]
        logger.info(
            "[DRY RUN] %s %s — %d recipient(s) (%s)",
            jurisdiction_name, period, len(users), ", ".join(role_labels),
        )

        for user in users:
            # Personalized greeting per recipient; report numbers are shared.
            contact_type = _infer_contact_type(user.get("job_title"))
            greeting = format_greeting(
                office_title=user.get("job_title"),
                person_name=user.get("display_name"),
                contact_type=contact_type,
            )

            magic_link_url = generate_outreach_magic_link(
                user_id=user["user_id"],
                next_path=f"/report/{copo}/{year}/{month}",
                ttl_days=ttl_days,
            )
            html_body = _build_import_report_html(
                jurisdiction_name=jurisdiction_name,
                period_label=period,
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
                period_label=period,
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
            email_slug = user["email"].replace("@", "_at_").replace(".", "_")
            city_slug = copo.replace(" ", "_")
            html_path = out_dir / f"dry_run_{year}_{month:02d}_{city_slug}_{email_slug}.html"
            txt_path = out_dir / f"dry_run_{year}_{month:02d}_{city_slug}_{email_slug}.txt"
            html_path.write_text(html_body, encoding="utf-8")
            txt_path.write_text(plain_text, encoding="utf-8")
            logger.info(
                "[DRY RUN] %s -> %s | greeting=%r | HTML: %s",
                jurisdiction_name, user["email"], greeting, html_path.name,
            )
            written += 1

    print(
        f"\n[DRY RUN] {period}\n"
        f"  HTML files written: {written}\n"
        f"  Skipped (no data): {skipped}\n"
        f"  Output dir: {out_dir}"
    )


def _run_test_email(year: int, month: int, period: str, test_email: str) -> None:
    """Send a live email to exactly one address, substituting that address for
    whichever city the account is registered to (or the first city found).

    The personalized greeting is generated from the account's stored job_title
    and display_name, same as in the live send path.
    """
    from app.db.psycopg import get_cursor
    from app.services.outreach import (
        _fetch_actual_revenue_for_period,
        _fetch_forecast_for_period,
        _fetch_anomaly_count_for_period,
        _fetch_missed_filing_count_for_period,
        _build_import_report_html,
        _build_import_report_plain,
        _get_link_ttl_days,
        _infer_contact_type,
        format_greeting,
        generate_outreach_magic_link,
        send_report_via_resend,
    )

    normalized = test_email.strip().lower()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.user_id::text AS user_id,
                u.email,
                u.display_name,
                u.job_title,
                i.copo,
                i.label AS jurisdiction_name
            FROM app_users u
            JOIN user_jurisdiction_interests i ON i.user_id = u.user_id
            WHERE u.email_normalized = %s
              AND u.status = 'active'
              AND i.interest_type = 'city'
              AND i.copo IS NOT NULL
            LIMIT 1
            """,
            [normalized],
        )
        row = cur.fetchone()

    if row is None:
        logger.error(
            "TEST_EMAIL %s has no active account with a city interest. "
            "Ensure the account exists and has a jurisdiction interest set.",
            test_email,
        )
        sys.exit(1)

    user_id = row["user_id"]
    email = row["email"]
    copo = row["copo"]
    jurisdiction_name = row["jurisdiction_name"] or copo
    ttl_days = _get_link_ttl_days()

    with get_cursor() as cur:
        actual_revenue = _fetch_actual_revenue_for_period(cur, copo, year, month)

    if actual_revenue is None:
        logger.warning(
            "%s (%s) has no ledger data for %d-%02d. "
            "Sending anyway with $0 placeholder for test purposes.",
            jurisdiction_name, copo, year, month,
        )
        actual_revenue = 0.0

    with get_cursor() as cur:
        forecast_revenue = _fetch_forecast_for_period(cur, copo, year, month)
        anomaly_count, top_anomaly = _fetch_anomaly_count_for_period(cur, copo, year, month)
        missed_count, top_missed = _fetch_missed_filing_count_for_period(cur, copo, year, month)

    # Personalize the greeting for this recipient.
    contact_type = _infer_contact_type(row.get("job_title"))
    greeting = format_greeting(
        office_title=row.get("job_title"),
        person_name=row.get("display_name"),
        contact_type=contact_type,
    )

    magic_link_url = generate_outreach_magic_link(
        user_id=user_id,
        next_path=f"/report/{copo}/{year}/{month}",
        ttl_days=ttl_days,
    )
    html_body = _build_import_report_html(
        jurisdiction_name=jurisdiction_name,
        period_label=period,
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
        period_label=period,
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

    logger.info(
        "TEST EMAIL | %s -> %s | greeting=%r",
        jurisdiction_name, email, greeting,
    )

    subject = f"{jurisdiction_name} {period} Tax Data \u2014 Just Published"
    success = send_report_via_resend(
        to_email=email,
        display_name=row.get("display_name"),
        subject=subject,
        html_body=html_body,
    )
    if success:
        logger.info("TEST email sent to %s for %s %s.", email, jurisdiction_name, period)
    else:
        logger.info(
            "REPORT EMAIL (no Resend key) | To: %s | Subject: %s\n%s",
            email, subject, plain_text,
        )


if __name__ == "__main__":
    main()
