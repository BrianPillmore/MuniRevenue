#!/usr/bin/env python3
"""Run the MuniRev anomaly detection engine.

This script:
1. Creates the ``anomalies`` table if it does not exist.
2. Truncates existing anomaly rows (re-run safe).
3. Runs AnomalyDetector.detect_all() against all ledger data.
4. Bulk-inserts discovered anomalies using ON CONFLICT DO NOTHING.
5. Prints a summary: total anomalies by severity, top 10 most anomalous
   cities.

Usage::

    cd backend
    python -m scripts.run_anomaly_detection

Or run directly::

    python scripts/run_anomaly_detection.py
"""

from __future__ import annotations

import logging
import sys
import time
from collections import Counter
from pathlib import Path

# Ensure the backend package is importable when running the script directly.
_backend_dir = Path(__file__).resolve().parent.parent / "backend"
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import psycopg2
import psycopg2.extras

from app.services.anomaly_detector import AnomalyDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("anomaly_detection")

DATABASE_URL = "postgresql://munirev:changeme@localhost:5432/munirev"

# ---------------------------------------------------------------------------
# DDL: anomalies table
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    copo VARCHAR(10) NOT NULL,
    tax_type VARCHAR(10) NOT NULL,
    anomaly_date DATE NOT NULL,
    anomaly_type VARCHAR(30) NOT NULL,
    severity VARCHAR(10) NOT NULL,
    expected_value NUMERIC(15,2),
    actual_value NUMERIC(15,2),
    deviation_pct NUMERIC(10,2),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(copo, tax_type, anomaly_date, anomaly_type)
);
"""

INSERT_SQL = """
INSERT INTO anomalies (
    copo, tax_type, anomaly_date, anomaly_type, severity,
    expected_value, actual_value, deviation_pct, description
) VALUES (
    %(copo)s, %(tax_type)s, %(anomaly_date)s, %(anomaly_type)s, %(severity)s,
    %(expected_value)s, %(actual_value)s, %(deviation_pct)s, %(description)s
)
ON CONFLICT (copo, tax_type, anomaly_date, anomaly_type) DO NOTHING
"""


def create_table(conn: psycopg2.extensions.connection) -> None:
    """Create the anomalies table if it does not already exist."""
    cur = conn.cursor()
    cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    cur.close()
    logger.info("Ensured anomalies table exists.")


def truncate_table(conn: psycopg2.extensions.connection) -> None:
    """Truncate the anomalies table for a clean re-run."""
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE anomalies RESTART IDENTITY;")
    conn.commit()
    cur.close()
    logger.info("Truncated anomalies table.")


def insert_anomalies(
    conn: psycopg2.extensions.connection,
    anomalies: list[dict],
) -> int:
    """Bulk-insert anomaly rows.  Returns number of rows inserted."""
    if not anomalies:
        return 0

    cur = conn.cursor()
    inserted = 0

    # Batch in chunks of 1000 for memory efficiency.
    batch_size = 1000
    for start in range(0, len(anomalies), batch_size):
        batch = anomalies[start : start + batch_size]
        psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=batch_size)
        inserted += len(batch)

    conn.commit()
    cur.close()
    return inserted


def collect_all_anomalies(conn: psycopg2.extensions.connection) -> list[dict]:
    """Run the detector across all city/tax pairs and collect results.

    Unlike AnomalyDetector.detect_all() which just returns a count,
    this function accumulates the actual anomaly dicts so they can be
    inserted into the database.
    """
    detector = AnomalyDetector()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT copo, tax_type, COUNT(*) AS n
        FROM ledger_records
        GROUP BY copo, tax_type
        HAVING COUNT(*) >= 3
        ORDER BY copo, tax_type
    """)
    pairs = cur.fetchall()
    cur.close()

    all_anomalies: list[dict] = []
    processed = 0

    for row in pairs:
        copo = row["copo"]
        tax_type = row["tax_type"]
        anomalies = detector.detect_for_city(conn, copo, tax_type)
        all_anomalies.extend(anomalies)
        processed += 1

        if processed % 100 == 0:
            logger.info(
                "Processed %d/%d pairs (%d anomalies so far)",
                processed,
                len(pairs),
                len(all_anomalies),
            )

    logger.info(
        "Detection complete: %d pairs scanned, %d anomalies found.",
        processed,
        len(all_anomalies),
    )
    return all_anomalies


