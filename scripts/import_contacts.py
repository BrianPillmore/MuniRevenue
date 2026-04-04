#!/usr/bin/env python3
"""
Import all city and county contacts CSVs into the contacts table.
Run from repo root: python scripts/import_contacts.py
"""
import asyncio
import csv
import os
import re
from datetime import date
from pathlib import Path

import asyncpg

RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "research_contacts"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/citytax")

CITY_PATTERN = re.compile(r"city_contacts_batch_(\d+)\.csv")
COUNTY_PATTERN = re.compile(r"county_contacts_batch_(\d+)\.csv")


def parse_date(s: str) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def nullify(s: str) -> str | None:
    return s.strip() if s.strip() else None


async def main():
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id SERIAL PRIMARY KEY,
            batch_id VARCHAR(20) NOT NULL,
            jurisdiction_type VARCHAR(10) NOT NULL CHECK (jurisdiction_type IN ('city', 'county')),
            jurisdiction_name VARCHAR(255) NOT NULL,
            population_rank_2024 INTEGER,
            office_title VARCHAR(255),
            district_or_ward VARCHAR(100),
            person_name VARCHAR(255),
            phone VARCHAR(50),
            email VARCHAR(255),
            contact_type VARCHAR(30),
            source_url TEXT,
            notes TEXT,
            verified_date DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    inserted = 0
    skipped = 0

    for csv_file in sorted(RAW_DIR.glob("*_contacts_batch_*.csv")):
        if CITY_PATTERN.match(csv_file.name):
            jurisdiction_type = "city"
        elif COUNTY_PATTERN.match(csv_file.name):
            jurisdiction_type = "county"
        else:
            continue

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    await conn.execute("""
                        INSERT INTO contacts (
                            batch_id, jurisdiction_type, jurisdiction_name,
                            population_rank_2024, office_title, district_or_ward,
                            person_name, phone, email, contact_type,
                            source_url, notes, verified_date
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                        ON CONFLICT DO NOTHING
                    """,
                        nullify(row.get("batch_id", "")),
                        jurisdiction_type,
                        nullify(row.get("jurisdiction_name", "")),
                        int(row["population_rank_2024"]) if row.get("population_rank_2024") else None,
                        nullify(row.get("office_title", "")),
                        nullify(row.get("district_or_ward") or row.get("district", "")),
                        nullify(row.get("person_name", "")),
                        nullify(row.get("phone", "")),
                        nullify(row.get("email", "")),
                        nullify(row.get("contact_type", "")),
                        nullify(row.get("source_url", "")),
                        nullify(row.get("notes", "")),
                        parse_date(row.get("verified_date", "")),
                    )
                    inserted += 1
                except Exception as e:
                    print(f"  SKIP {csv_file.name}: {e}")
                    skipped += 1

    print(f"Done: {inserted} inserted, {skipped} skipped")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
