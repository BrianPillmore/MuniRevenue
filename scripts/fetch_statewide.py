"""Fetch ALL Oklahoma tax data from OkTAP — cities and counties.

Retrieves ledger reports (sales, use, lodging) for all available years,
for both cities and counties. Each request returns all jurisdictions
for that tax_type/year/jurisdiction_type combination.

Usage:
    cd backend
    .venv/Scripts/python ../scripts/fetch_statewide.py

Data is saved to:
    data/raw/   — raw .xls files from OkTAP
    data/parsed/ — summary CSVs for quick inspection

Estimated time: ~3 minutes per year (6 requests x 5s delay), ~18 min total.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.oktap_retriever import fetch_ledger, fetch_naics, REQUEST_DELAY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
PARSED_DIR = DATA_DIR / "parsed"

YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
TAX_TYPES = ["sales", "use", "lodging"]
JURISDICTION_TYPES = ["City", "County"]

# Polite delay between requests (seconds)
DELAY = 5


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    total_records = 0
    total_requests = 0
    failed = 0
    start_time = time.time()

    log.info("=" * 60)
    log.info("MuniRev Statewide Data Retrieval")
    log.info("Years: %s", YEARS)
    log.info("Tax types: %s", TAX_TYPES)
    log.info("Jurisdiction types: %s", JURISDICTION_TYPES)
    log.info("Delay between requests: %ds", DELAY)
    log.info("=" * 60)

    all_records = []

    for year in YEARS:
        for jtype in JURISDICTION_TYPES:
            for tax_type in TAX_TYPES:
                total_requests += 1
                label = f"ledger/{tax_type}/{year}/{jtype.lower()}"
                log.info("[%d] Fetching %s...", total_requests, label)

                # Check if we already have this file
                raw_file = RAW_DIR / f"ledger_{tax_type}_{year}_{jtype.lower()}.xls"
                if raw_file.exists():
                    log.info("  Already exists, skipping. Delete file to re-fetch.")
                    continue

                result = fetch_ledger(
                    tax_type=tax_type,
                    year=year,
                    copo="",  # empty = all jurisdictions
                    month=None,  # None = all months
                    city_or_county=jtype,
                )

                if result.success:
                    log.info("  -> %d records", result.record_count)
                    total_records += result.record_count

                    # Save raw file
                    if result.file_bytes:
                        with open(raw_file, "wb") as f:
                            f.write(result.file_bytes)
                        log.info("  Saved: %s (%d bytes)",
                                 raw_file.name, len(result.file_bytes))

                    # Collect parsed records
                    if result.parsed_ledger:
                        for r in result.parsed_ledger.records:
                            all_records.append({
                                "copo": r.copo,
                                "tax_type": tax_type,
                                "jurisdiction_type": jtype.lower(),
                                "voucher_date": str(r.voucher_date),
                                "tax_rate": str(r.tax_rate),
                                "current_month_collection": str(r.current_month_collection),
                                "returned": str(r.returned),
                                "year": year,
                            })
                else:
                    failed += 1
                    log.warning("  FAILED: %s", result.error)

                # Polite delay
                log.info("  Waiting %ds...", DELAY)
                time.sleep(DELAY)

    # Write summary CSV
    if all_records:
        csv_path = PARSED_DIR / "all_ledger_records.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_records[0].keys())
            writer.writeheader()
            writer.writerows(all_records)
        log.info("Wrote %d records to %s", len(all_records), csv_path)

        # Also write per-city summary
        by_copo: dict[str, list] = {}
        for r in all_records:
            by_copo.setdefault(r["copo"], []).append(r)

        summary_path = PARSED_DIR / "jurisdiction_summary.csv"
        with open(summary_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["copo", "jurisdiction_type", "record_count",
                             "tax_types", "date_range", "total_returned"])
            for copo in sorted(by_copo.keys()):
                recs = by_copo[copo]
                jtypes = set(r["jurisdiction_type"] for r in recs)
                ttypes = set(r["tax_type"] for r in recs)
                dates = sorted(r["voucher_date"] for r in recs)
                total = sum(float(r["returned"]) for r in recs)
                writer.writerow([
                    copo,
                    ",".join(jtypes),
                    len(recs),
                    ",".join(sorted(ttypes)),
                    f"{dates[0]} to {dates[-1]}",
                    f"{total:.2f}",
                ])
        log.info("Wrote jurisdiction summary: %d jurisdictions", len(by_copo))

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("COMPLETE")
    log.info("  Requests: %d (%d failed)", total_requests, failed)
    log.info("  Records: %d", total_records)
    log.info("  Jurisdictions: %d", len(by_copo) if all_records else 0)
    log.info("  Time: %.1f minutes", elapsed / 60)
    log.info("  Data dir: %s", DATA_DIR)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
