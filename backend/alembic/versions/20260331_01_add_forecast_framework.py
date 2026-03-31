"""Add forecast framework persistence tables.

Revision ID: 20260331_01
Revises:
Create Date: 2026-03-31
"""

from __future__ import annotations

from alembic import op


revision = "20260331_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    statements = [
        """
        CREATE TABLE IF NOT EXISTS forecast_runs (
            id BIGSERIAL PRIMARY KEY,
            copo VARCHAR(10) NOT NULL,
            tax_type VARCHAR(20) NOT NULL,
            activity_code VARCHAR(10),
            series_scope VARCHAR(20) NOT NULL,
            requested_model VARCHAR(20) NOT NULL,
            selected_model VARCHAR(20) NOT NULL,
            horizon_months INTEGER NOT NULL,
            lookback_months INTEGER,
            confidence_level NUMERIC(6,4) NOT NULL,
            indicator_profile VARCHAR(30) NOT NULL,
            training_start DATE,
            training_end DATE,
            feature_set JSONB,
            model_parameters JSONB,
            explanation JSONB,
            data_quality JSONB,
            selected BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_predictions (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            model_type VARCHAR(20) NOT NULL,
            target_date DATE NOT NULL,
            projected_value NUMERIC(15,2) NOT NULL,
            lower_bound NUMERIC(15,2) NOT NULL,
            upper_bound NUMERIC(15,2) NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS forecast_backtests (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL REFERENCES forecast_runs(id) ON DELETE CASCADE,
            model_type VARCHAR(20) NOT NULL,
            mape NUMERIC(10,4),
            smape NUMERIC(10,4),
            mae NUMERIC(15,4),
            rmse NUMERIC(15,4),
            coverage NUMERIC(10,4),
            fold_count INTEGER NOT NULL DEFAULT 0,
            holdout_description TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS economic_indicators (
            id BIGSERIAL PRIMARY KEY,
            geography_type VARCHAR(20) NOT NULL,
            geography_key VARCHAR(80) NOT NULL,
            indicator_family VARCHAR(30) NOT NULL,
            indicator_name VARCHAR(80) NOT NULL,
            period_date DATE NOT NULL,
            value NUMERIC(15,4) NOT NULL,
            source_name VARCHAR(120),
            source_vintage DATE,
            is_forecast BOOLEAN NOT NULL DEFAULT FALSE,
            metadata JSONB
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_forecast_runs_lookup ON forecast_runs (copo, tax_type, selected_model, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_forecast_runs_scope ON forecast_runs (activity_code, series_scope, created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_forecast_predictions_run_model ON forecast_predictions (run_id, model_type, target_date)",
        "CREATE INDEX IF NOT EXISTS idx_forecast_backtests_run_model ON forecast_backtests (run_id, model_type)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_economic_indicators_unique ON economic_indicators (geography_type, geography_key, indicator_family, indicator_name, period_date)",
        "CREATE INDEX IF NOT EXISTS ix_economic_indicator_lookup ON economic_indicators (indicator_family, geography_type, geography_key, period_date)",
    ]

    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    statements = [
        "DROP INDEX IF EXISTS ix_economic_indicator_lookup",
        "DROP INDEX IF EXISTS idx_economic_indicators_unique",
        "DROP TABLE IF EXISTS economic_indicators",
        "DROP INDEX IF EXISTS idx_forecast_backtests_run_model",
        "DROP TABLE IF EXISTS forecast_backtests",
        "DROP INDEX IF EXISTS idx_forecast_predictions_run_model",
        "DROP TABLE IF EXISTS forecast_predictions",
        "DROP INDEX IF EXISTS idx_forecast_runs_scope",
        "DROP INDEX IF EXISTS idx_forecast_runs_lookup",
        "DROP TABLE IF EXISTS forecast_runs",
    ]

    for statement in statements:
        op.execute(statement)
