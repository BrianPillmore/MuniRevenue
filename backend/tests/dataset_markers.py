"""Markers for tests that assert production-scale data.

CI loads a small deterministic synthetic fixture (tests/ci_data), not the
production database. A few tests assert volumes that only the real, externally
ingested data satisfies (hundreds of jurisdictions, 70k+ ledger rows, 1M+ NAICS
rows, BLS/Census indicator tables). Those are skipped unless
MUNIREV_TEST_DATASET=production; every other test runs for real in CI.
"""
import os
import unittest

requires_production_dataset = unittest.skipUnless(
    os.environ.get("MUNIREV_TEST_DATASET") == "production",
    "data dependency: asserts production-scale data; set MUNIREV_TEST_DATASET=production to run",
)
