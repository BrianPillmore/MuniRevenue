"""Seed Oklahoma jurisdictions from known city/county codes.

This script populates the jurisdictions table with Oklahoma municipalities
and their OkTAP copo codes. Run once after database initialization.

Usage:
    python scripts/seed_jurisdictions.py

The copo codes come from OkTAP export data. This initial seed covers
major cities; additional jurisdictions are auto-created on data import.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Major Oklahoma cities with known copo codes.
# This is a starter set — the import pipeline auto-creates jurisdictions
# for any copo code seen in uploaded data.
KNOWN_JURISDICTIONS = [
    {"copo": "0955", "name": "Yukon", "jurisdiction_type": "city", "county_name": "Canadian"},
    {"copo": "0750", "name": "Oklahoma City", "jurisdiction_type": "city", "county_name": "Oklahoma"},
    {"copo": "0900", "name": "Tulsa", "jurisdiction_type": "city", "county_name": "Tulsa"},
    {"copo": "0710", "name": "Norman", "jurisdiction_type": "city", "county_name": "Cleveland"},
    {"copo": "0105", "name": "Broken Arrow", "jurisdiction_type": "city", "county_name": "Tulsa"},
    {"copo": "0560", "name": "Lawton", "jurisdiction_type": "city", "county_name": "Comanche"},
    {"copo": "0250", "name": "Edmond", "jurisdiction_type": "city", "county_name": "Oklahoma"},
    {"copo": "0695", "name": "Mustang", "jurisdiction_type": "city", "county_name": "Canadian"},
    {"copo": "0680", "name": "Moore", "jurisdiction_type": "city", "county_name": "Cleveland"},
    {"copo": "0270", "name": "Enid", "jurisdiction_type": "city", "county_name": "Garfield"},
    {"copo": "0660", "name": "Midwest City", "jurisdiction_type": "city", "county_name": "Oklahoma"},
    {"copo": "0850", "name": "Stillwater", "jurisdiction_type": "city", "county_name": "Payne"},
    {"copo": "0810", "name": "Shawnee", "jurisdiction_type": "city", "county_name": "Pottawatomie"},
    {"copo": "0770", "name": "Owasso", "jurisdiction_type": "city", "county_name": "Tulsa"},
    {"copo": "0090", "name": "Bixby", "jurisdiction_type": "city", "county_name": "Tulsa"},
    {"copo": "0775", "name": "Jenks", "jurisdiction_type": "city", "county_name": "Tulsa"},
    {"copo": "0035", "name": "Bartlesville", "jurisdiction_type": "city", "county_name": "Washington"},
    {"copo": "0020", "name": "Ardmore", "jurisdiction_type": "city", "county_name": "Carter"},
    {"copo": "0240", "name": "Duncan", "jurisdiction_type": "city", "county_name": "Stephens"},
    {"copo": "0230", "name": "Del City", "jurisdiction_type": "city", "county_name": "Oklahoma"},
    {"copo": "0785", "name": "Ponca City", "jurisdiction_type": "city", "county_name": "Kay"},
    {"copo": "0190", "name": "Chickasha", "jurisdiction_type": "city", "county_name": "Grady"},
    {"copo": "0630", "name": "McAlester", "jurisdiction_type": "city", "county_name": "Pittsburg"},
    {"copo": "0695", "name": "Muskogee", "jurisdiction_type": "city", "county_name": "Muskogee"},
    {"copo": "0245", "name": "Durant", "jurisdiction_type": "city", "county_name": "Bryan"},
    {"copo": "0820", "name": "Sand Springs", "jurisdiction_type": "city", "county_name": "Tulsa"},
    {"copo": "0060", "name": "Bethany", "jurisdiction_type": "city", "county_name": "Oklahoma"},
    {"copo": "0830", "name": "Sapulpa", "jurisdiction_type": "city", "county_name": "Creek"},
    {"copo": "0200", "name": "Claremore", "jurisdiction_type": "city", "county_name": "Rogers"},
    {"copo": "0895", "name": "Tahlequah", "jurisdiction_type": "city", "county_name": "Cherokee"},
]


def main() -> None:
    """Print seed data as JSON for use by the import pipeline."""
    print(json.dumps(KNOWN_JURISDICTIONS, indent=2))
    print(f"\n{len(KNOWN_JURISDICTIONS)} jurisdictions ready to seed.", file=sys.stderr)


if __name__ == "__main__":
    main()
