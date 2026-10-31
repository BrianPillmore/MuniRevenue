-- CI-only schema compatibility layer.
-- app/db/schema.sql is the original baseline; the API code queries objects
-- that production gained later (outside this repo's migrations). Apply this
-- file after schema.sql in CI so the endpoints run against a faithful shape.
-- Never run against production.

-- naics_records.year / .month (aliases of calendar_year / calendar_month)
ALTER TABLE naics_records
    ADD COLUMN IF NOT EXISTS year  SMALLINT GENERATED ALWAYS AS (EXTRACT(YEAR  FROM report_date)::SMALLINT) STORED,
    ADD COLUMN IF NOT EXISTS month SMALLINT GENERATED ALWAYS AS (EXTRACT(MONTH FROM report_date)::SMALLINT) STORED;

-- naics_sectors: sector code -> name lookup used by /api/stats/naics-sectors
CREATE TABLE IF NOT EXISTS naics_sectors (
    sector      VARCHAR(2)   PRIMARY KEY,
    sector_name VARCHAR(255) NOT NULL
);

-- anomaly_type values emitted by the anomaly detector
ALTER TYPE anomaly_type ADD VALUE IF NOT EXISTS 'yoy_spike';
ALTER TYPE anomaly_type ADD VALUE IF NOT EXISTS 'yoy_drop';
ALTER TYPE anomaly_type ADD VALUE IF NOT EXISTS 'mom_outlier';
ALTER TYPE anomaly_type ADD VALUE IF NOT EXISTS 'naics_shift';

-- denormalised activity description carried on naics_records in production
ALTER TABLE naics_records ADD COLUMN IF NOT EXISTS activity_code_description VARCHAR(255);

-- anomalies: production exposes an integer id and created_at (alias of detected_at)
ALTER TABLE anomalies
    ADD COLUMN IF NOT EXISTS id         BIGINT      GENERATED ALWAYS AS IDENTITY,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ GENERATED ALWAYS AS (detected_at) STORED;
