"""Fast NAICS loader using PostgreSQL COPY and a staging table.

Instead of 80K individual INSERTs per file (~20 min), this:
1. Parses the XML into a CSV buffer in memory
2. Uses COPY FROM to bulk load into a staging table (~5 sec)
3. Upserts from staging into naics_records (~5 sec)
4. Truncates staging

Result: ~10 seconds per file instead of 20 minutes.

Usage:
    cd backend
    .venv/Scripts/python ../scripts/load_naics_fast.py
"""
from __future__ import annotations

import io
import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import psycopg2
from app.services.oktap_parser import parse_naics_export, OkTAPParseError

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
NAICS_DIR = Path(__file__).parent.parent / "data" / "raw" / "naics"


def create_staging_table(cur):
    cur.execute("""
        CREATE TABLE IF NOT EXISTS naics_staging (
            copo VARCHAR(20),
            tax_type VARCHAR(10),
            year INTEGER,
            month INTEGER,
            activity_code VARCHAR(20),
            activity_code_description TEXT,
            sector VARCHAR(15),
            tax_rate NUMERIC(10,4),
            sector_total NUMERIC(15,2),
            year_to_date NUMERIC(15,2)
        )
    """)
    cur.execute("TRUNCATE naics_staging")


def load_file_fast(conn, cur, filepath: Path) -> int:
    """Load one NAICS file using COPY + upsert. Returns record count."""
    import re

    match = re.match(r"naics_(\w+)_(\d+)_(\d+)_(\w+)\.xls", filepath.name)
    if not match:
        return 0

    tax_type = match.group(1)
    year = int(match.group(2))
    month = int(match.group(3))

    with open(filepath, "rb") as f:
        data = f.read()

    try:
        parsed = parse_naics_export(data, tax_type, year, month)
    except OkTAPParseError as e:
        log.warning("  Parse error: %s", e)
        return 0

    if not parsed.records:
        return 0

    # Ensure all jurisdictions exist
    copos = {r.copo for r in parsed.records}
    for copo in copos:
        cur.execute(
            "INSERT INTO jurisdictions (copo, name, jurisdiction_type) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (copo, f"Unknown ({copo})", "city"),
        )

    # Build CSV buffer
    buf = io.StringIO()
    for r in parsed.records:
        activity = r.activity_code or "UNCLASSIFIED"
        desc = (r.activity_code_description or "").replace("\t", " ").replace("\n", " ")
        buf.write(f"{r.copo}\t{tax_type}\t{year}\t{month}\t{activity}\t{desc}\t{r.sector}\t{r.tax_rate}\t{r.sector_total}\t{r.year_to_date}\n")

    buf.seek(0)

    # COPY into staging
    cur.execute("TRUNCATE naics_staging")
    cur.copy_from(buf, "naics_staging", sep="\t",
                  columns=("copo", "tax_type", "year", "month", "activity_code",
                           "activity_code_description", "sector", "tax_rate",
                           "sector_total", "year_to_date"))

    # Upsert from staging into main table (deduplicate first)
    cur.execute("""
        INSERT INTO naics_records (copo, tax_type, year, month, activity_code,
                                   activity_code_description, sector, tax_rate,
                                   sector_total, year_to_date)
        SELECT DISTINCT ON (copo, tax_type, year, month, activity_code)
               copo, tax_type, year, month, activity_code,
               activity_code_description, sector, tax_rate,
               sector_total, year_to_date
        FROM naics_staging
        ORDER BY copo, tax_type, year, month, activity_code, sector_total DESC
        ON CONFLICT (copo, tax_type, year, month, activity_code)
        DO UPDATE SET
            sector_total = EXCLUDED.sector_total,
            year_to_date = EXCLUDED.year_to_date
    """)

    conn.commit()
    return len(parsed.records)


def main():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    create_staging_table(cur)
    conn.commit()

    files = sorted(NAICS_DIR.glob("naics_*.xls"))
    log.info("Loading %d NAICS files (fast mode)...", len(files))

    total = 0
    start = time.time()

    for i, filepath in enumerate(files):
        size_mb = filepath.stat().st_size / 1_000_000
        log.info("[%d/%d] %s (%.0f MB)", i + 1, len(files), filepath.name, size_mb)

        t0 = time.time()
        count = load_file_fast(conn, cur, filepath)
        elapsed = time.time() - t0

        total += count
        log.info("  -> %d records in %.1fs", count, elapsed)

    # Cleanup
    cur.execute("DROP TABLE IF EXISTS naics_staging")
    conn.commit()

    # Final counts
    cur.execute("SELECT COUNT(*) FROM naics_records")
    db_total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT copo) FROM naics_records")
    db_cities = cur.fetchone()[0]
    cur.execute("SELECT MIN(year*100+month), MAX(year*100+month) FROM naics_records")
    r = cur.fetchone()

    elapsed_total = time.time() - start
    log.info("=" * 60)
    log.info("DONE in %.1f minutes", elapsed_total / 60)
    log.info("  Loaded this run: %d records", total)
    log.info("  DB total NAICS: %d", db_total)
    log.info("  DB cities: %d", db_cities)
    log.info("  Date range: %s to %s", r[0], r[1])
    log.info("=" * 60)

    conn.close()


if __name__ == "__main__":
    main()
