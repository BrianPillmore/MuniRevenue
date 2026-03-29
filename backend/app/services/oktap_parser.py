"""Parser for OkTAP export files (XML SpreadsheetML format).

OkTAP exports .xls files that are actually XML SpreadsheetML, not binary
Excel.  This module parses the two known report types -- Ledger and NAICS --
into validated Pydantic models with Decimal-precision financial fields.

Only stdlib ``xml.etree.ElementTree`` is used for XML parsing.
"""

from __future__ import annotations

import datetime
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# XML SpreadsheetML namespace
# ---------------------------------------------------------------------------

_SS_NS = "urn:schemas-microsoft-com:office:spreadsheet"

# Fully-qualified tag names for namespace-aware lookups.
_WORKSHEET_TAG = f"{{{_SS_NS}}}Worksheet"
_TABLE_TAG = f"{{{_SS_NS}}}Table"
_ROW_TAG = f"{{{_SS_NS}}}Row"
_CELL_TAG = f"{{{_SS_NS}}}Cell"
_DATA_TAG = f"{{{_SS_NS}}}Data"

# ---------------------------------------------------------------------------
# Known header signatures used for report-type detection
# ---------------------------------------------------------------------------

_LEDGER_HEADERS = [
    "Copo",
    "Tax Rate",
    "Current Month Collection",
    "Refunded",
    "Suspended Monies",
    "Apportioned",
    "Revolving Fund",
    "Interest Returned",
    "Returned",
    "Voucher Date",
]

_NAICS_HEADERS = [
    "Copo",
    "Sector",
    "Activity Code",
    "Activity Code Description",
    "Tax Rate",
    "Sector Total",
    "Year To Date",
]


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class OkTAPParseError(ValueError):
    """Raised when an OkTAP export file cannot be parsed."""


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class LedgerRecord(BaseModel):
    """A single data row from an OkTAP Ledger report."""

    copo: str
    tax_rate: Decimal
    current_month_collection: Decimal
    refunded: Decimal
    suspended_monies: Decimal
    apportioned: Decimal
    revolving_fund: Decimal
    interest_returned: Decimal
    returned: Decimal
    voucher_date: datetime.date


class NaicsRecord(BaseModel):
    """A single data row from an OkTAP NAICS report."""

    copo: str
    sector: str
    activity_code: Optional[str] = None
    activity_code_description: str
    tax_rate: Decimal
    sector_total: Decimal
    year_to_date: Decimal


class ParsedLedgerReport(BaseModel):
    """Complete parsed result of a Ledger export."""

    tax_type: str
    records: list[LedgerRecord]
    filename: Optional[str] = None


class ParsedNaicsReport(BaseModel):
    """Complete parsed result of a NAICS export."""

    tax_type: str
    year: int
    month: int
    records: list[NaicsRecord]
    filename: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_rows(file_bytes: bytes) -> list[list[str]]:
    """Parse XML SpreadsheetML bytes and return all rows as lists of strings.

    Each inner list contains the text content of every ``<Data>`` element in
    the row, preserving column order.

    Raises:
        OkTAPParseError: If the XML cannot be parsed or has an unexpected
            structure.
    """
    try:
        root = ET.fromstring(file_bytes)
    except ET.ParseError as exc:
        raise OkTAPParseError(f"Failed to parse XML: {exc}") from exc

    # Find the first Worksheet > Table.
    worksheet = root.find(_WORKSHEET_TAG)
    if worksheet is None:
        # Try namespace-unaware search as a fallback.
        worksheet = root.find("Worksheet")
    if worksheet is None:
        raise OkTAPParseError(
            "No <Worksheet> element found. The file may not be an OkTAP "
            "SpreadsheetML export."
        )

    table = worksheet.find(_TABLE_TAG)
    if table is None:
        table = worksheet.find("Table")
    if table is None:
        raise OkTAPParseError(
            "No <Table> element found inside the worksheet."
        )

    rows: list[list[str]] = []
    for row_el in table.iter(_ROW_TAG):
        cells: list[str] = []
        for cell_el in row_el.iter(_CELL_TAG):
            data_el = cell_el.find(_DATA_TAG)
            cells.append(
                data_el.text if data_el is not None and data_el.text else ""
            )
        if cells:
            rows.append(cells)

    if not rows:
        raise OkTAPParseError("The spreadsheet contains no rows.")

    return rows


def _parse_decimal(value: str, field_name: str, row_index: int) -> Decimal:
    """Convert a string value to Decimal with a clear error message."""
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise OkTAPParseError(
            f"Cannot convert {field_name!r} value {value!r} to Decimal "
            f"in data row {row_index}."
        ) from exc


def _parse_voucher_date(value: str, row_index: int) -> datetime.date:
    """Parse an ISO-formatted datetime string into a date object.

    Accepts formats like ``2025-07-09T00:00:00`` or ``2025-07-09``.
    """
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise OkTAPParseError(
        f"Cannot parse Voucher Date {value!r} in data row {row_index}. "
        f"Expected ISO format (e.g. 2025-07-09T00:00:00)."
    )


def _is_totals_row(cells: list[str]) -> bool:
    """Return True when *cells* represents the trailing totals row.

    The totals row has an empty Copo (first column).
    """
    return not cells or cells[0].strip() == ""


