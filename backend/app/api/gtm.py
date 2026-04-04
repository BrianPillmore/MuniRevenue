"""Go-to-market dashboard API — admin only.

Endpoint group: GET /api/admin/gtm/*
              POST /api/admin/gtm/send-reports

Returns pipeline and funnel data for tracking outreach progress across all
Oklahoma municipalities: contact coverage, signed-up users, and revenue data.
Also provides a trigger endpoint to send personalized report emails.

Authentication: requires an active browser session with is_admin = TRUE.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.psycopg import get_cursor
from app.user_auth import UserSessionContext, require_admin_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/gtm", tags=["gtm"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class GtmStats(BaseModel):
    total_cities: int
    cities_with_contact: int
    cities_with_email: int
    cities_with_user: int
    total_counties: int
    counties_with_contact: int
    counties_with_email: int
    counties_with_user: int
    total_active_users: int
    total_magic_links_sent: int
    total_contacts: int
    total_contacts_with_email: int
    total_contacts_with_phone: int


class GtmCityRow(BaseModel):
    copo: str
    name: str
    jurisdiction_type: str
    county_name: Optional[str]
    contact_count: int
    email_count: int
    phone_count: int
    user_count: int
    latest_data_date: Optional[str]
    latest_revenue: Optional[float]


class GtmPipelineResponse(BaseModel):
    stats: GtmStats
    cities: list[GtmCityRow]
    counties: list[GtmCityRow]


class GtmUserRow(BaseModel):
    user_id: str
    email: str
    display_name: Optional[str]
    job_title: Optional[str]
    organization_name: Optional[str]
    jurisdiction_name: Optional[str]
    copo: Optional[str]
    created_at: str
    last_login_at: Optional[str]
    status: str


class GtmUsersResponse(BaseModel):
    total: int
    users: list[GtmUserRow]


class GtmContactRow(BaseModel):
    id: int
    jurisdiction_name: str
    jurisdiction_type: str
    office_title: Optional[str]
    person_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    contact_type: Optional[str]
    verified_date: Optional[str]
    notes: Optional[str]


class GtmContactsResponse(BaseModel):
    total: int
    contacts: list[GtmContactRow]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/pipeline", response_model=GtmPipelineResponse)
def get_gtm_pipeline(
    _session: UserSessionContext = Depends(require_admin_session),
) -> GtmPipelineResponse:
    """Return full city/county pipeline with contact and user coverage."""
    with get_cursor() as cur:
        # City rows: join contacts table + user_jurisdiction_interests + ledger summary
        cur.execute(
            """
            WITH contact_counts AS (
                SELECT
                    c.jurisdiction_name,
                    COUNT(*) AS contact_count,
                    COUNT(c.email) FILTER (WHERE c.email IS NOT NULL AND c.email <> '') AS email_count,
                    COUNT(c.phone) FILTER (WHERE c.phone IS NOT NULL AND c.phone <> '') AS phone_count
                FROM contacts c
                WHERE c.jurisdiction_type = 'city'
                GROUP BY c.jurisdiction_name
            ),
            user_counts AS (
                SELECT
                    i.copo,
                    COUNT(DISTINCT i.user_id) AS user_count
                FROM user_jurisdiction_interests i
                WHERE i.interest_type = 'city'
                GROUP BY i.copo
            ),
            ledger_summary AS (
                SELECT
                    copo,
                    MAX(voucher_date)::text AS latest_data_date,
                    SUM(returned) FILTER (
                        WHERE voucher_date = (
                            SELECT MAX(v2.voucher_date)
                            FROM ledger_records v2
                            WHERE v2.copo = ledger_records.copo
                              AND v2.tax_type = 'sales'
                        )
                        AND tax_type = 'sales'
                    )::float8 AS latest_revenue
                FROM ledger_records
                GROUP BY copo
            )
            SELECT
                j.copo,
                j.name,
                j.jurisdiction_type,
                j.county_name,
                COALESCE(cc.contact_count, 0)::int AS contact_count,
                COALESCE(cc.email_count, 0)::int    AS email_count,
                COALESCE(cc.phone_count, 0)::int    AS phone_count,
                COALESCE(uc.user_count, 0)::int     AS user_count,
                ls.latest_data_date,
                ls.latest_revenue
            FROM jurisdictions j
            LEFT JOIN contact_counts cc ON LOWER(cc.jurisdiction_name) = LOWER(j.name)
            LEFT JOIN user_counts uc ON uc.copo = j.copo
            LEFT JOIN ledger_summary ls ON ls.copo = j.copo
            WHERE j.jurisdiction_type = 'city'
            ORDER BY j.name
            """
        )
        city_rows = [GtmCityRow(**dict(r)) for r in cur.fetchall()]

        # County rows
        cur.execute(
            """
            WITH contact_counts AS (
                SELECT
                    c.jurisdiction_name,
                    COUNT(*) AS contact_count,
                    COUNT(c.email) FILTER (WHERE c.email IS NOT NULL AND c.email <> '') AS email_count,
                    COUNT(c.phone) FILTER (WHERE c.phone IS NOT NULL AND c.phone <> '') AS phone_count
                FROM contacts c
                WHERE c.jurisdiction_type = 'county'
                GROUP BY c.jurisdiction_name
            ),
            user_counts AS (
                SELECT
                    i.copo,
                    COUNT(DISTINCT i.user_id) AS user_count
                FROM user_jurisdiction_interests i
                WHERE i.interest_type = 'county'
                GROUP BY i.copo
            )
            SELECT
                j.copo,
                j.name,
                j.jurisdiction_type,
                NULL::text AS county_name,
                COALESCE(cc.contact_count, 0)::int AS contact_count,
                COALESCE(cc.email_count, 0)::int    AS email_count,
                COALESCE(cc.phone_count, 0)::int    AS phone_count,
                COALESCE(uc.user_count, 0)::int     AS user_count,
                NULL::text AS latest_data_date,
                NULL::float8 AS latest_revenue
            FROM jurisdictions j
            LEFT JOIN contact_counts cc ON LOWER(cc.jurisdiction_name) = LOWER(j.name)
            LEFT JOIN user_counts uc ON uc.copo = j.copo
            WHERE j.jurisdiction_type = 'county'
            ORDER BY j.name
            """
        )
        county_rows = [GtmCityRow(**dict(r)) for r in cur.fetchall()]

        # Aggregate stats
        cur.execute("SELECT COUNT(*) AS n FROM app_users WHERE status = 'active'")
        total_active_users = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM user_magic_links")
        total_magic_links = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM contacts")
        total_contacts = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM contacts WHERE email IS NOT NULL AND email <> ''")
        total_contacts_with_email = cur.fetchone()["n"]

        cur.execute("SELECT COUNT(*) AS n FROM contacts WHERE phone IS NOT NULL AND phone <> ''")
        total_contacts_with_phone = cur.fetchone()["n"]

    stats = GtmStats(
        total_cities=len(city_rows),
        cities_with_contact=sum(1 for r in city_rows if r.contact_count > 0),
        cities_with_email=sum(1 for r in city_rows if r.email_count > 0),
        cities_with_user=sum(1 for r in city_rows if r.user_count > 0),
        total_counties=len(county_rows),
        counties_with_contact=sum(1 for r in county_rows if r.contact_count > 0),
        counties_with_email=sum(1 for r in county_rows if r.email_count > 0),
        counties_with_user=sum(1 for r in county_rows if r.user_count > 0),
        total_active_users=total_active_users,
        total_magic_links_sent=total_magic_links,
        total_contacts=total_contacts,
        total_contacts_with_email=total_contacts_with_email,
        total_contacts_with_phone=total_contacts_with_phone,
    )

    return GtmPipelineResponse(stats=stats, cities=city_rows, counties=county_rows)


@router.get("/users", response_model=GtmUsersResponse)
def get_gtm_users(
    _session: UserSessionContext = Depends(require_admin_session),
) -> GtmUsersResponse:
    """Return all registered users with their jurisdiction and login activity."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT
                u.user_id::text,
                u.email,
                u.display_name,
                u.job_title,
                u.organization_name,
                i.label   AS jurisdiction_name,
                i.copo,
                u.created_at::text,
                u.last_login_at::text,
                u.status
            FROM app_users u
            LEFT JOIN LATERAL (
                SELECT label, copo
                FROM user_jurisdiction_interests
                WHERE user_id = u.user_id
                LIMIT 1
            ) i ON TRUE
            ORDER BY u.created_at DESC
            """
        )
        rows = [GtmUserRow(**dict(r)) for r in cur.fetchall()]

    return GtmUsersResponse(total=len(rows), users=rows)


@router.get("/contacts", response_model=GtmContactsResponse)
def get_gtm_contacts(
    search: str = "",
    _session: UserSessionContext = Depends(require_admin_session),
) -> GtmContactsResponse:
    """Return all contacts from the contacts table, optionally filtered by search."""
    with get_cursor() as cur:
        if search.strip():
            q = f"%{search.strip().lower()}%"
            cur.execute(
                """
                SELECT
                    id,
                    jurisdiction_name,
                    jurisdiction_type,
                    office_title,
                    person_name,
                    phone,
                    email,
                    contact_type,
                    verified_date::text,
                    notes
                FROM contacts
                WHERE LOWER(jurisdiction_name) LIKE %s
                   OR LOWER(COALESCE(email, '')) LIKE %s
                   OR LOWER(COALESCE(person_name, '')) LIKE %s
                   OR LOWER(COALESCE(office_title, '')) LIKE %s
                ORDER BY jurisdiction_name, office_title
                """,
                [q, q, q, q],
            )
        else:
            cur.execute(
                """
                SELECT
                    id,
                    jurisdiction_name,
                    jurisdiction_type,
                    office_title,
                    person_name,
                    phone,
                    email,
                    contact_type,
                    verified_date::text,
                    notes
                FROM contacts
                ORDER BY jurisdiction_name, office_title
                """
            )
        rows = [GtmContactRow(**dict(r)) for r in cur.fetchall()]

    return GtmContactsResponse(total=len(rows), contacts=rows)


# ---------------------------------------------------------------------------
# Send-reports endpoint
# ---------------------------------------------------------------------------


class SendReportsRequest(BaseModel):
    year: int = Field(..., ge=2000, le=2100, description="Reporting year (e.g. 2026)")
    month: int = Field(..., ge=1, le=12, description="Reporting month 1-12")


class SendReportsResponse(BaseModel):
    queued: bool
    period: str


_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _run_send(year: int, month: int) -> None:
    from app.services.outreach import send_reports_after_import
    try:
        send_reports_after_import(period_year=year, period_month=month)
    except Exception:
        logger.exception("send_reports background task failed for %d-%02d", year, month)


@router.post("/send-reports", response_model=SendReportsResponse)
def send_reports(
    body: SendReportsRequest,
    background_tasks: BackgroundTasks,
    _session: UserSessionContext = Depends(require_admin_session),
) -> SendReportsResponse:
    """Enqueue a personalized email campaign for the given reporting period.

    Sends each active user a city-specific email with revenue data, anomaly
    counts, and a one-click magic-link to their report page.  The send runs
    asynchronously in the background so this endpoint returns immediately.
    """
    period_label = f"{_MONTH_NAMES[body.month - 1]} {body.year}"
    logger.info(
        "Admin %s triggered send_reports for %s",
        _session.user_id,
        period_label,
    )
    background_tasks.add_task(_run_send, body.year, body.month)
    return SendReportsResponse(queued=True, period=period_label)
