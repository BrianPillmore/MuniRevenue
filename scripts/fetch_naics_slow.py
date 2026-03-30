"""Fetch ALL Oklahoma NAICS data from OkTAP — all years, all months.

Key discovery: the month dropdown only populates all 12 months when the year
is changed via keyboard typing (not programmatic select_option alone).
The OkTAP framework requires actual keypress events on the year dropdown.

Usage:
    cd backend
    .venv/Scripts/python ../scripts/fetch_naics_slow.py

5-minute delay between requests to avoid throttling.
Resume-safe: skips already-downloaded files.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from app.services.oktap_parser import parse_naics_export, OkTAPParseError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "naics"
RAW_DIR.mkdir(parents=True, exist_ok=True)

YEARS = [2021, 2022, 2023, 2024, 2025, 2026]
MONTHS = list(range(1, 13))
TAX_CONFIGS = [("sales", "Dd-4_0"), ("use", "Dd-4_1")]
DELAY = 120  # 2 minutes


def navigate_to_naics(page):
    page.goto("https://oktap.tax.ok.gov/OkTAP/Web/_/",
              wait_until="networkidle", timeout=60000)
    time.sleep(2)
    page.click("text=View Public Reports", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(2)
    page.click("text=Tax by NAICS Report", timeout=15000)
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(3)


def type_year(page, year: int):
    """Type year digits into the year dropdown to trigger month reload."""
    page.focus("#Dd-6")
    time.sleep(0.3)
    for digit in str(year):
        page.keyboard.press(digit)
        time.sleep(0.1)
    page.keyboard.press("Tab")
    time.sleep(3)


def select_month_by_js(page, month: int):
    """Select a month by setting value via JS after months are loaded."""
    # The month options are loaded dynamically after year change.
    # Use JS to set value and dispatch change event.
    page.evaluate(f"""() => {{
        const sel = document.querySelector('#Dd-7');
        sel.value = '{month}';
        sel.dispatchEvent(new Event('change', {{bubbles: true}}));
    }}""")
    time.sleep(0.5)
    # Also click and Tab to ensure framework registers the change
    page.focus("#Dd-7")
    page.keyboard.press("Tab")
    time.sleep(1)


def fetch_one(year: int, month: int, tax_name: str, tax_radio: str) -> tuple[int, bytes | None]:
    """Fetch one NAICS report. Opens fresh browser each time."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            navigate_to_naics(page)

            # Tax type radio
            page.locator(f"label[for='{tax_radio}']").click(force=True, timeout=10000)
            time.sleep(0.5)
            # City radio
            page.locator("label[for='Dd-5_0']").click(force=True, timeout=10000)
            time.sleep(0.5)

            # Year via keyboard typing (triggers month dropdown reload)
            type_year(page, year)

            # Verify months loaded
            month_count = page.evaluate(
                "() => document.querySelector('#Dd-7').options.length"
            )
            if month_count < month:
                log.warning("  Only %d months available, need month %d", month_count, month)
                return 0, None

            # Month via keyboard position
            select_month_by_js(page, month)

            # Verify month value
            actual_month = page.evaluate("() => document.querySelector('#Dd-7').value")
            if str(actual_month) != str(month):
                log.warning("  Month mismatch: wanted %d, got %s", month, actual_month)

            # Copo (need one to make NAICS work, but returns all cities)
            page.fill("#Dd-8", "0955")
            time.sleep(0.5)

            # Search
            page.locator("#Dd-a").click(force=True, timeout=10000)
            page.wait_for_load_state("networkidle", timeout=180000)
            time.sleep(5)

            body = page.inner_text("body")
            if "No Results" in body:
                return 0, None
            if "Must complete" in body:
                log.warning("  Form incomplete")
                return 0, None

            # Export
            for link in page.query_selector_all("a"):
                if link.inner_text().strip().lower() == "export":
                    with page.expect_download(timeout=180000) as dl_info:
                        link.click()
                    download = dl_info.value

                    save_path = str(RAW_DIR / f"_temp_{year}_{month}_{tax_name}.xls")
                    download.save_as(save_path)

                    with open(save_path, "rb") as f:
                        data = f.read()

                    try:
                        os.unlink(save_path)
                    except OSError:
                        pass

                    parsed = parse_naics_export(data, tax_name, year, month)
                    return len(parsed.records), data

            return 0, None

        finally:
            browser.close()


def main():
    total_records = 0
    total_done = 0
    total_failed = 0
    start_time = time.time()

    # Build job list
    jobs = []
    for year in YEARS:
        for month in MONTHS:
            for tax_name, tax_radio in TAX_CONFIGS:
                jobs.append((year, month, tax_name, tax_radio))

    log.info("=" * 60)
    log.info("NAICS Statewide Fetch — All Years, All Months")
    log.info("Jobs: %d, Delay: %ds", len(jobs), DELAY)
    log.info("=" * 60)

    for i, (year, month, tax_name, tax_radio) in enumerate(jobs):
        dest = RAW_DIR / f"naics_{tax_name}_{year}_{month:02d}_all.xls"

        if dest.exists() and dest.stat().st_size > 1000:
            log.info("[%d/%d] %s %d-%02d: SKIP (exists, %d bytes)",
                     i + 1, len(jobs), tax_name, year, month, dest.stat().st_size)
            total_done += 1
            continue

        log.info("[%d/%d] %s %d-%02d: fetching...",
                 i + 1, len(jobs), tax_name, year, month)

        try:
            count, data = fetch_one(year, month, tax_name, tax_radio)

            if count == 0:
                log.info("  -> no data")
            else:
                with open(dest, "wb") as f:
                    f.write(data)
                copos = set()
                try:
                    parsed = parse_naics_export(data, tax_name, year, month)
                    copos = set(r.copo for r in parsed.records)
                except Exception:
                    pass
                total_records += count
                log.info("  -> %d records, %d cities, %d bytes",
                         count, len(copos), len(data))

            total_done += 1
        except Exception as e:
            total_failed += 1
            log.error("  FAILED: %s", str(e)[:200])

        # Delay before next request
        remaining = len(jobs) - (i + 1)
        if remaining > 0:
            log.info("  Waiting %ds...", DELAY)
            time.sleep(DELAY)

    elapsed = time.time() - start_time
    log.info("=" * 60)
    log.info("DONE: %d/%d done, %d failed, %d records, %.0f min",
             total_done, len(jobs), total_failed, total_records, elapsed / 60)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
