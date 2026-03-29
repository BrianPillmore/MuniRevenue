from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://munirev:munirev@localhost:5432/munirev",
)

# For SQLite fallback during development without PostgreSQL
SQLITE_FALLBACK = os.environ.get("MUNIREV_SQLITE_FALLBACK", "")

def get_engine():
    if SQLITE_FALLBACK:
        from sqlalchemy import create_engine as _ce
        return _ce(f"sqlite:///{SQLITE_FALLBACK}", echo=False)
    return create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)


engine = get_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Session:
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
