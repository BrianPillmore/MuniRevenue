"""Load all downloaded OkTAP data into PostgreSQL.

Reads raw .xls files from data/raw/, parses them, and INSERTs into
the ledger_records and naics_records tables. Uses ON CONFLICT DO UPDATE
for idempotent re-runs.

Auto-creates jurisdiction records for any copo codes not in the
jurisdictions table (from the data itself).

Usage:
    cd backend
    .venv/Scripts/python ../scripts/load_data.py

Post-import email reports:
    .venv/Scripts/python ../scripts/load_data.py \\
        --send-reports \\
        --report-month 2026-03-01 \\
        --recipients-csv /path/to/recipients.csv

The recipients CSV must have columns: copo, jurisdiction_name, email
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import psycopg2
import psycopg2.extras
from app.services.oktap_parser import (
    OkTAPParseError,
    parse_ledger_export,
    parse_naics_export,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://munirev:changeme@localhost:5432/munirev",
)
DATA_DIR = Path(__file__).parent.parent / "data" / "raw"
UNCLASSIFIED_ACTIVITY_CODE = "999999"


def ensure_jurisdiction(cur, copo: str, jtype: str = "city"):
    """Create jurisdiction if it doesn't exist."""
    cur.execute(
        """INSERT INTO jurisdictions (copo, name, jurisdiction_type)
           VALUES (%s, %s, %s)
           ON CONFLICT (copo) DO NOTHING""",
        (copo, f"Unknown ({copo})", jtype),
    )


def ensure_naics_code(cur, activity_code: str, description: str) -> None:
    """Create or update a NAICS code reference row."""
    sector_description = "Unclassified" if activity_code == UNCLASSIFIED_ACTIVITY_CODE else None
    cur.execute(
        """INSERT INTO naics_codes (activity_code, description, sector_description)
           VALUES (%s, %s, %s)
           ON CONFLICT (activity_code) DO UPDATE SET
             description = EXCLUDED.description,
             sector_description = COALESCE(naics_codes.sector_description, EXCLUDED.sector_description)""",
        (activity_code, description, sector_description),
    )


def create_import_batch(cur, source_type: str, filename: str, file_hash: str):
    """Create an audit row for an import file and return the import_id."""
    cur.execute(
        """INSERT INTO data_imports (
               source_type, file_name, file_hash, status,
               started_at, records_total, records_success, records_failed
           )
           VALUES (%s, %s, %s, 'processing', NOW(), 0, 0, 0)
           RETURNING import_id""",
        (source_type, filename, file_hash),
    )
    return cur.fetchone()[0]


def complete_import_batch(
    cur,
    import_id,
    *,
    total: int,
    success: int,
    failed: int = 0,
    error_detail: Optional[dict] = None,
) -> None:
    """Mark an import batch completed, partial, or failed."""
    if failed and success:
        status = "partial"
    elif failed:
        status = "failed"
    else:
        status = "completed"

    cur.execute(
        """UPDATE data_imports
           SET status = %s,
               records_total = %s,
               records_success = %s,
               records_failed = %s,
               error_detail = %s,
               completed_at = NOW()
           WHERE import_id = %s""",
        (
            status,
            total,
            success,
            failed,
            psycopg2.extras.Json(error_detail) if error_detail is not None else None,
            import_id,
        ),
    )


def normalize_activity_code(activity_code: Optional[str], description: str) -> tuple[str, str]:
    """Convert parser output into a schema-compatible NAICS code row."""
    normalized_description = description.strip() or "Unclassified"
    if activity_code and activity_code.strip():
        return activity_code.strip(), normalized_description
    return UNCLASSIFIED_ACTIVITY_CODE, normalized_description


def parse_ledger_filename(filename: str) -> tuple[str, int, Optional[int], str] | None:
    """Parse annual and supplemental ledger filenames.

    Supported formats:
    - ledger_sales_2025_city.xls
    - ledger_sales_2025_m05_city.xls
    - ledger_sales_2025_m06_county.xls
    """
    match = re.match(r"ledger_(\w+)_(\d+)(?:_m(\d{2}))?_(\w+)\.xls", filename)
    if not match:
        return None
    tax_type = match.group(1)
    year = int(match.group(2))
    month_hint = int(match.group(3)) if match.group(3) else None
    jurisdiction_type = match.group(4)
    return tax_type, year, month_hint, jurisdiction_type


