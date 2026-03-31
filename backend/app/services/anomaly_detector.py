"""Anomaly detection service for MuniRev ledger data.

Scans ledger_records to identify unusual revenue patterns across
Oklahoma jurisdictions.  Three detection methods are used:

1. **Year-over-year spike/drop** -- flags months where the YoY change
   exceeds configurable thresholds.
2. **Month-over-month outlier** -- flags months where the MoM change
   exceeds 3 standard deviations of the jurisdiction's historical MoM
   distribution.
3. **Revenue cliff (missing data)** -- flags months where a city that
   previously collected >$10,000 suddenly reports $0 or NULL.

All queries use psycopg2 with parameterized statements.  No ORM.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import psycopg2.extensions
import psycopg2.extras

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

# YoY thresholds (absolute percent change)
YOY_HIGH_THRESHOLD: float = 25.0
YOY_CRITICAL_THRESHOLD: float = 40.0

# MoM outlier: flag if |MoM change| > MOM_STD_DEV_MULTIPLIER * std_dev
MOM_STD_DEV_MULTIPLIER: float = 3.0

# Revenue cliff: prior-month minimum to qualify
REVENUE_CLIFF_MIN: float = 10_000.0


class AnomalyDetector:
    """Detects revenue anomalies in ledger data.

    Designed to be instantiated once and reused.  Each detection method
    accepts a psycopg2 connection so the caller controls the transaction
    boundary.
    """

    def detect_all(self, conn: psycopg2.extensions.connection) -> int:
        """Scan all cities and all tax types.  Returns total anomalies found.

        Iterates over every distinct (copo, tax_type) pair that has at
        least 12 months of data and runs the full detection suite.
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Find all (copo, tax_type) pairs with enough data to analyse.
        cur.execute("""
            SELECT copo, tax_type, COUNT(*) AS n
            FROM ledger_records
            GROUP BY copo, tax_type
            HAVING COUNT(*) >= 3
            ORDER BY copo, tax_type
        """)
        pairs = cur.fetchall()
        cur.close()

        total_anomalies = 0
        processed = 0

        for row in pairs:
            copo = row["copo"]
            tax_type = row["tax_type"]
            anomalies = self.detect_for_city(conn, copo, tax_type)
            total_anomalies += len(anomalies)
            processed += 1

            if processed % 100 == 0:
                logger.info(
                    "Processed %d/%d city/tax pairs (%d anomalies so far)",
                    processed,
                    len(pairs),
                    total_anomalies,
                )

        logger.info(
            "Detection complete: %d city/tax pairs scanned, %d anomalies found.",
            processed,
            total_anomalies,
        )
        return total_anomalies

    def detect_for_city(
        self,
        conn: psycopg2.extensions.connection,
        copo: str,
        tax_type: str,
    ) -> list[dict[str, Any]]:
        """Detect anomalies for a single city / tax_type combination.

        Returns a list of anomaly dicts ready for database insertion.
        Each dict contains: copo, tax_type, anomaly_date, anomaly_type,
        severity, expected_value, actual_value, deviation_pct, description.
        """
        time_series = self._fetch_time_series(conn, copo, tax_type)

        if len(time_series) < 2:
            return []

        anomalies: list[dict[str, Any]] = []
        anomalies.extend(self._detect_yoy(time_series, copo, tax_type))
        anomalies.extend(self._detect_mom_outlier(time_series, copo, tax_type))
        anomalies.extend(self._detect_revenue_cliff(time_series, copo, tax_type))

        return anomalies

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_time_series(
        conn: psycopg2.extensions.connection,
        copo: str,
        tax_type: str,
    ) -> list[dict[str, Any]]:
        """Fetch the ordered monthly time series for a city/tax_type.

        Returns a list of dicts with keys: voucher_date, returned.
        Sorted ascending by voucher_date.
        """
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT voucher_date, COALESCE(returned, 0) AS returned
            FROM ledger_records
            WHERE copo = %s AND tax_type = %s
            ORDER BY voucher_date ASC
            """,
            (copo, tax_type),
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(r) for r in rows]

    @staticmethod
    def _pct_change(old: float, new: float) -> float | None:
        """Compute percentage change from *old* to *new*.

        Returns None when *old* is zero (division undefined).
        """
        if old == 0:
            return None
        return ((new - old) / abs(old)) * 100.0

    # ------------------------------------------------------------------
    # Detection method 1: Year-over-year spike / drop
    # ------------------------------------------------------------------

    def _detect_yoy(
        self,
        series: list[dict[str, Any]],
        copo: str,
        tax_type: str,
    ) -> list[dict[str, Any]]:
        """Flag months where |YoY change| exceeds thresholds.

        For each month that has a corresponding month 12 periods earlier,
        compute the year-over-year change and flag if it exceeds 25%
        (high) or 40% (critical).
        """
        anomalies: list[dict[str, Any]] = []

        # Build a lookup by (year, month) for O(1) prior-year access.
        by_period: dict[tuple[int, int], dict[str, Any]] = {}
        for rec in series:
            vd = rec["voucher_date"]
            by_period[(vd.year, vd.month)] = rec

        for rec in series:
            vd = rec["voucher_date"]
            prior_key = (vd.year - 1, vd.month)
            prior = by_period.get(prior_key)

            if prior is None:
                continue

            prior_val = float(prior["returned"])
            current_val = float(rec["returned"])
            pct = self._pct_change(prior_val, current_val)

            if pct is None:
                continue

            abs_pct = abs(pct)

            if abs_pct < YOY_HIGH_THRESHOLD:
                continue

            if abs_pct >= YOY_CRITICAL_THRESHOLD:
                severity = "critical"
            else:
                severity = "high"

            direction = "spike" if pct > 0 else "drop"
            direction_past = "spiked" if pct > 0 else "dropped"
            anomaly_type = f"yoy_{direction}"

            anomalies.append({
                "copo": copo,
                "tax_type": tax_type,
                "anomaly_date": vd,
                "anomaly_type": anomaly_type,
                "severity": severity,
                "expected_value": round(prior_val, 2),
                "actual_value": round(current_val, 2),
                "deviation_pct": round(pct, 2),
                "description": (
                    f"{tax_type.capitalize()} tax revenue {direction_past} "
                    f"{abs_pct:.1f}% year-over-year on {vd.isoformat()}: "
                    f"${current_val:,.2f} vs prior-year ${prior_val:,.2f}."
                ),
            })

        return anomalies

    # ------------------------------------------------------------------
    # Detection method 2: Month-over-month statistical outlier
    # ------------------------------------------------------------------

    def _detect_mom_outlier(
        self,
        series: list[dict[str, Any]],
        copo: str,
        tax_type: str,
    ) -> list[dict[str, Any]]:
        """Flag months where |MoM change| exceeds 3 standard deviations.

        Computes the standard deviation of all consecutive MoM percentage
        changes for the jurisdiction, then flags any month where the
        current MoM change exceeds ``MOM_STD_DEV_MULTIPLIER * std_dev``.
        """
        if len(series) < 4:
            # Need enough data points to compute a meaningful std_dev.
            return []

        # Compute all MoM percentage changes.
        mom_changes: list[float] = []
        for i in range(1, len(series)):
            prev_val = float(series[i - 1]["returned"])
            curr_val = float(series[i]["returned"])
            pct = self._pct_change(prev_val, curr_val)
            if pct is not None:
                mom_changes.append(pct)

        if len(mom_changes) < 3:
            return []

        # Compute mean and standard deviation of MoM changes.
        mean = sum(mom_changes) / len(mom_changes)
        variance = sum((x - mean) ** 2 for x in mom_changes) / len(mom_changes)
        std_dev = math.sqrt(variance)

        if std_dev == 0:
            return []

        threshold = MOM_STD_DEV_MULTIPLIER * std_dev

        anomalies: list[dict[str, Any]] = []

        # Walk through again to flag outliers.
        change_idx = 0
        for i in range(1, len(series)):
            prev_val = float(series[i - 1]["returned"])
            curr_val = float(series[i]["returned"])
            pct = self._pct_change(prev_val, curr_val)

            if pct is None:
                continue

            abs_pct = abs(pct - mean)

            if abs_pct > threshold:
                vd = series[i]["voucher_date"]
                # Determine severity based on how many std_devs away.
                n_sigmas = abs_pct / std_dev
                if n_sigmas >= 5:
                    severity = "critical"
                elif n_sigmas >= 4:
                    severity = "high"
                else:
                    severity = "medium"

                anomalies.append({
                    "copo": copo,
                    "tax_type": tax_type,
                    "anomaly_date": vd,
                    "anomaly_type": "mom_outlier",
                    "severity": severity,
                    "expected_value": round(prev_val, 2),
                    "actual_value": round(curr_val, 2),
                    "deviation_pct": round(pct, 2),
                    "description": (
                        f"{tax_type.capitalize()} tax MoM change of "
                        f"{pct:+.1f}% on {vd.isoformat()} is "
                        f"{n_sigmas:.1f} standard deviations from the mean "
                        f"({mean:.1f}% +/- {std_dev:.1f}%)."
                    ),
                })

            change_idx += 1

        return anomalies

    # ------------------------------------------------------------------
    # Detection method 3: Revenue cliff (missing data)
    # ------------------------------------------------------------------

    def _detect_revenue_cliff(
        self,
        series: list[dict[str, Any]],
        copo: str,
        tax_type: str,
    ) -> list[dict[str, Any]]:
        """Flag months where revenue drops to $0 after exceeding $10,000.

        If a city had ``returned > $10,000`` in the prior month but
        reports $0 (or NULL, coerced to 0) this month, that is flagged
        as a ``critical`` missing_data anomaly.
        """
        anomalies: list[dict[str, Any]] = []

        for i in range(1, len(series)):
            prev_val = float(series[i - 1]["returned"])
            curr_val = float(series[i]["returned"])

            if prev_val >= REVENUE_CLIFF_MIN and curr_val == 0:
                vd = series[i]["voucher_date"]
                anomalies.append({
                    "copo": copo,
                    "tax_type": tax_type,
                    "anomaly_date": vd,
                    "anomaly_type": "missing_data",
                    "severity": "critical",
                    "expected_value": round(prev_val, 2),
                    "actual_value": 0.00,
                    "deviation_pct": -100.00,
                    "description": (
                        f"{tax_type.capitalize()} tax revenue dropped to $0 on "
                        f"{vd.isoformat()} after ${prev_val:,.2f} the prior month. "
                        f"Possible missing data or reporting gap."
                    ),
                })

        return anomalies