def print_summary(
    conn: psycopg2.extensions.connection,
    total_inserted: int,
) -> None:
    """Print a human-readable summary of detected anomalies."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Count by severity.
    cur.execute("""
        SELECT severity, COUNT(*) AS cnt
        FROM anomalies
        GROUP BY severity
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high'     THEN 2
                WHEN 'medium'   THEN 3
                WHEN 'low'      THEN 4
                ELSE 5
            END
    """)
    severity_rows = cur.fetchall()

    # Count by anomaly type.
    cur.execute("""
        SELECT anomaly_type, COUNT(*) AS cnt
        FROM anomalies
        GROUP BY anomaly_type
        ORDER BY cnt DESC
    """)
    type_rows = cur.fetchall()

    # Top 10 most anomalous cities.
    cur.execute("""
        SELECT a.copo, j.name, COUNT(*) AS anomaly_count,
               SUM(CASE WHEN a.severity = 'critical' THEN 1 ELSE 0 END) AS critical_count
        FROM anomalies a
        JOIN jurisdictions j ON a.copo = j.copo
        GROUP BY a.copo, j.name
        ORDER BY anomaly_count DESC
        LIMIT 10
    """)
    top_cities = cur.fetchall()
    cur.close()

    # Print report.
    print("\n" + "=" * 70)
    print("  MUNIREV ANOMALY DETECTION SUMMARY")
    print("=" * 70)
    print(f"\n  Total anomalies inserted: {total_inserted:,}")

    print("\n  Anomalies by severity:")
    print("  " + "-" * 40)
    for row in severity_rows:
        print(f"    {row['severity']:>10s}:  {row['cnt']:>6,}")

    print("\n  Anomalies by type:")
    print("  " + "-" * 40)
    for row in type_rows:
        print(f"    {row['anomaly_type']:>20s}:  {row['cnt']:>6,}")

    print("\n  Top 10 most anomalous cities:")
    print("  " + "-" * 60)
    print(f"    {'Rank':>4s}  {'COPO':<8s}  {'City':<25s}  {'Total':>6s}  {'Critical':>8s}")
    print("  " + "-" * 60)
    for i, row in enumerate(top_cities, 1):
        print(
            f"    {i:>4d}  {row['copo']:<8s}  {row['name']:<25s}  "
            f"{row['anomaly_count']:>6,}  {row['critical_count']:>8,}"
        )

    print("\n" + "=" * 70)


def main() -> None:
    """Entry point for the anomaly detection script."""
    start_time = time.time()

    logger.info("Connecting to database: %s", DATABASE_URL.split("@")[-1])
    conn = psycopg2.connect(DATABASE_URL)

    try:
        # Step 1: Ensure table exists.
        create_table(conn)

        # Step 2: Truncate for clean re-run.
        truncate_table(conn)

        # Step 3: Run detection across all cities / tax types.
        logger.info("Starting anomaly detection across all jurisdictions...")
        all_anomalies = collect_all_anomalies(conn)

        # Step 4: Bulk insert.
        if all_anomalies:
            inserted = insert_anomalies(conn, all_anomalies)
            logger.info("Inserted %d anomaly rows.", inserted)
        else:
            inserted = 0
            logger.info("No anomalies detected.")

        # Step 5: Print summary.
        print_summary(conn, inserted)

    finally:
        conn.close()

    elapsed = time.time() - start_time
    logger.info("Anomaly detection completed in %.1f seconds.", elapsed)


if __name__ == "__main__":
    main()