def load_ledger_file(cur, filepath: Path) -> int:
    """Load a single ledger .xls file. Returns record count."""
    filename = filepath.name

    parsed_filename = parse_ledger_filename(filename)
    if parsed_filename is None:
        log.warning("  Skipping unrecognized filename: %s", filename)
        return 0

    tax_type, _year, month_hint, jtype = parsed_filename

    with open(filepath, "rb") as f:
        data = f.read()

    file_hash = hashlib.sha256(data).hexdigest()
    import_id = create_import_batch(cur, "ledger", filename, file_hash)

    try:
        parsed = parse_ledger_export(data, tax_type)
    except OkTAPParseError as e:
        log.warning("  Parse error: %s", e)
        complete_import_batch(
            cur,
            import_id,
            total=0,
            success=0,
            failed=1,
            error_detail={"error": str(e)},
        )
        return 0

    count = 0
    for r in parsed.records:
        ensure_jurisdiction(cur, r.copo, jtype)
        cur.execute(
            """INSERT INTO ledger_records
               (copo, tax_type, voucher_date, tax_rate, current_month_collection,
                refunded, suspended_monies, apportioned, revolving_fund,
                                interest_returned, returned, import_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (copo, tax_type, voucher_date) DO UPDATE SET
                 returned = EXCLUDED.returned,
                 current_month_collection = EXCLUDED.current_month_collection,
                 tax_rate = EXCLUDED.tax_rate,
                 import_id = EXCLUDED.import_id""",
            (
                r.copo, tax_type, r.voucher_date, float(r.tax_rate),
                float(r.current_month_collection), float(r.refunded),
                float(r.suspended_monies), float(r.apportioned),
                float(r.revolving_fund), float(r.interest_returned),
                float(r.returned), import_id,
            ),
        )
        count += 1

    complete_import_batch(cur, import_id, total=count, success=count)
    if month_hint is not None:
        log.info("  Supplemental month import detected for %s month %02d", tax_type, month_hint)

    return count


def load_naics_file(cur, filepath: Path) -> int:
    """Load a single NAICS .xls file. Returns record count."""
    filename = filepath.name

    # Format: naics_{tax_type}_{year}_{month}_all.xls
    match = re.match(r"naics_(\w+)_(\d+)_(\d+)_(\w+)\.xls", filename)
    if not match:
        log.warning("  Skipping unrecognized filename: %s", filename)
        return 0

    tax_type = match.group(1)
    year = int(match.group(2))
    month_from_filename = int(match.group(3))
    jurisdiction_label = match.group(4).lower()
    jurisdiction_type = "county" if jurisdiction_label == "county" else "city"

    with open(filepath, "rb") as f:
        data = f.read()

    file_hash = hashlib.sha256(data).hexdigest()
    import_id = create_import_batch(cur, "naics", filename, file_hash)

    try:
        # Try parsing with the filename month first
        parsed = parse_naics_export(data, tax_type, year, month_from_filename)
    except OkTAPParseError as e:
        log.warning("  Parse error: %s", e)
        complete_import_batch(
            cur,
            import_id,
            total=0,
            success=0,
            failed=1,
            error_detail={"error": str(e)},
        )
        return 0

    # Determine actual month from the data if possible
    # The NAICS data doesn't have dates, so we use what we have
    actual_month = month_from_filename
    report_date = date(year, actual_month, 1)

    count = 0
    for r in parsed.records:
        ensure_jurisdiction(cur, r.copo, jurisdiction_type)
        activity_code, activity_description = normalize_activity_code(
            r.activity_code,
            r.activity_code_description,
        )
        ensure_naics_code(cur, activity_code, activity_description)
        cur.execute(
            """INSERT INTO naics_records
               (copo, tax_type, report_date, activity_code, tax_rate,
                sector_total, year_to_date, import_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (copo, tax_type, report_date, activity_code) DO UPDATE SET
                 sector_total = EXCLUDED.sector_total,
                 year_to_date = EXCLUDED.year_to_date,
                 import_id = EXCLUDED.import_id""",
            (
                r.copo,
                tax_type,
                report_date,
                activity_code,
                float(r.tax_rate),
                float(r.sector_total),
                float(r.year_to_date),
                import_id,
            ),
        )
        count += 1

    complete_import_batch(cur, import_id, total=count, success=count)

    return count


