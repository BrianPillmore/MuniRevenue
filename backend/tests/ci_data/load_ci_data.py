"""Load the deterministic CI fixture into the database named by DATABASE_URL.

Run after schema.sql, the auth tables and alembic. Synthetic data only; never
point this at production. Usage: python tests/ci_data/load_ci_data.py
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import psycopg2

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent.parent


def main() -> None:
    import sys

    sys.path.insert(0, str(BACKEND))
    from app.services.forecasting import ensure_forecast_schema

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute((HERE / "00_schema_compat.sql").read_text())
    ensure_forecast_schema(cur)
    cur.execute((HERE / "10_seed.sql").read_text())

    # Labor indicators (monthly, deterministic) at state and Canadian-county scope,
    # spanning the history window plus the 12-month forecast horizon.
    cur.execute(
        """
        INSERT INTO economic_indicators
            (geography_type, geography_key, indicator_family, indicator_name,
             period_date, value, source_name, source_vintage)
        SELECT g.gt, g.gk, 'labor', 'unemployment_rate', d::date,
               3.0 + ((extract(year FROM d) * 12 + extract(month FROM d))::int % 7) / 10.0,
               'CI synthetic fixture', current_date
        FROM (VALUES ('state','OK'), ('county','Canadian County'), ('county','Oklahoma County')) AS g(gt, gk)
        CROSS JOIN generate_series(
            date_trunc('month', current_date) - interval '72 months',
            date_trunc('month', current_date) + interval '14 months',
            interval '1 month') AS d
        """
    )
    cur.execute("SELECT count(*) FROM jurisdictions")
    print(f"CI fixture loaded ({cur.fetchone()[0]} jurisdictions) as of {date.today()}")


if __name__ == "__main__":
    main()
