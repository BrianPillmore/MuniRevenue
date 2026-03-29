"""Automated retrieval of OkTAP reports via headless browser.

Uses Playwright to navigate the OkTAP web application, fill forms,
trigger searches, and download exported .xls files. The downloaded
files are then parsed by the existing oktap_parser module.

OkTAP form field IDs (discovered via Playwright inspection):
  Ledger (#1):  Tax Type=Dd-4 (STH/STS/STU), City/County=Dd-5,
                Year=Dd-6, Month=Dd-7, Copo=Dd-8, Search=Dd-9
  NAICS (#2):   Tax Type=Dd-4 (STS/STU), City/County/State=Dd-5,
                Year=Dd-6, Month=Dd-7, Copo=Dd-8, Sector=Dd-9, Search=Dd-a
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.services.oktap_parser import (
    OkTAPParseError,
    ParsedLedgerReport,
    ParsedNaicsReport,
    detect_report_type,
    parse_ledger_export,
    parse_naics_export,
)

logger = logging.getLogger(__name__)

OKTAP_BASE = "https://oktap.tax.ok.gov/OkTAP/Web/_/"
REQUEST_DELAY = 3  # seconds between requests (respectful rate limit)

# OkTAP tax type radio values
TAX_TYPE_MAP = {
    "lodging": "STH",
    "sales": "STS",
    "use": "STU",
}


class OkTAPRetrievalError(Exception):
    """Raised when OkTAP data retrieval fails."""


@dataclass
class RetrievalResult:
    """Result of a single OkTAP retrieval."""
    success: bool
    report_type: str  # "ledger" or "naics"
    tax_type: str
    year: int
    month: Optional[int] = None
    copo: Optional[str] = None
    record_count: int = 0
    file_bytes: Optional[bytes] = None
    parsed_ledger: Optional[ParsedLedgerReport] = None
    parsed_naics: Optional[ParsedNaicsReport] = None
    error: Optional[str] = None


@dataclass
class BatchResult:
    """Result of a batch retrieval job."""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    total_records: int = 0
    results: list[RetrievalResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _navigate_to_report(page, report_type: str) -> None:
    """Navigate from OkTAP home to a specific report form."""
    page.goto(OKTAP_BASE, wait_until="networkidle", timeout=30000)
    page.click("text=View Public Reports")
    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(1)

    if report_type == "ledger":
        page.click("text=Ledger Reports")
    elif report_type == "naics":
        page.click("text=Tax by NAICS Report")
    else:
        raise OkTAPRetrievalError(f"Unknown report type: {report_type}")

    page.wait_for_load_state("networkidle", timeout=15000)
    time.sleep(1)


def _fill_ledger_form(
    page,
    tax_type: str,
    year: int,
    copo: str = "",
    month: Optional[int] = None,
    city_or_county: str = "City",
) -> None:
    """Fill the OkTAP Ledger Reports form."""
    radio_value = TAX_TYPE_MAP.get(tax_type)
    if not radio_value:
        raise OkTAPRetrievalError(f"Invalid tax type: {tax_type}")

    # Tax type radio (click label, not hidden input)
    radio_idx = list(TAX_TYPE_MAP.values()).index(radio_value)
    page.click(f"label[for='Dd-4_{radio_idx}']")
    time.sleep(0.3)

    # City/County radio
    if city_or_county.lower() == "county":
        page.click("label[for='Dd-5_1']")
    else:
        page.click("label[for='Dd-5_0']")
    time.sleep(0.3)

    # Year
    page.select_option("#Dd-6", str(year))
    time.sleep(0.3)

    # Month (optional — blank gets all months)
    if month is not None:
        page.select_option("#Dd-7", str(month))
        time.sleep(0.3)

    # Copo (optional — blank gets all cities/counties)
    if copo:
        page.fill("#Dd-8", copo)
        time.sleep(0.3)


def _fill_naics_form(
    page,
    tax_type: str,
    year: int,
    month: int,
    copo: str = "",
    city_or_county: str = "City",
) -> None:
    """Fill the OkTAP NAICS Report form."""
    radio_value = TAX_TYPE_MAP.get(tax_type)
    if radio_value not in ("STS", "STU"):
        raise OkTAPRetrievalError(f"NAICS only supports sales/use, got: {tax_type}")

    # Tax type radio
    idx = 0 if radio_value == "STS" else 1
    page.click(f"label[for='Dd-4_{idx}']")
    time.sleep(0.3)

    # City/County/State radio
    loc_map = {"city": 0, "county": 1, "state": 2}
    loc_idx = loc_map.get(city_or_county.lower(), 0)
    page.click(f"label[for='Dd-5_{loc_idx}']")
    time.sleep(0.3)

    # Year + Month (required for NAICS)
    page.select_option("#Dd-6", str(year))
    time.sleep(0.3)
    page.select_option("#Dd-7", str(month))
    time.sleep(0.3)

    # Copo
    if copo:
        page.fill("#Dd-8", copo)
        time.sleep(0.3)


def _search_and_export(page, search_button_id: str = "#Dd-9") -> Optional[bytes]:
    """Click Search, wait for results, click Export, return file bytes."""
    page.click(search_button_id)
    page.wait_for_load_state("networkidle", timeout=60000)
    time.sleep(3)

    body_text = page.inner_text("body")
    if "No Results" in body_text:
        return None

    # Find Export link
    export_link = None
    for link in page.query_selector_all("a"):
        text = link.inner_text().strip()
        if text.lower() == "export":
            export_link = link
            break

    if not export_link:
        raise OkTAPRetrievalError("Results found but no Export link available.")

    # Click Export and capture download
    with page.expect_download(timeout=60000) as download_info:
        export_link.click()
    download = download_info.value

    # Save to temp file and read bytes
    with tempfile.NamedTemporaryFile(suffix=".xls", delete=False) as tmp:
        download.save_as(tmp.name)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp_path)


def fetch_ledger(
    tax_type: str,
    year: int,
    copo: str = "",
    month: Optional[int] = None,
    city_or_county: str = "City",
) -> RetrievalResult:
    """Fetch a ledger report from OkTAP.

    Args:
        tax_type: "lodging", "sales", or "use"
        year: Report year (e.g. 2026)
        copo: City/county code. Empty string = all cities/counties.
        month: Month number 1-12. None = all months in the year.
        city_or_county: "City" or "County"

    Returns:
        RetrievalResult with parsed data.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            _navigate_to_report(page, "ledger")
            _fill_ledger_form(page, tax_type, year, copo, month, city_or_county)
            file_bytes = _search_and_export(page)

            if file_bytes is None:
                return RetrievalResult(
                    success=True, report_type="ledger", tax_type=tax_type,
                    year=year, month=month, copo=copo or "ALL",
                    record_count=0,
                )

            parsed = parse_ledger_export(file_bytes, tax_type)
            return RetrievalResult(
                success=True, report_type="ledger", tax_type=tax_type,
                year=year, month=month, copo=copo or "ALL",
                record_count=len(parsed.records),
                file_bytes=file_bytes, parsed_ledger=parsed,
            )

        except Exception as exc:
            logger.error("Ledger retrieval failed: %s", exc)
            return RetrievalResult(
                success=False, report_type="ledger", tax_type=tax_type,
                year=year, month=month, copo=copo or "ALL",
                error=str(exc),
            )
        finally:
            browser.close()


