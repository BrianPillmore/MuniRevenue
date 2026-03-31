#!/usr/bin/env python3
"""Run anomaly detection across all jurisdictions in the MuniRev database.

Usage:
    cd backend
    .venv/Scripts/python scripts/run_anomaly_detection.py

This script:
1. Clears the existing anomalies table.
2. Runs ledger-based anomaly detection (YoY, MoM, revenue cliff) for all
   (copo, tax_type) pairs with sufficient data.
3. Stores all detected anomalies in the ``anomalies`` table.
4. Runs NAICS industry anomaly detection for the top 20 industries per city.
5. Stores NAICS shift anomalies in the ``anomalies`` table.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

# Ensure the backend package is importable when running from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras

from app.services.anomaly_detector import AnomalyDetector

DATABASE_URL = "postgresql://munirev:changeme@localhost:5432/munirev"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run_anomaly_detection")


def _store_anomalies(
    conn: psycopg2.extensions.connection,
    anomalies: list[dict],
) -> int:
    """Bulk-insert anomaly records into the anomalies table.

    Returns the number of rows inserted.
    """
    if not anomalies:
        return 0

    cur = conn.cursor()
    insert_sql = """
        INSERT INTO anomalies (
            copo, tax_type, anomaly_date, anomaly_type,
            severity, expected_value, actual_value,
            deviation_pct, description
        ) VALUES (
            %(copo)s, %(tax_type)s, %(anomaly_date)s, %(anomaly_type)s,
            %(severity)s, %(expected_value)s, %(actual_value)s,
            %(deviation_pct)s, %(description)s
        )
    """
    psycopg2.extras.execute_batch(cur, insert_sql, anomalies, page_size=500)
    conn.commit()
    cur.close()
    return len(anomalies)


def main() -> None:
    """Run the full anomaly detection pipeline."""
    logger.info("Connecting to database: %s", DATABASE_URL)
    conn = psycopg2.connect(DATABASE_URL)

    try:
        # ── Step 1: Clear existing anomalies ──
        logger.info("Clearing existing anomalies table...")
        cur = conn.cursor()
        cur.execute("DELETE FROM anomalies")
        conn.commit()
        cur.close()
        logger.info("Anomalies table cleared.")

        detector = AnomalyDetector()

        # ── Step 2: Ledger-based anomaly detection ──
        logger.info("=" * 60)
        logger.info("Phase 1: Ledger anomaly detection (YoY, MoM, revenue cliff)")
        logger.info("=" * 60)

        t0 = time.time()

        # Find all (copo, tax_type) pairs with enough data
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

        all_ledger_anomalies: list[dict] = []
        processed = 0

        for row in pairs:
            copo = row["copo"]
            tax_type = row["tax_type"]
            anomalies = detector.detect_for_city(conn, copo, tax_type)
            all_ledger_anomalies.extend(anomalies)
            processed += 1

            if processed % 100 == 0:
                logger.info(
                    "  Processed %d/%d city/tax pairs (%d anomalies so far)",
                    processed, len(pairs), len(all_ledger_anomalies),
                )

        inserted = _store_anomalies(conn, all_ledger_anomalies)
        elapsed = time.time() - t0
        logger.info(
            "Ledger detection complete: %d pairs scanned, %d anomalies stored in %.1fs.",
            processed, inserted, elapsed,
        )

        # ── Step 3: NAICS industry anomaly detection ──
        logger.info("=" * 60)
        logger.info("Phase 2: NAICS industry anomaly detection")
        logger.info("=" * 60)

        t0 = time.time()

        # Find all (copo, tax_type) pairs with NAICS data
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("""
            SELECT DISTINCT copo, tax_type
            FROM naics_records
            ORDER BY copo, tax_type
        """)
        naics_pairs = cur.fetchall()
        cur.close()

        all_naics_anomalies: list[dict] = []
        naics_processed = 0

        for row in naics_pairs:
            copo = row["copo"]
            tax_type = row["tax_type"]
            anomalies = detector.detect_naics_anomalies(
                conn, copo, tax_type, naics_limit=20,
            )
            all_naics_anomalies.extend(anomalies)
            naics_processed += 1

            if naics_processed % 100 == 0:
                logger.info(
                    "  Processed %d/%d NAICS city/tax pairs (%d anomalies so far)",
                    naics_processed, len(naics_pairs), len(all_naics_anomalies),
                )

        naics_inserted = _store_anomalies(conn, all_naics_anomalies)
        elapsed = time.time() - t0
        logger.info(
            "NAICS detection complete: %d pairs scanned, %d anomalies stored in %.1fs.",
            naics_processed, naics_inserted, elapsed,
        )

        # ── Summary ──
        logger.info("=" * 60)
        logger.info("ANOMALY DETECTION COMPLETE")
        logger.info("  Ledger anomalies: %d", inserted)
        logger.info("  NAICS anomalies:  %d", naics_inserted)
        logger.info("  Total:            %d", inserted + naics_inserted)
        logger.info("=" * 60)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
