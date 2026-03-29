"""Fetch ALL Oklahoma NAICS tax data from OkTAP — cities and counties.

Uses a SINGLE browser session and re-fills the form for each request,
avoiding the overhead of opening a new browser per request.

Usage:
    cd backend
    .venv/Scripts/python ../scripts/fetch_naics_statewide.py
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.oktap_parser import parse_naics_export, OkTAPParseError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw" / "naics"
PARSED_DIR = DATA_DIR / "parsed"

YEARS = [2021, 2022, 2023, 2024, 2025]  # NAICS only goes to 2025 on OkTAP
TAX_TYPES = ["sales", "use"]
JURISDICTION_TYPES = ["City", "County"]
NOW = datetime.now()
DELAY = 5


def should_skip(year: int, month: int) -> bool:
    if year > NOW.year:
        return True
    if year == NOW.year and month >= NOW.month - 1:
        return True
    return False


def navigate_to_naics(page) -> None:
    """Navigate from OkTAP home to the NAICS report form."""
    page.goto("https://oktap.tax.ok.gov/OkTAP/Web/_/", wait_until="networkidle", timeout=30000)
    page.click("text=View Public Reports")
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(1)
    page.click("text=Tax by NAICS Report")
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(1)


def fetch_single_naics(page, context, tax_type: str, year: int, month: int,
                       jtype: str) -> tuple[int, bytes | None]:
    """Fill form and fetch one NAICS report. Returns (record_count, file_bytes)."""
    # Tax type radio
    if tax_type == "sales":
        page.click("label[for='Dd-4_0']")
    else:
        page.click("label[for='Dd-4_1']")
    time.sleep(0.3)

    # Jurisdiction type
    jtype_map = {"City": "Dd-5_0", "County": "Dd-5_1", "State": "Dd-5_2"}
    page.click(f"label[for='{jtype_map[jtype]}']")
    time.sleep(0.3)

    # Year
    page.select_option("#Dd-6", str(year))
    time.sleep(0.3)

    # Month
    page.select_option("#Dd-7", str(month))
    time.sleep(0.3)

    # Clear Copo (blank = all)
    page.fill("#Dd-8", "")
    time.sleep(0.3)

    # Click Search
    page.click("#Dd-a")
    page.wait_for_load_state("networkidle", timeout=60000)
    time.sleep(3)

    body_text = page.inner_text("body")
    if "No Results" in body_text:
        return 0, None

    # Find Export link
    export_link = None
    for link in page.query_selector_all("a"):
        if link.inner_text().strip().lower() == "export":
            export_link = link
            break

    if not export_link:
        return 0, None

    # Download
    with page.expect_download(timeout=60000) as dl_info:
        export_link.click()
    download = dl_info.value

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".xls", delete=False) as tmp:
        download.save_as(tmp.name)
        tmp_path = tmp.name

    with open(tmp_path, "rb") as f:
        file_bytes = f.read()
    os.unlink(tmp_path)

    # Parse to count records
    try:
        parsed = parse_naics_export(file_bytes, tax_type, year, month)
        return len(parsed.records), file_bytes
    except OkTAPParseError:
        return 0, file_bytes


def go_back_to_form(page) -> None:
    """Click Back to return to the search form for the next query."""
    back_btn = page.query_selector("#Dc-9")
    if back_btn:
        back_btn.click()
        page.wait_for_load_state("networkidle", timeout=15000)
        time.sleep(1)
    else:
        # Re-navigate
        navigate_to_naics(page)


def main() -> None:
    from playwright.sync_api import sync_playwright

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PARSED_DIR.mkdir(parents=True, exist_ok=True)

    total_records = 0
    total_requests = 0
    skipped = 0
    failed = 0
    start_time = time.time()

    log.info("=" * 60)
    log.info("MuniRev NAICS Statewide Data Retrieval")
    log.info("Years: %s", YEARS)
    log.info("Tax types: %s", TAX_TYPES)
    log.info("Jurisdiction types: %s", JURISDICTION_TYPES)
    log.info("=" * 60)

    all_records = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        # Initial navigation
        navigate_to_naics(page)

        for year in YEARS:
            for month in range(1, 13):
                if should_skip(year, month):
                    skipped += 1
                    continue

                for jtype in JURISDICTION_TYPES:
                    for tax_type in TAX_TYPES:
                        total_requests += 1
                        label = f"naics/{tax_type}/{year}-{month:02d}/{jtype.lower()}"

                        raw_file = RAW_DIR / f"naics_{tax_type}_{year}_{month:02d}_{jtype.lower()}.xls"
                        if raw_file.exists():
                            log.info("[%d] %s — exists, skipping", total_requests, label)
                            continue

                        log.info("[%d] Fetching %s...", total_requests, label)

                        try:
                            count, file_bytes = fetch_single_naics(
                                page, context, tax_type, year, month, jtype
                            )

                            if count == 0:
                                log.info("  -> No data")
                            else:
                                log.info("  -> %d records", count)
                                total_records += count

                                if file_bytes:
                                    with open(raw_file, "wb") as f:
                                        f.write(file_bytes)
                                    log.info("  Saved: %s (%d bytes)",
                                             raw_file.name, len(file_bytes))

                                    # Collect for CSV
                                    try:
                                        parsed = parse_naics_export(
                                            file_bytes, tax_type, year, month
                                        )
                                        for r in parsed.records:
                                            all_records.append({
                                                "copo": r.copo,
                                                "tax_type": tax_type,
                                                "jurisdiction_type": jtype.lower(),
                                                "year": year,
                                                "month": month,
                                                "sector": r.sector,
                                                "activity_code": r.activity_code or "",
                                                "description": r.activity_code_description,
                                                "sector_total": str(r.sector_total),
                                                "year_to_date": str(r.year_to_date),
                                            })
                                    except OkTAPParseError as e:
                                        log.warning("  Parse error for CSV: %s", e)

                            # Go back for next query
                            go_back_to_form(page)

                        except Exception as exc:
                            failed += 1
                            log.warning("  FAILED: %s", exc)
                            # Re-navigate on failure
                            try:
                                navigate_to_naics(page)
                            except Exception:
                                pass

                        time.sleep(DELAY)

        browser.close()

    # Write CSVs
    if all_records:
        csv_path = PARSED_DIR / "all_naics_records.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=all_records[0].keys())
            writer.writeheader()
            writer.writerows(all_records)
        log.info("Wrote %d NAICS records to %s", len(all_records), csv_path)

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("COMPLETE")
    log.info("  Requests: %d (%d failed, %d skipped)", total_requests, failed, skipped)
    log.info("  Records: %d", total_records)
    log.info("  Time: %.1f minutes", elapsed / 60)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