def fetch_naics(
    tax_type: str,
    year: int,
    month: int,
    copo: str = "",
    city_or_county: str = "City",
) -> RetrievalResult:
    """Fetch a NAICS report from OkTAP.

    Args:
        tax_type: "sales" or "use"
        year: Report year
        month: Report month (1-12, required)
        copo: City/county code. Empty = all.
        city_or_county: "City", "County", or "State"

    Returns:
        RetrievalResult with parsed data.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            _navigate_to_report(page, "naics")
            _fill_naics_form(page, tax_type, year, month, copo, city_or_county)
            # NAICS search button has a different ID
            file_bytes = _search_and_export(page, search_button_id="#Dd-a")

            if file_bytes is None:
                return RetrievalResult(
                    success=True, report_type="naics", tax_type=tax_type,
                    year=year, month=month, copo=copo or "ALL",
                    record_count=0,
                )

            parsed = parse_naics_export(file_bytes, tax_type, year, month)
            return RetrievalResult(
                success=True, report_type="naics", tax_type=tax_type,
                year=year, month=month, copo=copo or "ALL",
                record_count=len(parsed.records),
                file_bytes=file_bytes, parsed_naics=parsed,
            )

        except Exception as exc:
            logger.error("NAICS retrieval failed: %s", exc)
            return RetrievalResult(
                success=False, report_type="naics", tax_type=tax_type,
                year=year, month=month, copo=copo or "ALL",
                error=str(exc),
            )
        finally:
            browser.close()


def fetch_all_ledger_statewide(
    tax_type: str,
    year: int,
    city_or_county: str = "City",
) -> RetrievalResult:
    """Fetch ledger data for ALL cities (or counties) in one request.

    OkTAP returns all jurisdictions when the Copo field is left blank.
    This is much faster than fetching one city at a time.
    """
    return fetch_ledger(tax_type, year, copo="", city_or_county=city_or_county)


def fetch_statewide_batch(
    years: list[int],
    tax_types: list[str] | None = None,
    include_naics: bool = False,
) -> BatchResult:
    """Fetch all available data for all cities across multiple years.

    Args:
        years: List of years to fetch (e.g. [2022, 2023, 2024, 2025, 2026])
        tax_types: Tax types to fetch. Default: ["sales", "use", "lodging"]
        include_naics: Also fetch NAICS breakdowns (much slower)

    Returns:
        BatchResult with all retrieval results.
    """
    if tax_types is None:
        tax_types = ["sales", "use", "lodging"]

    batch = BatchResult()

    # Ledger: one request per tax_type per year gets ALL cities
    for year in years:
        for tax_type in tax_types:
            batch.total_requests += 1
            logger.info("Fetching ledger: %s %s (all cities)...", tax_type, year)

            result = fetch_all_ledger_statewide(tax_type, year, "City")
            batch.results.append(result)

            if result.success:
                batch.successful += 1
                batch.total_records += result.record_count
                logger.info("  -> %d records", result.record_count)
            else:
                batch.failed += 1
                batch.errors.append(f"ledger/{tax_type}/{year}: {result.error}")
                logger.warning("  -> FAILED: %s", result.error)

            time.sleep(REQUEST_DELAY)

        # Also fetch county data
        for tax_type in tax_types:
            batch.total_requests += 1
            logger.info("Fetching ledger: %s %s (all counties)...", tax_type, year)

            result = fetch_all_ledger_statewide(tax_type, year, "County")
            batch.results.append(result)

            if result.success:
                batch.successful += 1
                batch.total_records += result.record_count
            else:
                batch.failed += 1
                batch.errors.append(f"ledger/{tax_type}/{year}/county: {result.error}")

            time.sleep(REQUEST_DELAY)

    # NAICS: requires per-month requests
    if include_naics:
        naics_types = [t for t in tax_types if t in ("sales", "use")]
        for year in years:
            for month in range(1, 13):
                for tax_type in naics_types:
                    batch.total_requests += 1
                    logger.info("Fetching NAICS: %s %s-%02d (all cities)...",
                                tax_type, year, month)

                    result = fetch_naics(tax_type, year, month, copo="")
                    batch.results.append(result)

                    if result.success:
                        batch.successful += 1
                        batch.total_records += result.record_count
                    else:
                        batch.failed += 1
                        batch.errors.append(
                            f"naics/{tax_type}/{year}-{month:02d}: {result.error}"
                        )

                    time.sleep(REQUEST_DELAY)

    return batch
