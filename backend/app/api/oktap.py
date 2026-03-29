"""OkTAP data import routes.

Handles file uploads of .xls exports from Oklahoma's OkTAP tax reporting
system. Supports ledger reports (monthly revenue by city and tax type) and
NAICS reports (monthly revenue by city, tax type, and NAICS industry code).

The uploaded files are XML SpreadsheetML format with a .xls extension --
not binary Excel.  Parsing is delegated to ``app.services.oktap_parser``.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.services.oktap_parser import (
    OkTAPParseError,
    ParsedLedgerReport,
    ParsedNaicsReport,
    detect_report_type,
    parse_ledger_export,
    parse_naics_export,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/oktap", tags=["oktap"])

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

VALID_LEDGER_TAX_TYPES = {"lodging", "sales", "use"}
VALID_NAICS_TAX_TYPES = {"sales", "use"}


class ReportTypeEnum(str, Enum):
    ledger = "ledger"
    naics = "naics"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ImportResult(BaseModel):
    """Result of importing a single OkTAP file."""

    report_type: str = Field(
        ..., description="The detected or declared report type (ledger or naics)."
    )
    tax_type: str = Field(
        ..., description="The tax type the file was parsed as (lodging, sales, or use)."
    )
    record_count: int = Field(
        ..., ge=0, description="Number of records extracted from the file."
    )
    records: list[dict[str, Any]] = Field(
        default_factory=list,
        description="The parsed records from the OkTAP export.",
    )
    copo: Optional[str] = Field(
        None,
        description=(
            "City or political subdivision code from the first record, "
            "if available."
        ),
    )


class BulkImportResult(BaseModel):
    """Aggregate result of importing multiple OkTAP files."""

    total_files: int = Field(..., ge=0, description="Total number of files submitted.")
    successful: int = Field(..., ge=0, description="Number of files parsed successfully.")
    failed: int = Field(..., ge=0, description="Number of files that failed to parse.")
    results: list[ImportResult] = Field(
        default_factory=list,
        description="Per-file import results for each successfully parsed file.",
    )
    errors: list[dict[str, str]] = Field(
        default_factory=list,
        description="Per-file error details for each file that failed to parse.",
    )


class ReportTypeInfo(BaseModel):
    """Metadata about a supported OkTAP report type."""

    name: str
    description: str
    supported_tax_types: list[str]
    requires_year_month: bool


class ReportTypesResponse(BaseModel):
    """Available OkTAP report types and their metadata."""

    report_types: list[ReportTypeInfo]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_xls_extension(file: UploadFile) -> None:
    """Raise 400 if the uploaded file does not have a .xls extension."""
    filename = (file.filename or "").lower()
    if not filename.endswith(".xls"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Expected a .xls file but received '{file.filename}'. "
                "OkTAP exports use the .xls extension (XML SpreadsheetML)."
            ),
        )


def _validate_tax_type(tax_type: str, allowed: set[str], context: str) -> str:
    """Normalize and validate the tax_type parameter."""
    normalized = tax_type.strip().lower()
    if normalized not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid tax_type '{tax_type}' for {context}. "
                f"Must be one of: {', '.join(sorted(allowed))}."
            ),
        )
    return normalized


def _build_import_result(
    report_type: str,
    tax_type: str,
    parsed: ParsedLedgerReport | ParsedNaicsReport,
) -> ImportResult:
    """Convert a parsed report into an ``ImportResult`` response model."""
    records: list[dict[str, Any]] = []
    if hasattr(parsed, "records"):
        raw = parsed.records
        if raw and hasattr(raw[0], "model_dump"):
            records = [r.model_dump(mode="json") for r in raw]
        elif raw and hasattr(raw[0], "dict"):
            records = [r.dict() for r in raw]
        elif raw and hasattr(raw[0], "__dict__"):
            records = [vars(r) for r in raw]
        else:
            records = list(raw)

    copo: Optional[str] = None
    if records:
        first = records[0]
        copo = first.get("copo") or first.get("city_code") or first.get("code")

    return ImportResult(
        report_type=report_type,
        tax_type=tax_type,
        record_count=len(records),
        records=records,
        copo=copo,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/import/ledger",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
    summary="Import an OkTAP ledger report",
)
async def import_ledger(
    file: UploadFile = File(..., description="OkTAP ledger export (.xls)"),
    tax_type: str = Form(
        ..., description="Tax type: lodging, sales, or use."
    ),
) -> ImportResult:
    """Upload and parse a single OkTAP **ledger** report.

    Ledger reports contain monthly revenue by city and tax type.  The file
    must be a .xls export from OkTAP (XML SpreadsheetML format).

    The parsed records are returned directly.  Database storage will be
    added in a future release.
    """
    _validate_xls_extension(file)
    validated_tax_type = _validate_tax_type(
        tax_type, VALID_LEDGER_TAX_TYPES, "ledger import"
    )

    file_bytes = await file.read()

    try:
        parsed = parse_ledger_export(file_bytes, validated_tax_type)
    except OkTAPParseError as exc:
        logger.warning("Ledger parse failed for %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _build_import_result("ledger", validated_tax_type, parsed)


@router.post(
    "/import/naics",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
    summary="Import an OkTAP NAICS report",
)
async def import_naics(
    file: UploadFile = File(..., description="OkTAP NAICS export (.xls)"),
    tax_type: str = Form(..., description="Tax type: sales or use."),
    year: int = Form(..., description="Report year (e.g. 2025)."),
    month: int = Form(
        ..., description="Report month as an integer (1-12)."
    ),
) -> ImportResult:
    """Upload and parse a single OkTAP **NAICS** report.

    NAICS reports contain monthly revenue by city, tax type, and NAICS
    industry code.  The year and month parameters identify the reporting
    period because the NAICS export file does not always encode that
    information internally.
    """
    _validate_xls_extension(file)
    validated_tax_type = _validate_tax_type(
        tax_type, VALID_NAICS_TAX_TYPES, "NAICS import"
    )

    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"month must be between 1 and 12, got {month}.",
        )
    if year < 1900 or year > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"year must be between 1900 and 2100, got {year}.",
        )

    file_bytes = await file.read()

    try:
        parsed = parse_naics_export(
            file_bytes, validated_tax_type, year, month
        )
    except OkTAPParseError as exc:
        logger.warning("NAICS parse failed for %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _build_import_result("naics", validated_tax_type, parsed)


@router.post(
    "/import/auto",
    response_model=ImportResult,
    status_code=status.HTTP_200_OK,
    summary="Auto-detect report type and import",
)
async def import_auto(
    file: UploadFile = File(
        ..., description="OkTAP export (.xls) -- type will be detected."
    ),
    tax_type: str = Form(..., description="Tax type: lodging, sales, or use."),
    year: Optional[int] = Form(
        None,
        description="Report year (required for NAICS reports).",
    ),
    month: Optional[int] = Form(
        None,
        description="Report month 1-12 (required for NAICS reports).",
    ),
) -> ImportResult:
    """Upload an OkTAP export and let the server detect whether it is a
    ledger or NAICS report, then parse it accordingly.

    If the file is detected as a NAICS report, ``year`` and ``month`` must
    be provided -- otherwise the request will be rejected with HTTP 400.
    """
    _validate_xls_extension(file)

    file_bytes = await file.read()

    try:
        report_type = detect_report_type(file_bytes)
    except OkTAPParseError as exc:
        logger.warning("Report type detection failed for %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if report_type == "ledger":
        validated_tax_type = _validate_tax_type(
            tax_type, VALID_LEDGER_TAX_TYPES, "ledger import (auto-detected)"
        )
        try:
            parsed = parse_ledger_export(file_bytes, validated_tax_type)
        except OkTAPParseError as exc:
            logger.warning("Ledger parse failed for %s: %s", file.filename, exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        return _build_import_result("ledger", validated_tax_type, parsed)

    # NAICS report detected
    if year is None or month is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Detected a NAICS report but year and month were not provided. "
                "Both are required for NAICS imports."
            ),
        )

    if not (1 <= month <= 12):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"month must be between 1 and 12, got {month}.",
        )
    if year < 1900 or year > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"year must be between 1900 and 2100, got {year}.",
        )

    validated_tax_type = _validate_tax_type(
        tax_type, VALID_NAICS_TAX_TYPES, "NAICS import (auto-detected)"
    )

    try:
        parsed = parse_naics_export(
            file_bytes, validated_tax_type, year, month
        )
    except OkTAPParseError as exc:
        logger.warning("NAICS parse failed for %s: %s", file.filename, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return _build_import_result("naics", validated_tax_type, parsed)


@router.post(
    "/import/bulk",
    response_model=BulkImportResult,
    status_code=status.HTTP_200_OK,
    summary="Bulk import multiple OkTAP files",
)
async def import_bulk(
    files: list[UploadFile] = File(
        ..., description="One or more OkTAP export files (.xls)."
    ),
    tax_type: str = Form(..., description="Tax type: lodging, sales, or use."),
    year: Optional[int] = Form(
        None,
        description="Report year (required if any file is a NAICS report).",
    ),
    month: Optional[int] = Form(
        None,
        description="Report month 1-12 (required if any file is a NAICS report).",
    ),
) -> BulkImportResult:
    """Upload multiple OkTAP .xls exports at once.

    Each file is independently auto-detected and parsed.  The response
    contains a summary plus per-file results and errors.  A single file's
    failure does **not** abort the remaining files.
    """
    results: list[ImportResult] = []
    errors: list[dict[str, str]] = []

    for upload in files:
        filename = upload.filename or "<unknown>"

        # Extension validation -- record error and skip.
        fname_lower = (upload.filename or "").lower()
        if not fname_lower.endswith(".xls"):
            errors.append(
                {
                    "filename": filename,
                    "detail": (
                        f"Skipped '{filename}': expected .xls extension."
                    ),
                }
            )
            continue

        file_bytes = await upload.read()

        try:
            report_type = detect_report_type(file_bytes)
        except OkTAPParseError as exc:
            errors.append({"filename": filename, "detail": str(exc)})
            continue

        try:
            if report_type == "ledger":
                validated_tt = _validate_tax_type(
                    tax_type,
                    VALID_LEDGER_TAX_TYPES,
                    f"ledger import ({filename})",
                )
                parsed = parse_ledger_export(file_bytes, validated_tt)
                results.append(
                    _build_import_result("ledger", validated_tt, parsed)
                )

            else:
                # NAICS
                if year is None or month is None:
                    errors.append(
                        {
                            "filename": filename,
                            "detail": (
                                "Detected NAICS report but year/month not provided."
                            ),
                        }
                    )
                    continue

                if not (1 <= month <= 12):
                    errors.append(
                        {
                            "filename": filename,
                            "detail": f"month must be between 1 and 12, got {month}.",
                        }
                    )
                    continue

                validated_tt = _validate_tax_type(
                    tax_type,
                    VALID_NAICS_TAX_TYPES,
                    f"NAICS import ({filename})",
                )
                parsed = parse_naics_export(
                    file_bytes, validated_tt, year, month
                )
                results.append(
                    _build_import_result("naics", validated_tt, parsed)
                )

        except OkTAPParseError as exc:
            logger.warning("Bulk parse failed for %s: %s", filename, exc)
            errors.append({"filename": filename, "detail": str(exc)})
        except HTTPException as exc:
            # Tax-type validation raises HTTPException; capture it here
            # so other files can still proceed.
            errors.append({"filename": filename, "detail": exc.detail})

    return BulkImportResult(
        total_files=len(files),
        successful=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
    )


@router.get(
    "/report-types",
    response_model=ReportTypesResponse,
    status_code=status.HTTP_200_OK,
    summary="List available OkTAP report types",
)
async def list_report_types() -> ReportTypesResponse:
    """Return metadata about the OkTAP report types this API can import."""
    return ReportTypesResponse(
        report_types=[
            ReportTypeInfo(
                name="ledger",
                description=(
                    "Monthly revenue by city and tax type. "
                    "Covers lodging, sales, and use taxes."
                ),
                supported_tax_types=sorted(VALID_LEDGER_TAX_TYPES),
                requires_year_month=False,
            ),
            ReportTypeInfo(
                name="naics",
                description=(
                    "Monthly revenue by city, tax type, and NAICS industry "
                    "code. Covers sales and use taxes."
                ),
                supported_tax_types=sorted(VALID_NAICS_TAX_TYPES),
                requires_year_month=True,
            ),
        ]
    )
