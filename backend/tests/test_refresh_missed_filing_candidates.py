from __future__ import annotations

import sys
import time
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from psycopg2 import sql

from app.api.cities import get_conn

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.refresh_missed_filing_candidates import (  # noqa: E402
    NaicsRow,
    build_candidate_rows,
    create_build_table,
    create_refresh_meta_table,
    create_stage_indexes,
    insert_candidates,
    lookup_index_name_for,
    publish_stage_table,
)


def make_candidate_payload(
    *,
    anomaly_date: date,
    activity_code: str,
    activity_description: str,
    actual_value: float,
    prior_year_value: float | None = 1000.0,
) -> dict[str, object]:
    return {
        "city_name": "Testville",
        "anomaly_date": anomaly_date,
        "activity_code": activity_code,
        "activity_description": activity_description,
        "city_total": 9000.0,
        "city_prior_year_total": 10000.0,
        "city_trailing_mean_3": 9200.0,
        "city_trailing_count_3": 3,
        "city_trailing_mean_6": 9100.0,
        "city_trailing_count_6": 6,
        "city_trailing_mean_12": 9050.0,
        "city_trailing_count_12": 12,
        "city_trailing_median_12": 9000.0,
        "city_exp_weighted_avg_12": 9100.0,
        "prior_year_value": prior_year_value,
        "trailing_mean_3": 550.0,
        "trailing_count_3": 3,
        "trailing_mean_6": 500.0,
        "trailing_count_6": 6,
        "trailing_mean_12": 480.0,
        "trailing_count_12": 12,
        "trailing_median_12": 500.0,
        "exp_weighted_avg_12": 490.0,
        "hybrid_expected_value": 800.0,
        "hybrid_city_expected_total": 9600.0,
        "hybrid_missing_amount": 800.0 - actual_value,
        "hybrid_missing_pct": round(((800.0 - actual_value) / 800.0) * 100, 2),
        "hybrid_baseline_share_pct": 8.33,
        "hybrid_baseline_months_used": 13,
        "actual_value": actual_value,
    }


class TestBuildCandidateRows(unittest.TestCase):
    def test_build_candidate_rows_is_exhaustive_for_actionable_codes(self) -> None:
        ledger_months = {
            date(2025, month, 1): ("Testville", 10000.0)
            for month in range(1, 13)
        }
        ledger_months[date(2026, 1, 1)] = ("Testville", 9000.0)

        naics_rows = [
            NaicsRow(date(2025, 1, 1), "111111", "Large Retail", 6000.0),
            NaicsRow(date(2026, 1, 1), "111111", "Large Retail", 1000.0),
            NaicsRow(date(2025, 1, 1), "222222", "Small But Actionable", 400.0),
        ]

        rows = build_candidate_rows(
            ledger_months,
            naics_rows,
            target_start=date(2026, 1, 1),
            target_end=date(2026, 1, 1),
        )

        by_code = {row["activity_code"]: row for row in rows}
        self.assertIn("111111", by_code)
        self.assertIn("222222", by_code)
        self.assertEqual(by_code["222222"]["actual_value"], 0.0)
        self.assertEqual(by_code["222222"]["prior_year_value"], 400.0)

    def test_build_candidate_rows_skips_codes_without_usable_baseline(self) -> None:
        ledger_months = {
            date(2025, month, 1): ("Testville", 10000.0)
            for month in range(1, 13)
        }
        ledger_months[date(2026, 1, 1)] = ("Testville", 9000.0)

        naics_rows = [
            NaicsRow(date(2025, 12, 1), "333333", "Too Little History", 500.0),
        ]

        rows = build_candidate_rows(
            ledger_months,
            naics_rows,
            target_start=date(2026, 1, 1),
            target_end=date(2026, 1, 1),
        )

        self.assertEqual(rows, [])


class TestPublishStageTable(unittest.TestCase):
    def test_publish_stage_table_swaps_stage_snapshot(self) -> None:
        suffix = uuid4().hex[:8]
        live_table = f"missed_filing_candidates_t_{suffix}"
        stage_table = f"{live_table}_stage"
        meta_table = f"{live_table}_meta"
        lookup_index_name = lookup_index_name_for(live_table)
        snapshot_created_at = datetime(2026, 4, 1, 15, 0, tzinfo=timezone.utc)

        conn = get_conn()
        try:
            create_build_table(conn, live_table)
            create_build_table(conn, stage_table)
            create_refresh_meta_table(conn, meta_table)

            insert_candidates(
                conn,
                live_table,
                "LIVE001",
                "sales",
                [
                    make_candidate_payload(
                        anomaly_date=date(2026, 1, 1),
                        activity_code="111111",
                        activity_description="Live Row",
                        actual_value=50.0,
                    )
                ],
                snapshot_created_at,
            )
            insert_candidates(
                conn,
                stage_table,
                "NEXT001",
                "sales",
                [
                    make_candidate_payload(
                        anomaly_date=date(2026, 2, 1),
                        activity_code="222222",
                        activity_description="Stage Row",
                        actual_value=0.0,
                    )
                ],
                snapshot_created_at,
            )
            create_stage_indexes(conn, stage_table)

            publish_stage_table(
                conn,
                stage_table,
                snapshot_created_at=snapshot_created_at,
                duration_seconds=12.34,
                live_table=live_table,
                meta_table=meta_table,
                lookup_index_name=lookup_index_name,
            )

            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT copo, activity_code FROM {}").format(
                        sql.Identifier(live_table)
                    )
                )
                rows = cur.fetchall()
                self.assertEqual(rows, [("NEXT001", "222222")])

                cur.execute(
                    sql.SQL(
                        "SELECT snapshot_row_count, data_min_month, data_max_month FROM {} WHERE singleton = TRUE"
                    ).format(sql.Identifier(meta_table))
                )
                snapshot_row_count, data_min_month, data_max_month = cur.fetchone()
                self.assertEqual(snapshot_row_count, 1)
                self.assertEqual(data_min_month, date(2026, 2, 1))
                self.assertEqual(data_max_month, date(2026, 2, 1))

                cur.execute("SELECT to_regclass(%s)", (stage_table,))
                self.assertIsNone(cur.fetchone()[0])

                cur.execute("SELECT to_regclass(%s)", (lookup_index_name,))
                self.assertEqual(cur.fetchone()[0], lookup_index_name)
        finally:
            with conn.cursor() as cur:
                for table_name in (stage_table, live_table, meta_table):
                    cur.execute(
                        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                            sql.Identifier(table_name)
                        )
                    )
            conn.commit()
            conn.close()
