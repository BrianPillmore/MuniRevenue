from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras


DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://munirev:changeme@localhost:5432/munirev",
)


def get_conn() -> psycopg2.extensions.connection:
    return psycopg2.connect(DATABASE_URL)


@contextmanager
def get_cursor(*, dict_cursor: bool = True) -> Iterator[psycopg2.extensions.cursor]:
    conn = get_conn()
    try:
        cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
