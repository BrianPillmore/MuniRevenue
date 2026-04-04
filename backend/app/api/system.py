from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.security import AuthContext, SecuritySettings, require_scopes
from app.db.psycopg import get_conn
from app.services.email_report import (
    EmailSettings,
    ReportRecipient,
    SendReportsResult,
    load_email_settings,
    send_reports_after_import,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])


# ---------------------------------------------------------------------------
# Existing system response models
# ---------------------------------------------------------------------------


class AuthMeResponse(BaseModel):
    subject: str | None
    roles: list[str]
    scopes: list[str]
    auth_mode: str
    auth_method: str
    request_id: str | None = None


class SecurityStatusResponse(BaseModel):
    auth_mode: str
    rate_limit_enabled: bool
    rate_limit_requests: int
    rate_limit_window_seconds: int
    force_https: bool
    trust_forwarded_for: bool
    allowed_hosts: list[str]
    cors_origins: list[str]
    csrf_trusted_origins: list[str]
    proxy_subject_headers: list[str]
    proxy_role_headers: list[str]
    proxy_scope_headers: list[str]
    openapi_enabled: bool


# ---------------------------------------------------------------------------
# Report dispatch request / response models
# ---------------------------------------------------------------------------


class ReportRecipientSchema(BaseModel):
    """A single jurisdiction-to-email mapping for the report dispatch."""
    copo: str = Field(..., description="Four-digit OkTAP jurisdiction code.", min_length=4, max_length=4)
    jurisdiction_name: str = Field(..., description="Human-readable jurisdiction name.")
    email: str = Field(..., description="Recipient email address.")


class SendReportsRequest(BaseModel):
    """Request body for POST /api/admin/send-reports."""

    report_month: date = Field(
        ...,
        description=(
            "The voucher month to report on (first day of month, e.g. 2026-03-01). "
            "Must be the first day of the month."
        ),
    )
    recipients: list[ReportRecipientSchema] = Field(
        ...,
        min_length=1,
        description="List of jurisdiction contacts to receive reports.",
    )


class SendReportsResponse(BaseModel):
    """Aggregate result of a report dispatch run."""

    report_month: date
    attempted: int
    sent: int
    skipped_no_data: int
    failed: int
    errors: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Existing routes
# ---------------------------------------------------------------------------


@router.get(
    "/auth/me",
    response_model=AuthMeResponse,
    dependencies=[Depends(require_scopes("api:read"))],
)
def get_auth_me(request: Request) -> AuthMeResponse:
    auth_context: AuthContext = request.state.auth_context
    return AuthMeResponse(
        subject=auth_context.subject,
        roles=list(auth_context.roles),
        scopes=list(auth_context.scopes),
        auth_mode=auth_context.auth_mode,
        auth_method=auth_context.auth_method,
        request_id=getattr(request.state, "request_id", None),
    )


@router.get(
    "/admin/security",
    response_model=SecurityStatusResponse,
    dependencies=[Depends(require_scopes("api:admin"))],
)
def get_security_status(request: Request) -> SecurityStatusResponse:
    settings: SecuritySettings = request.app.state.security_settings
    return SecurityStatusResponse(
        auth_mode=settings.auth_mode,
        rate_limit_enabled=settings.rate_limit_enabled,
        rate_limit_requests=settings.rate_limit_requests,
        rate_limit_window_seconds=settings.rate_limit_window_seconds,
        force_https=settings.force_https,
        trust_forwarded_for=settings.trust_forwarded_for,
        allowed_hosts=settings.allowed_hosts,
        cors_origins=settings.cors_origins,
        csrf_trusted_origins=settings.csrf_trusted_origins,
        proxy_subject_headers=list(settings.proxy_auth_headers),
        proxy_role_headers=list(settings.proxy_role_headers),
        proxy_scope_headers=list(settings.proxy_scope_headers),
        openapi_enabled=settings.openapi_enabled,
    )


# ---------------------------------------------------------------------------
# Report dispatch route
# ---------------------------------------------------------------------------


@router.post(
    "/admin/send-reports",
    response_model=SendReportsResponse,
    summary="Dispatch post-import revenue reports",
    description=(
        "Builds and delivers HTML revenue summary emails for each jurisdiction listed in "
        "`recipients`. Only tax types that have actual ledger records in the database for "
        "a given jurisdiction are included. Delivery mode is controlled by the "
        "`MUNIREV_EMAIL_MODE` environment variable (log | smtp)."
    ),
    dependencies=[Depends(require_scopes("api:admin"))],
)
def send_reports(body: SendReportsRequest) -> SendReportsResponse:
    """Trigger post-import report emails for a list of jurisdiction contacts.

    The endpoint is synchronous -- it completes all sends before returning.
    For large recipient lists consider calling this from a background task
    or the load_data script directly (which uses the same service layer).

    Returns a summary of attempted, sent, skipped, and failed reports.
    """
    settings: EmailSettings = load_email_settings()

    service_recipients = [
        ReportRecipient(
            copo=r.copo,
            jurisdiction_name=r.jurisdiction_name,
            email=r.email,
        )
        for r in body.recipients
    ]

    conn = get_conn()
    try:
        result: SendReportsResult = send_reports_after_import(
            recipients=service_recipients,
            report_month=body.report_month,
            db_conn=conn,
            settings=settings,
        )
    finally:
        conn.close()

    return SendReportsResponse(
        report_month=result.report_month,
        attempted=result.attempted,
        sent=result.sent,
        skipped_no_data=result.skipped_no_data,
        failed=result.failed,
        errors=result.errors,
    )
