"""Pytest session-scoped fixtures for the full test suite.

Ensures any tables that are not part of the core schema.sql (e.g., contacts,
which is populated by import scripts) exist before tests run, so that API
endpoints which JOIN those tables don't raise UndefinedTable errors.
"""

from __future__ import annotations

import pytest

from app.db.psycopg import get_cursor


@pytest.fixture(scope="session", autouse=True)
def ensure_contacts_table() -> None:
    """Create the contacts table if it doesn't already exist.

    The contacts table is normally created by scripts/import_contacts.py, not
    by the core schema migration. Tests that hit the GTM pipeline endpoint need
    this table to exist (even if empty) so the LEFT JOIN in the pipeline query
    doesn't error.
    """
    with get_cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id                   SERIAL PRIMARY KEY,
                batch_id             VARCHAR(20)  NOT NULL,
                jurisdiction_type    VARCHAR(10)  NOT NULL
                    CHECK (jurisdiction_type IN ('city', 'county')),
                jurisdiction_name    VARCHAR(255) NOT NULL,
                population_rank_2024 INTEGER,
                office_title         VARCHAR(255),
                district_or_ward     VARCHAR(100),
                person_name          VARCHAR(255),
                phone                VARCHAR(50),
                email                VARCHAR(255),
                contact_type         VARCHAR(30),
                source_url           TEXT,
                notes                TEXT,
                verified_date        DATE,
                created_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
                updated_at           TIMESTAMPTZ  NOT NULL DEFAULT now()
            )
            """
        )
