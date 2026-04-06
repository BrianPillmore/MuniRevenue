"""Prospects admin API — comprehensive view of all Oklahoma jurisdictions as prospects.

Endpoint group: GET /api/admin/prospects/*

Combines contact data from the DB with jurisdiction metadata (population, tier)
from the research_contacts CSV files to provide a full CRM-like prospect view.

Authentication: requires an active browser session with is_admin = TRUE.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.db.psycopg import get_cursor
from app.user_auth import UserSessionContext, require_admin_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/prospects", tags=["prospects"])

RAW_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "raw" / "research_contacts"


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ProspectContact(BaseModel):
    id: int
    office_title: Optional[str]
    district_or_ward: Optional[str]
    person_name: Optional[str]
    phone: Optional[str]
    email: Optional[str]
    contact_type: Optional[str]
    verified_date: Optional[str]
    notes: Optional[str]
    batch_id: Optional[str]


class ProspectRow(BaseModel):
    jurisdiction_name: str
    jurisdiction_type: str
    county: Optional[str]
    population_2024: Optional[int]
    population_rank: Optional[int]
    tier: str  # "tier1", "tier2", "tier3"
    total_contacts: int
    contacts_with_email: int
    contacts_with_phone: int
    contacts_with_name: int
    key_contact_name: Optional[str]
    key_contact_title: Optional[str]
    key_contact_email: Optional[str]
    user_count: int
    outreach_ready: bool  # has at least one email contact


class ProspectStats(BaseModel):
    total_prospects: int
    tier1_count: int
    tier2_count: int
    tier3_count: int
    with_email: int
    with_phone: int
    with_user: int
    outreach_ready: int
    total_contacts: int
    total_contacts_with_email: int


class ProspectsListResponse(BaseModel):
    stats: ProspectStats
    prospects: list[ProspectRow]


class ProspectDetailResponse(BaseModel):
    jurisdiction_name: str
    jurisdiction_type: str
    county: Optional[str]
    population_2024: Optional[int]
    population_rank: Optional[int]
    tier: str
    user_count: int
    contacts: list[ProspectContact]


# ---------------------------------------------------------------------------
# CSV helpers — load jurisdiction metadata at request time
# ---------------------------------------------------------------------------

def _load_priority_data() -> dict[str, dict]:
    """Load population/county data from priority CSV files, keyed by lowercase jurisdiction name."""
    data: dict[str, dict] = {}

    for csv_file in sorted(RAW_DIR.glob("city_batch_*_priority.csv")):
        try:
            with open(csv_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name = (row.get("jurisdiction_name") or "").strip()
                    if not name:
                        continue
                    key = name.lower()
                    pop = row.get("population_2024", "").strip()
                    rank = row.get("population_rank_2024", "").strip()
                    if key not in data or (pop and not data[key].get("population_2024")):
                        data[key] = {
                            "jurisdiction_type": "city",
                            "county": (row.get("county") or "").strip() or None,
                            "population_2024": int(pop) if pop else None,
                            "population_rank": int(rank) if rank else None,
                        }
        except Exception:
            logger.warning("Failed to read %s", csv_file, exc_info=True)

    for csv_file in sorted(RAW_DIR.glob("county_batch_*_priority.csv")):
        try:
            with open(csv_file, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    name = (row.get("jurisdiction_name") or "").strip()
                    if not name:
                        continue
                    key = name.lower()
                    pop = row.get("population_2024", "").strip()
                    rank = row.get("population_rank_2024", "").strip()
                    if key not in data or (pop and not data[key].get("population_2024")):
                        data[key] = {
                            "jurisdiction_type": "county",
                            "county": None,
                            "population_2024": int(pop) if pop else None,
                            "population_rank": int(rank) if rank else None,
                        }
        except Exception:
            logger.warning("Failed to read %s", csv_file, exc_info=True)

    return data


def _classify_tier(jurisdiction_type: str, population_rank: int | None, population: int | None) -> str:
    """Classify a jurisdiction into GTM tiers per the strategy doc."""
    if jurisdiction_type == "county":
        return "tier2"
    if population_rank is not None and population_rank <= 20:
        return "tier1"
    if population is not None:
        if population >= 5000:
            return "tier2"
        return "tier3"
    if population_rank is not None and population_rank <= 100:
        return "tier2"
    return "tier3"


# Priority titles for identifying key contacts
_KEY_TITLES = [
    "mayor", "finance director", "city manager", "city administrator",
    "city clerk", "treasurer", "county commissioner", "county treasurer",
]


def _pick_key_contact(contacts: list[dict]) -> tuple[str | None, str | None, str | None]:
    """Pick the most important contact for a jurisdiction (name, title, email)."""
    for priority in _KEY_TITLES:
        for c in contacts:
            title = (c.get("office_title") or "").lower()
            if priority in title and c.get("email"):
                return c.get("person_name"), c.get("office_title"), c.get("email")
    # Fallback: first contact with email
    for c in contacts:
        if c.get("email"):
            return c.get("person_name"), c.get("office_title"), c.get("email")
    # Fallback: first contact with a name
    for c in contacts:
        if c.get("person_name"):
            return c.get("person_name"), c.get("office_title"), c.get("email")
    return None, None, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ProspectsListResponse)
def list_prospects(
    tier: Optional[str] = Query(None, description="Filter by tier: tier1, tier2, tier3"),
    jtype: Optional[str] = Query(None, description="Filter by type: city, county"),
    search: str = Query("", description="Search by jurisdiction name"),
    _session: UserSessionContext = Depends(require_admin_session),
) -> ProspectsListResponse:
    """Return all jurisdictions as prospects with contact coverage and tier classification."""

    priority_data = _load_priority_data()

    with get_cursor() as cur:
        # Get all contacts grouped by jurisdiction
        cur.execute("""
            SELECT
                jurisdiction_name,
                jurisdiction_type,
                COUNT(*) AS total_contacts,
                COUNT(email) FILTER (WHERE email IS NOT NULL AND email <> '') AS contacts_with_email,
                COUNT(phone) FILTER (WHERE phone IS NOT NULL AND phone <> '') AS contacts_with_phone,
                COUNT(person_name) FILTER (WHERE person_name IS NOT NULL AND person_name <> '') AS contacts_with_name
            FROM contacts
            GROUP BY jurisdiction_name, jurisdiction_type
            ORDER BY jurisdiction_name
        """)
        contact_summary = {(r["jurisdiction_name"].lower(), r["jurisdiction_type"]): dict(r) for r in cur.fetchall()}

        # Get contacts detail for key contact selection
        cur.execute("""
            SELECT jurisdiction_name, jurisdiction_type, office_title, person_name, email
            FROM contacts
            ORDER BY jurisdiction_name, id
        """)
        contacts_by_jur: dict[str, list[dict]] = {}
        for r in cur.fetchall():
            key = r["jurisdiction_name"].lower()
            contacts_by_jur.setdefault(key, []).append(dict(r))

        # Get user counts per jurisdiction
        cur.execute("""
            SELECT
                LOWER(j.name) AS jname,
                j.jurisdiction_type,
                COUNT(DISTINCT i.user_id) AS user_count
            FROM jurisdictions j
            JOIN user_jurisdiction_interests i ON i.copo = j.copo
            GROUP BY LOWER(j.name), j.jurisdiction_type
        """)
        user_counts = {(r["jname"], r["jurisdiction_type"]): r["user_count"] for r in cur.fetchall()}

        # Get all jurisdictions from the jurisdictions table
        cur.execute("""
            SELECT name, jurisdiction_type, county_name
            FROM jurisdictions
            ORDER BY name
        """)
        all_jurisdictions = [dict(r) for r in cur.fetchall()]

    # Build prospect rows
    seen = set()
    prospects: list[ProspectRow] = []

    for j in all_jurisdictions:
        name = j["name"]
        jtype_val = j["jurisdiction_type"]
        key = name.lower()
        seen.add((key, jtype_val))

        pri = priority_data.get(key, {})
        pop = pri.get("population_2024")
        rank = pri.get("population_rank")
        county = j.get("county_name") or pri.get("county")

        cs = contact_summary.get((key, jtype_val), {})
        total_contacts = cs.get("total_contacts", 0)
        email_count = cs.get("contacts_with_email", 0)
        phone_count = cs.get("contacts_with_phone", 0)
        name_count = cs.get("contacts_with_name", 0)

        uc = user_counts.get((key, jtype_val), 0)
        tier_val = _classify_tier(jtype_val, rank, pop)

        kc_name, kc_title, kc_email = _pick_key_contact(contacts_by_jur.get(key, []))

        prospects.append(ProspectRow(
            jurisdiction_name=name,
            jurisdiction_type=jtype_val,
            county=county,
            population_2024=pop,
            population_rank=rank,
            tier=tier_val,
            total_contacts=total_contacts,
            contacts_with_email=email_count,
            contacts_with_phone=phone_count,
            contacts_with_name=name_count,
            key_contact_name=kc_name,
            key_contact_title=kc_title,
            key_contact_email=kc_email,
            user_count=uc,
            outreach_ready=email_count > 0,
        ))

    # Also add jurisdictions that are in contacts but not in the jurisdictions table
    for (ckey, ctype), cs in contact_summary.items():
        if (ckey, ctype) not in seen:
            seen.add((ckey, ctype))
            pri = priority_data.get(ckey, {})
            pop = pri.get("population_2024")
            rank = pri.get("population_rank")
            county = pri.get("county")
            tier_val = _classify_tier(ctype, rank, pop)
            kc_name, kc_title, kc_email = _pick_key_contact(contacts_by_jur.get(ckey, []))

            prospects.append(ProspectRow(
                jurisdiction_name=cs["jurisdiction_name"],
                jurisdiction_type=ctype,
                county=county,
                population_2024=pop,
                population_rank=rank,
                tier=tier_val,
                total_contacts=cs["total_contacts"],
                contacts_with_email=cs["contacts_with_email"],
                contacts_with_phone=cs["contacts_with_phone"],
                contacts_with_name=cs["contacts_with_name"],
                key_contact_name=kc_name,
                key_contact_title=kc_title,
                key_contact_email=kc_email,
                user_count=0,
                outreach_ready=cs["contacts_with_email"] > 0,
            ))

    # Apply filters
    if search.strip():
        q = search.strip().lower()
        prospects = [p for p in prospects if q in p.jurisdiction_name.lower()]
    if tier:
        prospects = [p for p in prospects if p.tier == tier]
    if jtype:
        prospects = [p for p in prospects if p.jurisdiction_type == jtype]

    # Sort: tier1 first, then by population desc, then alphabetical
    tier_order = {"tier1": 0, "tier2": 1, "tier3": 2}
    prospects.sort(key=lambda p: (tier_order.get(p.tier, 9), -(p.population_2024 or 0), p.jurisdiction_name))

    # Compute stats
    stats = ProspectStats(
        total_prospects=len(prospects),
        tier1_count=sum(1 for p in prospects if p.tier == "tier1"),
        tier2_count=sum(1 for p in prospects if p.tier == "tier2"),
        tier3_count=sum(1 for p in prospects if p.tier == "tier3"),
        with_email=sum(1 for p in prospects if p.contacts_with_email > 0),
        with_phone=sum(1 for p in prospects if p.contacts_with_phone > 0),
        with_user=sum(1 for p in prospects if p.user_count > 0),
        outreach_ready=sum(1 for p in prospects if p.outreach_ready),
        total_contacts=sum(p.total_contacts for p in prospects),
        total_contacts_with_email=sum(p.contacts_with_email for p in prospects),
    )

    return ProspectsListResponse(stats=stats, prospects=prospects)


@router.get("/{jurisdiction_name}", response_model=ProspectDetailResponse)
def get_prospect_detail(
    jurisdiction_name: str,
    _session: UserSessionContext = Depends(require_admin_session),
) -> ProspectDetailResponse:
    """Return all contacts for a specific jurisdiction."""

    priority_data = _load_priority_data()
    key = jurisdiction_name.lower()

    with get_cursor() as cur:
        cur.execute("""
            SELECT
                id, office_title, district_or_ward, person_name,
                phone, email, contact_type, verified_date::text,
                notes, batch_id
            FROM contacts
            WHERE LOWER(jurisdiction_name) = %s
            ORDER BY
                CASE WHEN email IS NOT NULL AND email <> '' THEN 0 ELSE 1 END,
                office_title, person_name
        """, [key])
        contacts = [ProspectContact(**dict(r)) for r in cur.fetchall()]

        # Determine jurisdiction type from contacts
        cur.execute("""
            SELECT DISTINCT jurisdiction_type FROM contacts WHERE LOWER(jurisdiction_name) = %s
        """, [key])
        jtypes = [r["jurisdiction_type"] for r in cur.fetchall()]
        jtype = jtypes[0] if jtypes else "city"

        # Get user count
        cur.execute("""
            SELECT COUNT(DISTINCT i.user_id) AS cnt
            FROM jurisdictions j
            JOIN user_jurisdiction_interests i ON i.copo = j.copo
            WHERE LOWER(j.name) = %s
        """, [key])
        user_count = cur.fetchone()["cnt"]

    pri = priority_data.get(key, {})

    return ProspectDetailResponse(
        jurisdiction_name=jurisdiction_name,
        jurisdiction_type=jtype,
        county=pri.get("county"),
        population_2024=pri.get("population_2024"),
        population_rank=pri.get("population_rank"),
        tier=_classify_tier(jtype, pri.get("population_rank"), pri.get("population_2024")),
        user_count=user_count,
        contacts=contacts,
    )