def _validate_headers(
    actual: list[str],
    expected: list[str],
    report_label: str,
) -> None:
    """Raise ``OkTAPParseError`` if the header row does not match."""
    normalised_actual = [h.strip() for h in actual]
    if normalised_actual != expected:
        raise OkTAPParseError(
            f"Unexpected header row for {report_label} report. "
            f"Expected {expected}, got {normalised_actual}."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_report_type(file_bytes: bytes) -> str:
    """Determine whether *file_bytes* is a Ledger or NAICS export.

    Args:
        file_bytes: Raw bytes of the OkTAP .xls (SpreadsheetML) file.

    Returns:
        ``"ledger"`` or ``"naics"``.

    Raises:
        OkTAPParseError: If the file cannot be parsed or the header row does
            not match either known report type.
    """
    rows = _extract_rows(file_bytes)
    headers = [h.strip() for h in rows[0]]

    if headers == _LEDGER_HEADERS:
        return "ledger"
    if headers == _NAICS_HEADERS:
        return "naics"

    raise OkTAPParseError(
        f"Unrecognised OkTAP report type. Header row: {headers}"
    )


def parse_ledger_export(
    file_bytes: bytes,
    tax_type: str,
    *,
    filename: str | None = None,
) -> ParsedLedgerReport:
    """Parse an OkTAP Ledger export into a ``ParsedLedgerReport``.

    Args:
        file_bytes: Raw bytes of the OkTAP .xls (SpreadsheetML) file.
        tax_type: The municipal tax type label (e.g. ``"sales"``).
        filename: Optional original filename for traceability.

    Returns:
        A validated ``ParsedLedgerReport`` containing all data rows.

    Raises:
        OkTAPParseError: On any structural or data-conversion error.
    """
    rows = _extract_rows(file_bytes)
    _validate_headers(rows[0], _LEDGER_HEADERS, "Ledger")

    expected_cols = len(_LEDGER_HEADERS)
    records: list[LedgerRecord] = []

    for idx, cells in enumerate(rows[1:], start=1):
        if _is_totals_row(cells):
            continue

        if len(cells) < expected_cols:
            raise OkTAPParseError(
                f"Ledger data row {idx} has {len(cells)} columns; "
                f"expected {expected_cols}."
            )

        records.append(
            LedgerRecord(
                copo=cells[0].strip(),
                tax_rate=_parse_decimal(cells[1], "Tax Rate", idx),
                current_month_collection=_parse_decimal(
                    cells[2], "Current Month Collection", idx
                ),
                refunded=_parse_decimal(cells[3], "Refunded", idx),
                suspended_monies=_parse_decimal(
                    cells[4], "Suspended Monies", idx
                ),
                apportioned=_parse_decimal(cells[5], "Apportioned", idx),
                revolving_fund=_parse_decimal(
                    cells[6], "Revolving Fund", idx
                ),
                interest_returned=_parse_decimal(
                    cells[7], "Interest Returned", idx
                ),
                returned=_parse_decimal(cells[8], "Returned", idx),
                voucher_date=_parse_voucher_date(cells[9].strip(), idx),
            )
        )

    if not records:
        raise OkTAPParseError("Ledger export contains no data rows.")

    return ParsedLedgerReport(
        tax_type=tax_type,
        records=records,
        filename=filename,
    )


def parse_naics_export(
    file_bytes: bytes,
    tax_type: str,
    year: int,
    month: int,
    *,
    filename: str | None = None,
) -> ParsedNaicsReport:
    """Parse an OkTAP NAICS export into a ``ParsedNaicsReport``.

    Args:
        file_bytes: Raw bytes of the OkTAP .xls (SpreadsheetML) file.
        tax_type: The municipal tax type label (e.g. ``"sales"``).
        year: Fiscal/calendar year the report covers.
        month: Month number (1-12) the report covers.
        filename: Optional original filename for traceability.

    Returns:
        A validated ``ParsedNaicsReport`` containing all data rows.

    Raises:
        OkTAPParseError: On any structural or data-conversion error.
    """
    if not 1 <= month <= 12:
        raise OkTAPParseError(f"Month must be 1-12, got {month}.")

    rows = _extract_rows(file_bytes)
    _validate_headers(rows[0], _NAICS_HEADERS, "NAICS")

    expected_cols = len(_NAICS_HEADERS)
    records: list[NaicsRecord] = []

    for idx, cells in enumerate(rows[1:], start=1):
        if _is_totals_row(cells):
            continue

        if len(cells) < expected_cols:
            raise OkTAPParseError(
                f"NAICS data row {idx} has {len(cells)} columns; "
                f"expected {expected_cols}."
            )

        activity_code_raw = cells[2].strip()
        records.append(
            NaicsRecord(
                copo=cells[0].strip(),
                sector=cells[1].strip(),
                activity_code=activity_code_raw if activity_code_raw else None,
                activity_code_description=cells[3].strip(),
                tax_rate=_parse_decimal(cells[4], "Tax Rate", idx),
                sector_total=_parse_decimal(cells[5], "Sector Total", idx),
                year_to_date=_parse_decimal(cells[6], "Year To Date", idx),
            )
        )

    if not records:
        raise OkTAPParseError("NAICS export contains no data rows.")

    return ParsedNaicsReport(
        tax_type=tax_type,
        year=year,
        month=month,
        records=records,
        filename=filename,
    )
