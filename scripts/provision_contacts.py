#!/usr/bin/env python3
"""
Bulk account provisioner for MuniRev outreach.

Reads all city_contacts_batch_*.csv and county_contacts_batch_*.csv files from
data/raw/research_contacts/, provisions an app_users account for each contact
that has an email address, and registers a jurisdiction interest.

Usage:
    cd backend && python ../scripts/provision_contacts.py
    DATABASE_URL=postgresql://... python ../scripts/provision_contacts.py
"""
from __future__ import annotations

import csv
import logging
import os
import re
import sys
from pathlib import Path

# Resolve paths relative to repo root regardless of cwd.
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
RAW_DIR = REPO_ROOT / "data" / "raw" / "research_contacts"

# Put the backend package on the Python path so we can import app modules.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load a .env file from the repo root if it exists (dev convenience).
_env_file = REPO_ROOT / ".env"
if _env_file.exists():
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _, _val = _line.partition("=")
                os.environ.setdefault(_key.strip(), _val.strip())

from app.db.psycopg import get_cursor  # noqa: E402 (after path setup)
from app.services.outreach import provision_account  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

CITY_PATTERN = re.compile(r"city_contacts_batch_.*\.csv$", re.IGNORECASE)
COUNTY_PATTERN = re.compile(r"county_contacts_batch_.*\.csv$", re.IGNORECASE)


def _nullify(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _lookup_copo(jurisdiction_name: str) -> str | None:
    """
    Try to find the copo for a city name using a case-insensitive similarity
    search against the jurisdictions table.  Returns None if not found.
    """
    if not jurisdiction_name:
        return None
    name_clean = jurisdiction_name.strip()
    with get_cursor() as cur:
        # Exact match first (case-insensitive).
        cur.execute(
            """
            SELECT copo FROM jurisdictions
            WHERE LOWER(name) = LOWER(%s)
              AND jurisdiction_type = 'city'
            LIMIT 1
            """,
            [name_clean],
        )
        row = cur.fetchone()
        if row:
            return row["copo"]

        # Trigram similarity fallback (requires pg_trgm, which is in schema.sql).
        cur.execute(
            """
            SELECT copo, similarity(name, %s) AS sim
            FROM jurisdictions
            WHERE jurisdiction_type = 'city'
              AND similarity(name, %s) > 0.45
            ORDER BY sim DESC
            LIMIT 1
            """,
            [name_clean, name_clean],
        )
        row = cur.fetchone()
        if row:
            logger.debug(
                "Fuzzy-matched '%s' -> copo=%s (similarity=%.2f)",
                name_clean, row["copo"], float(row["sim"]),
            )
            return row["copo"]

    return None


def _process_file(csv_path: Path, jurisdiction_type: str) -> tuple[int, int, int]:
    """
    Process one CSV file.  Returns (created, updated, skipped) counts.

    We distinguish created vs updated by checking whether the row existed before
    via a quick pre-check, but since provision_account uses ON CONFLICT and
    psycopg2 doesn't surface xmax easily, we track by whether email_verified_at
    was already set before our upsert.  For simplicity the script counts both
    INSERT and UPDATE paths together as "processed" and tracks only skips.
    """
    created = 0
    updated = 0
    skipped = 0

    logger.info("Processing %s (%s)...", csv_path.name, jurisdiction_type)

    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            email = _nullify(row.get("email") or row.get("Email") or "")
            if not email:
                skipped += 1
                continue

            person_name = _nullify(
                row.get("person_name") or row.get("Person Name") or row.get("name") or ""
            )
            office_title = _nullify(
                row.get("office_title") or row.get("Office Title") or row.get("title") or ""
            )
            jurisdiction_name = _nullify(
                row.get("jurisdiction_name") or row.get("Jurisdiction Name") or ""
            )
            if not jurisdiction_name:
                logger.warning("Row missing jurisdiction_name, skipping email=%s", email)
                skipped += 1
                continue

            # Resolve copo for cities.
            copo: str | None = None
            if jurisdiction_type == "city":
                copo = _nullify(row.get("copo") or row.get("COPO") or "")
                if not copo:
                    copo = _lookup_copo(jurisdiction_name)
                if not copo:
                    logger.debug(
                        "No copo found for city '%s', email=%s; interest will be skipped.",
                        jurisdiction_name, email,
                    )

            # Determine whether the account already exists so we can report accurately.
            with get_cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM app_users WHERE email_normalized = LOWER(%s)",
                    [email.strip()],
                )
                existed = cur.fetchone() is not None

            try:
                provision_account(
                    email=email,
                    display_name=person_name,
                    job_title=office_title,
                    organization_name=jurisdiction_name,
                    jurisdiction_name=jurisdiction_name,
                    jurisdiction_type=jurisdiction_type,
                    copo=copo,
                )
                if existed:
                    updated += 1
                else:
                    created += 1
            except Exception as exc:
                logger.error(
                    "Failed to provision %s (%s): %s", email, jurisdiction_name, exc
                )
                skipped += 1

    return created, updated, skipped


def main() -> None:
    if not RAW_DIR.exists():
        logger.error("Research contacts directory not found: %s", RAW_DIR)
        sys.exit(1)

    csv_files = sorted(RAW_DIR.glob("*_contacts_batch_*.csv"))
    if not csv_files:
        logger.warning("No contact CSV files found in %s", RAW_DIR)
        return

    total_created = 0
    total_updated = 0
    total_skipped = 0

    for csv_path in csv_files:
        if CITY_PATTERN.search(csv_path.name):
            jtype = "city"
        elif COUNTY_PATTERN.search(csv_path.name):
            jtype = "county"
        else:
            logger.debug("Skipping unrecognized file: %s", csv_path.name)
            continue

        c, u, s = _process_file(csv_path, jtype)
        total_created += c
        total_updated += u
        total_skipped += s
        logger.info(
            "  %s: %d created, %d updated, %d skipped",
            csv_path.name, c, u, s,
        )

    print(
        f"\nSummary: {total_created} accounts created, "
        f"{total_updated} updated, "
        f"{total_skipped} skipped (no email or error)."
    )


if __name__ == "__main__":
    main()
