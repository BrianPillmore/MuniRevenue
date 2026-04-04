"""Contacts query endpoints for MuniRev GTM outreach.

This router must be registered in ``app.main``:

    from app.api.contacts import router as contacts_router
    app.include_router(contacts_router)

All queries use psycopg2 with parameterized statements to prevent SQL injection.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

from app.db.psycopg import get_cursor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("/")
def list_contacts(
    jurisdiction_type: str | None = Query(None, description="Filter by 'city' or 'county'"),
    jurisdiction_name: str | None = Query(None, description="Filter by jurisdiction name (partial match)"),
    contact_type: str | None = Query(None, description="Filter by contact type"),
    has_email: bool | None = Query(None, description="Filter to contacts with a non-empty email"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict[str, Any]]:
    """List contacts with optional filtering and pagination."""
    conditions: list[str] = []
    params: list[Any] = []

    if jurisdiction_type is not None:
        conditions.append("jurisdiction_type = %s")
        params.append(jurisdiction_type)

    if jurisdiction_name is not None:
        conditions.append("jurisdiction_name ILIKE %s")
        params.append(f"%{jurisdiction_name}%")

    if contact_type is not None:
        conditions.append("contact_type = %s")
        params.append(contact_type)

    if has_email is True:
        conditions.append("email IS NOT NULL AND email != ''")

    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT
            id,
            jurisdiction_type,
            jurisdiction_name,
            population_rank_2024,
            office_title,
            district_or_ward,
            person_name,
            phone,
            email,
            contact_type,
            source_url,
            notes,
            verified_date
        FROM contacts
        {where_clause}
        ORDER BY
            population_rank_2024 ASC NULLS LAST,
            jurisdiction_name ASC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    return [
        {
            **dict(row),
            "verified_date": row["verified_date"].isoformat() if row["verified_date"] else None,
        }
        for row in rows
    ]


@router.get("/summary")
def contacts_summary() -> list[dict[str, Any]]:
    """Count contacts by jurisdiction type and contact type, including email/phone coverage."""
    sql = """
        SELECT
            jurisdiction_type,
            contact_type,
            COUNT(*)                                                    AS count,
            COUNT(*) FILTER (WHERE email IS NOT NULL AND email != '')   AS with_email,
            COUNT(*) FILTER (WHERE phone IS NOT NULL AND phone != '')   AS with_phone
        FROM contacts
        GROUP BY jurisdiction_type, contact_type
        ORDER BY jurisdiction_type, contact_type
    """
    with get_cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    return [dict(row) for row in rows]