# ---------------------------------------------------------------------------
# Report recipients helpers
# ---------------------------------------------------------------------------


def load_recipients_from_csv(csv_path: Path) -> list[tuple[str, str, str]]:
    """Load (copo, jurisdiction_name, email) tuples from a CSV file.

    The CSV must have a header row with at least the columns:
        copo, jurisdiction_name, email

    Rows with a blank email are silently skipped.
    """
    recipients: list[tuple[str, str, str]] = []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            copo = (row.get("copo") or "").strip()
            name = (row.get("jurisdiction_name") or "").strip()
            email = (row.get("email") or "").strip()
            if not copo or not email:
                continue
            if not name:
                name = f"Jurisdiction {copo}"
            recipients.append((copo, name, email))
    return recipients


def load_recipients_from_db(conn) -> list[tuple[str, str, str]]:
    """Query contacts with emails for all jurisdictions present in ledger_records.

    Selects one email per jurisdiction, preferring finance / treasurer / clerk /
    mayor roles (in that order) when multiple contacts exist for a city.

    Returns a list of (copo, jurisdiction_name, email) tuples.
    """
    import psycopg2.extras as _extras
    cur = conn.cursor(cursor_factory=_extras.RealDictCursor)
    cur.execute(
        """
        WITH ranked_contacts AS (
            SELECT
                j.copo,
                j.name                  AS jurisdiction_name,
                c.email,
                ROW_NUMBER() OVER (
                    PARTITION BY j.copo
                    ORDER BY
                        CASE
                            WHEN lower(c.office_title) LIKE '%finance%'   THEN 1
                            WHEN lower(c.office_title) LIKE '%treasurer%' THEN 2
                            WHEN lower(c.office_title) LIKE '%clerk%'     THEN 3
                            WHEN lower(c.office_title) LIKE '%mayor%'     THEN 4
                            ELSE 5
                        END,
                        c.id ASC
                ) AS rn
            FROM jurisdictions j
            JOIN contacts c ON lower(c.jurisdiction_name) = lower(j.name)
            WHERE c.email IS NOT NULL
              AND c.email != ''
              AND j.copo IN (
                  SELECT DISTINCT copo FROM ledger_records
              )
        )
        SELECT copo, jurisdiction_name, email
        FROM ranked_contacts
        WHERE rn = 1
        ORDER BY jurisdiction_name
        """
    )
    rows = cur.fetchall()
    cur.close()
    return [(row["copo"], row["jurisdiction_name"], row["email"]) for row in rows]


