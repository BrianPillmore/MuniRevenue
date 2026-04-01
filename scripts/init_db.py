"""Initialize the local PostgreSQL schema for MuniRev.

Applies the checked-in PostgreSQL schema and then creates the forecast and
economic indicator support tables used by the application.

Usage:
    cd backend
    .venv/Scripts/python ../scripts/init_db.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import psycopg2

from app.services.forecasting import ensure_forecast_schema


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://munirev:changeme@localhost:5432/munirev",
)
SCHEMA_PATH = Path(__file__).parent.parent / "backend" / "app" / "db" / "schema.sql"


def main() -> None:
    log.info("Initializing database schema at %s", DB_URL)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    conn = psycopg2.connect(DB_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
                ensure_forecast_schema(cur)
        log.info("Database schema initialized successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()