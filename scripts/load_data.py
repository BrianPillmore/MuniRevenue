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

import logging
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import psycopg2
from app.services.oktap_parser import (
    OkTAPParseError,
    parse_ledger_export,
    parse_naics_export,
    detect_report_type,
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


def ensure_jurisdiction(cur, copo: str, jtype: str = "city"):
    """Create jurisdiction if it doesn't exist."""
    cur.execute(
        """INSERT INTO jurisdictions (copo, name, jurisdiction_type)
           VALUES (%s, %s, %s)
           ON CONFLICT (copo) DO NOTHING""",
        (copo, f"Unknown ({copo})", jtype),
    )


def load_ledger_file(cur, filepath: Path) -> int:
    """Load a single ledger .xls file. Returns record count."""
    filename = filepath.name

    # Parse tax_type and jurisdiction_type from filename
    # Format: ledger_{tax_type}_{year}_{jtype}.xls
    match = re.match(r"ledger_(\w+)_(\d+)_(\w+)\.xls", filename)
    if not match:
        log.warning("  Skipping unrecognized filename: %s", filename)
        return 0

    tax_type = match.group(1)
    jtype = match.group(3)  # "city" or "county"

    with open(filepath, "rb") as f:
        data = f.read()

    try:
        parsed = parse_ledger_export(data, tax_type)
    except OkTAPParseError as e:
        log.warning("  Parse error: %s", e)
        return 0

    count = 0
    for r in parsed.records:
        ensure_jurisdiction(cur, r.copo, jtype)
        cur.execute(
            """INSERT INTO ledger_records
               (copo, tax_type, voucher_date, tax_rate, current_month_collection,
                refunded, suspended_monies, apportioned, revolving_fund,
                interest_returned, returned)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (copo, tax_type, voucher_date) DO UPDATE SET
                 returned = EXCLUDED.returned,
                 current_month_collection = EXCLUDED.current_month_collection,
                 tax_rate = EXCLUDED.tax_rate""",
            (
                r.copo, tax_type, r.voucher_date, float(r.tax_rate),
                float(r.current_month_collection), float(r.refunded),
                float(r.suspended_monies), float(r.apportioned),
                float(r.revolving_fund), float(r.interest_returned),
                float(r.returned),
            ),
        )
        count += 1

    # Log import
    cur.execute(
        "INSERT INTO data_imports (filename, report_type, records_imported) VALUES (%s, %s, %s)",
        (filename, "ledger", count),
    )

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

    with open(filepath, "rb") as f:
        data = f.read()

    try:
        # Try parsing with the filename month first
        parsed = parse_naics_export(data, tax_type, year, month_from_filename)
    except OkTAPParseError as e:
        log.warning("  Parse error: %s", e)
        return 0

    # Determine actual month from the data if possible
    # The NAICS data doesn't have dates, so we use what we have
    actual_month = month_from_filename

    count = 0
    for r in parsed.records:
        ensure_jurisdiction(cur, r.copo, "city")
        cur.execute(
            """INSERT INTO naics_records
               (copo, tax_type, year, month, activity_code, activity_code_description,
                sector, tax_rate, sector_total, year_to_date)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (copo, tax_type, year, month, activity_code) DO UPDATE SET
                 sector_total = EXCLUDED.sector_total,
                 year_to_date = EXCLUDED.year_to_date""",
            (
                r.copo, tax_type, year, actual_month,
                r.activity_code or "UNCLASSIFIED",
                r.activity_code_description, r.sector,
                float(r.tax_rate), float(r.sector_total), float(r.year_to_date),
            ),
        )
        count += 1

    cur.execute(
        "INSERT INTO data_imports (filename, report_type, records_imported) VALUES (%s, %s, %s)",
        (filename, "naics", count),
    )

    return count


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    start = time.time()
    total_ledger = 0
    total_naics = 0

    # Load ledger files
    ledger_files = sorted(DATA_DIR.glob("ledger_*.xls"))
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
    naics_files = sorted(naics_dir.glob("naics_*.xls")) if naics_dir.exists() else []
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
