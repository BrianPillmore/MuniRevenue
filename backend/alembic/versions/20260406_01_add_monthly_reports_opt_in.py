"""Add monthly_reports_opt_in to app_users.

Revision ID: 20260406_01
Revises: 20260331_01
Create Date: 2026-04-06
"""

from __future__ import annotations

from alembic import op


revision = "20260406_01"
down_revision = "20260331_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE app_users "
        "ADD COLUMN IF NOT EXISTS monthly_reports_opt_in BOOLEAN NOT NULL DEFAULT TRUE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE app_users DROP COLUMN IF EXISTS monthly_reports_opt_in"
    )