def infer_report_month(conn) -> date:
    """Return the most recently imported voucher month from ledger_records."""
    import psycopg2.extras as _extras
    cur = conn.cursor(cursor_factory=_extras.RealDictCursor)
    cur.execute("SELECT MAX(voucher_date) AS max_date FROM ledger_records")
    row = cur.fetchone()
    cur.close()
    if row and row["max_date"]:
        d = row["max_date"]
        return date(d.year, d.month, 1)
    return date.today().replace(day=1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Load OkTAP raw data into PostgreSQL")
    parser.add_argument("--ledger-limit", type=int, default=None, help="Only load the first N ledger files")
    parser.add_argument("--naics-limit", type=int, default=None, help="Only load the first N NAICS files")
    parser.add_argument("--skip-ledger", action="store_true", help="Skip ledger imports")
    parser.add_argument("--skip-naics", action="store_true", help="Skip NAICS imports")

    # Report dispatch options
    parser.add_argument(
        "--send-reports",
        action="store_true",
        help=(
            "After importing, dispatch HTML revenue report emails. "
            "Delivery mode is controlled by MUNIREV_EMAIL_MODE (log|smtp)."
        ),
    )
    parser.add_argument(
        "--report-month",
        type=str,
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Voucher month to report on (first day of month, e.g. 2026-03-01). "
            "Defaults to the most recently imported voucher month."
        ),
    )
    parser.add_argument(
        "--recipients-csv",
        type=str,
        default=None,
        metavar="PATH",
        help=(
            "CSV file with columns: copo, jurisdiction_name, email. "
            "When omitted, recipients are queried from the contacts table."
        ),
    )

    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    start = time.time()
    total_ledger = 0
    total_naics = 0

    # Load ledger files
    ledger_files = [] if args.skip_ledger else sorted(DATA_DIR.glob("ledger_*.xls"))
    if args.ledger_limit is not None:
        ledger_files = ledger_files[: max(0, args.ledger_limit)]
    log.info("=" * 60)
    log.info("Loading %d ledger files...", len(ledger_files))

    for i, filepath in enumerate(ledger_files):
        log.info("[%d/%d] %s", i + 1, len(ledger_files), filepath.name)
        count = load_ledger_file(cur, filepath)
        total_ledger += count
        log.info("  -> %d records", count)
        conn.commit()

    # Load NAICS files
    naics_dir = DATA_DIR / "naics"
    naics_files = []
    if not args.skip_naics and naics_dir.exists():
        naics_files = sorted(naics_dir.glob("naics_*.xls"))
    if args.naics_limit is not None:
        naics_files = naics_files[: max(0, args.naics_limit)]
    log.info("\nLoading %d NAICS files...", len(naics_files))

    for i, filepath in enumerate(naics_files):
        log.info("[%d/%d] %s (%d MB)", i + 1, len(naics_files),
                 filepath.name, filepath.stat().st_size // 1_000_000)
        count = load_naics_file(cur, filepath)
        total_naics += count
        log.info("  -> %d records", count)
        conn.commit()

    # Summary
    cur.execute("SELECT COUNT(*) FROM jurisdictions")
    j_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM ledger_records")
    l_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM naics_records")
    n_count = cur.fetchone()[0]

    elapsed = time.time() - start
    log.info("=" * 60)
    log.info("COMPLETE in %.1f minutes", elapsed / 60)
    log.info("  Jurisdictions: %d", j_count)
    log.info("  Ledger records: %d (loaded %d this run)", l_count, total_ledger)
    log.info("  NAICS records: %d (loaded %d this run)", n_count, total_naics)
    log.info("=" * 60)

    # ---------------------------------------------------------------------------
    # Optional: dispatch post-import report emails
    # ---------------------------------------------------------------------------
    if args.send_reports:
        from app.services.email_report import (
            ReportRecipient,
            load_email_settings,
            send_reports_after_import,
        )

        # Determine report month
        if args.report_month:
            try:
                parts = [int(x) for x in args.report_month.split("-")]
                report_month = date(parts[0], parts[1], 1)
            except (ValueError, IndexError):
                log.error("Invalid --report-month value: %s. Expected YYYY-MM-DD.", args.report_month)
                conn.close()
                sys.exit(1)
        else:
            report_month = infer_report_month(conn)
            log.info("Inferred report month: %s", report_month.isoformat())

        # Load recipients
        if args.recipients_csv:
            csv_path = Path(args.recipients_csv)
            if not csv_path.exists():
                log.error("Recipients CSV not found: %s", csv_path)
                conn.close()
                sys.exit(1)
            raw_recipients = load_recipients_from_csv(csv_path)
            log.info("Loaded %d recipients from %s", len(raw_recipients), csv_path.name)
        else:
            raw_recipients = load_recipients_from_db(conn)
            log.info("Loaded %d recipients from contacts table", len(raw_recipients))

        if not raw_recipients:
            log.warning("No recipients found. Skipping report dispatch.")
        else:
            service_recipients = [
                ReportRecipient(copo=copo, jurisdiction_name=name, email=email)
                for copo, name, email in raw_recipients
            ]
            settings = load_email_settings()
            log.info(
                "Dispatching reports for %s to %d recipients (mode=%s)...",
                report_month.isoformat(),
                len(service_recipients),
                settings.email_mode,
            )
            result = send_reports_after_import(
                recipients=service_recipients,
                report_month=report_month,
                db_conn=conn,
                settings=settings,
            )
            log.info(
                "Report dispatch complete: %d sent, %d skipped (no data), %d failed.",
                result.sent,
                result.skipped_no_data,
                result.failed,
            )
            if result.errors:
                for err in result.errors:
                    log.warning(
                        "  Failed: %s (%s) -> %s",
                        err.get("copo"),
                        err.get("email"),
                        err.get("error"),
                    )

    conn.close()


if __name__ == "__main__":
    main()
