"""Load all downloaded OkTAP data into PostgreSQL.

Reads raw .xls files from data/raw/, parses them, and INSERTs into
the ledger_records and naics_records tables. Uses ON CONFLICT DO UPDATE
for idempotent re-runs.

Auto-creates jurisdiction records for any copo codes not in the
jurisdictions table (from the data itself).

Usage:
    cd backend
    .venv/Scripts/python ../scripts/load_data.py
"""
from __future__ import annotations

import argparse
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Load OkTAP raw data into PostgreSQL")
    parser.add_argument("--ledger-limit", type=int, default=None, help="Only load the first N ledger files")
    parser.add_argument("--naics-limit", type=int, default=None, help="Only load the first N NAICS files")
    parser.add_argument("--skip-ledger", action="store_true", help="Skip ledger imports")
    parser.add_argument("--skip-naics", action="store_true", help="Skip NAICS imports")
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

    conn.close()


if __name__ == "__main__":
    main()
