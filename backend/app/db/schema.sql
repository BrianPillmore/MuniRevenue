-- =============================================================================
-- MuniRev  --  Oklahoma Municipal Revenue Intelligence Platform
-- PostgreSQL Schema  (requires PostgreSQL 15+)
--
-- Designed for OkTAP Ledger and NAICS report ingestion, time-series analytics,
-- anomaly detection, and revenue forecasting across ~600 municipalities,
-- 77 counties, ~470 NAICS codes, and 5+ years of monthly data.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;       -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- trigram similarity for name search


-- ===========================  ENUM TYPES  ==================================

CREATE TYPE tax_type AS ENUM ('sales', 'use', 'lodging');

COMMENT ON TYPE tax_type IS
    'The three OkTAP tax categories: sales, use, and lodging.';

CREATE TYPE jurisdiction_type AS ENUM ('city', 'county');

COMMENT ON TYPE jurisdiction_type IS
    'Whether a jurisdiction is an incorporated city/town or a county.';

CREATE TYPE anomaly_severity AS ENUM ('low', 'medium', 'high', 'critical');

COMMENT ON TYPE anomaly_severity IS
    'Graduated severity rating for detected revenue anomalies.';

CREATE TYPE anomaly_type AS ENUM (
    'spike',              -- revenue unexpectedly high
    'drop',               -- revenue unexpectedly low
    'missing_data',       -- expected record absent
    'trend_break',        -- change in long-running trend direction
    'seasonal_deviation', -- deviates from established seasonal pattern
    'rate_change',        -- tax rate changed between periods
    'outlier'             -- generic statistical outlier
);

COMMENT ON TYPE anomaly_type IS
    'Classification of the kind of anomaly detected in revenue data.';

CREATE TYPE anomaly_status AS ENUM (
    'new',            -- just detected, not yet reviewed
    'investigating',  -- analyst is looking into it
    'confirmed',      -- verified as a real anomaly
    'dismissed',      -- false positive
    'resolved'        -- root cause identified and documented
);

COMMENT ON TYPE anomaly_status IS
    'Investigation lifecycle status for a detected anomaly.';

CREATE TYPE forecast_model_type AS ENUM (
    'seasonal_naive',    -- prior-year same-month carry-forward
    'linear_trend',      -- OLS linear regression on time
    'holt_winters',      -- triple exponential smoothing
    'arima',             -- ARIMA / SARIMAX
    'prophet',           -- Facebook Prophet
    'ensemble'           -- weighted blend of multiple models
);

COMMENT ON TYPE forecast_model_type IS
    'Statistical / ML model used to produce a revenue forecast.';

CREATE TYPE import_status AS ENUM (
    'pending',      -- queued, not yet processed
    'processing',   -- currently being ingested
    'completed',    -- finished successfully
    'failed',       -- finished with errors
    'partial'       -- some rows succeeded, some failed
);

COMMENT ON TYPE import_status IS
    'Processing lifecycle status for a data import batch.';


-- ===========================  REFERENCE TABLES  ============================

-- ---------------------------------------------------------------------------
-- jurisdictions  --  Oklahoma cities and counties
-- ---------------------------------------------------------------------------
CREATE TABLE jurisdictions (
    copo                VARCHAR(4)          NOT NULL,
    name                VARCHAR(100)        NOT NULL,
    jurisdiction_type   jurisdiction_type   NOT NULL,
    county_name         VARCHAR(50),
    population          INTEGER,
    latitude            NUMERIC(9,6),
    longitude           NUMERIC(9,6),
    tax_rate_sales      NUMERIC(6,4),
    tax_rate_use        NUMERIC(6,4),
    tax_rate_lodging    NUMERIC(6,4),
    active              BOOLEAN             NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ         NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ         NOT NULL DEFAULT now(),

    CONSTRAINT pk_jurisdictions          PRIMARY KEY (copo),
    CONSTRAINT ck_copo_format            CHECK (copo ~ '^\d{4}$'),
    CONSTRAINT ck_population_positive    CHECK (population IS NULL OR population >= 0),
    CONSTRAINT ck_latitude_range         CHECK (latitude  IS NULL OR latitude  BETWEEN  33.5 AND  37.5),
    CONSTRAINT ck_longitude_range        CHECK (longitude IS NULL OR longitude BETWEEN -103.5 AND -94.0)
);

COMMENT ON TABLE  jurisdictions IS
    'Oklahoma municipalities and counties that collect tax revenue through OkTAP.';
COMMENT ON COLUMN jurisdictions.copo IS
    'Four-digit OkTAP jurisdiction code (e.g., "0955" = Yukon). Primary identifier on all reports.';
COMMENT ON COLUMN jurisdictions.name IS
    'Official jurisdiction name as shown in OkTAP reports.';
COMMENT ON COLUMN jurisdictions.jurisdiction_type IS
    'Whether this is a city/town or a county.';
COMMENT ON COLUMN jurisdictions.county_name IS
    'Oklahoma county this jurisdiction belongs to (NULL for county-type rows).';
COMMENT ON COLUMN jurisdictions.population IS
    'Most recent population estimate, used for per-capita calculations.';
COMMENT ON COLUMN jurisdictions.latitude IS
    'Geographic centroid latitude (WGS 84). Oklahoma range: ~33.6 to ~37.0.';
COMMENT ON COLUMN jurisdictions.longitude IS
    'Geographic centroid longitude (WGS 84). Oklahoma range: ~-103.0 to ~-94.4.';
COMMENT ON COLUMN jurisdictions.tax_rate_sales IS
    'Current local sales tax rate (e.g. 0.0400 = 4%). Tracked for rate-change anomaly detection.';
COMMENT ON COLUMN jurisdictions.active IS
    'FALSE if the jurisdiction has been dissolved or no longer remits through OkTAP.';

CREATE INDEX idx_jurisdictions_name_trgm ON jurisdictions
    USING gin (name gin_trgm_ops);

CREATE INDEX idx_jurisdictions_type ON jurisdictions (jurisdiction_type);

CREATE INDEX idx_jurisdictions_county ON jurisdictions (county_name)
    WHERE county_name IS NOT NULL;


-- ---------------------------------------------------------------------------
-- naics_codes  --  North American Industry Classification reference
-- ---------------------------------------------------------------------------
CREATE TABLE naics_codes (
    activity_code       VARCHAR(6)      NOT NULL,
    sector              VARCHAR(2)      NOT NULL
        GENERATED ALWAYS AS (LEFT(activity_code, 2)) STORED,
    description         VARCHAR(255)    NOT NULL,
    sector_description  VARCHAR(255),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT pk_naics_codes           PRIMARY KEY (activity_code),
    CONSTRAINT ck_activity_code_format  CHECK (activity_code ~ '^\d{2,6}$'),
    CONSTRAINT ck_sector_format         CHECK (sector ~ '^\d{2}$')
);

COMMENT ON TABLE  naics_codes IS
    'Reference table of NAICS industry codes used in OkTAP NAICS reports.';
COMMENT ON COLUMN naics_codes.activity_code IS
    'Six-digit NAICS activity code (e.g., "221111"). Primary key.';
COMMENT ON COLUMN naics_codes.sector IS
    'Two-digit NAICS sector derived from the first two digits of activity_code. GENERATED column.';
COMMENT ON COLUMN naics_codes.description IS
    'Human-readable activity description (e.g., "Hydroelectric Power Generation").';
COMMENT ON COLUMN naics_codes.sector_description IS
    'Human-readable sector name (e.g., "Utilities" for sector 22).';

CREATE INDEX idx_naics_sector ON naics_codes (sector);


-- ---------------------------------------------------------------------------
-- data_imports  --  tracks every ingestion batch for auditability
-- ---------------------------------------------------------------------------
CREATE TABLE data_imports (
    import_id       UUID            NOT NULL DEFAULT gen_random_uuid(),
    source_type     VARCHAR(20)     NOT NULL,
    file_name       VARCHAR(255),
    file_hash       VARCHAR(64),
    status          import_status   NOT NULL DEFAULT 'pending',
    records_total   INTEGER         NOT NULL DEFAULT 0,
    records_success INTEGER         NOT NULL DEFAULT 0,
    records_failed  INTEGER         NOT NULL DEFAULT 0,
    error_detail    JSONB,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),

    CONSTRAINT pk_data_imports           PRIMARY KEY (import_id),
    CONSTRAINT ck_source_type            CHECK (source_type IN ('ledger', 'naics', 'jurisdiction', 'manual')),
    CONSTRAINT ck_records_non_negative   CHECK (records_total >= 0 AND records_success >= 0 AND records_failed >= 0),
    CONSTRAINT ck_records_sum            CHECK (records_success + records_failed <= records_total)
);

COMMENT ON TABLE  data_imports IS
    'Audit log for every data ingestion batch. Tracks source file, row counts, and errors.';
COMMENT ON COLUMN data_imports.source_type IS
    'Which OkTAP report type this import contains: ledger, naics, jurisdiction, or manual.';
COMMENT ON COLUMN data_imports.file_hash IS
    'SHA-256 hash of the source file to detect duplicate uploads.';
COMMENT ON COLUMN data_imports.status IS
    'Processing lifecycle: pending -> processing -> completed/failed/partial.';
COMMENT ON COLUMN data_imports.error_detail IS
    'JSONB array of per-row error messages when status is failed or partial.';

CREATE INDEX idx_imports_status     ON data_imports (status) WHERE status != 'completed';
CREATE INDEX idx_imports_source     ON data_imports (source_type, created_at DESC);
CREATE INDEX idx_imports_file_hash  ON data_imports (file_hash) WHERE file_hash IS NOT NULL;


-- ===========================  CORE DATA TABLES  ============================

-- ---------------------------------------------------------------------------
-- ledger_records  --  Monthly revenue from OkTAP Ledger Report
--
-- Partitioned by year on voucher_date for efficient time-range queries
-- and simpler data lifecycle management (DROP old partition vs DELETE).
-- ---------------------------------------------------------------------------
CREATE TABLE ledger_records (
    ledger_id                   BIGINT          GENERATED ALWAYS AS IDENTITY,
    copo                        VARCHAR(4)      NOT NULL,
    tax_type                    tax_type        NOT NULL,
    voucher_date                DATE            NOT NULL,
    tax_rate                    NUMERIC(6,4)    NOT NULL,
    current_month_collection    NUMERIC(14,2)   NOT NULL DEFAULT 0,
    refunded                    NUMERIC(14,2)   NOT NULL DEFAULT 0,
    suspended_monies            NUMERIC(14,2)   NOT NULL DEFAULT 0,
    apportioned                 NUMERIC(14,2)   NOT NULL DEFAULT 0,
    revolving_fund              NUMERIC(14,2)   NOT NULL DEFAULT 0,
    interest_returned           NUMERIC(14,2)   NOT NULL DEFAULT 0,
    returned                    NUMERIC(14,2)   NOT NULL DEFAULT 0,
    import_id                   UUID,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Fiscal helpers: derived columns for analytics convenience
    fiscal_year                 SMALLINT        NOT NULL
        GENERATED ALWAYS AS (
            CASE WHEN EXTRACT(MONTH FROM voucher_date) >= 7
                 THEN EXTRACT(YEAR FROM voucher_date)::SMALLINT + 1
                 ELSE EXTRACT(YEAR FROM voucher_date)::SMALLINT
            END
        ) STORED,
    calendar_year               SMALLINT        NOT NULL
        GENERATED ALWAYS AS (EXTRACT(YEAR FROM voucher_date)::SMALLINT) STORED,
    calendar_month              SMALLINT        NOT NULL
        GENERATED ALWAYS AS (EXTRACT(MONTH FROM voucher_date)::SMALLINT) STORED,

    CONSTRAINT pk_ledger_records        PRIMARY KEY (ledger_id, voucher_date),
    CONSTRAINT fk_ledger_jurisdiction   FOREIGN KEY (copo)      REFERENCES jurisdictions (copo),
    CONSTRAINT fk_ledger_import         FOREIGN KEY (import_id) REFERENCES data_imports (import_id),
    CONSTRAINT ck_tax_rate_positive     CHECK (tax_rate > 0),
    CONSTRAINT uq_ledger_natural_key    UNIQUE (copo, tax_type, voucher_date)
) PARTITION BY RANGE (voucher_date);

COMMENT ON TABLE  ledger_records IS
    'Monthly revenue data from OkTAP Ledger Reports. One row per city per tax type per month. '
    'Partitioned by year on voucher_date.';
COMMENT ON COLUMN ledger_records.copo IS
    'FK to jurisdictions. Four-digit OkTAP jurisdiction code.';
COMMENT ON COLUMN ledger_records.voucher_date IS
    'Date of the monthly voucher (one per month). Partition key.';
COMMENT ON COLUMN ledger_records.returned IS
    'Net amount returned to the jurisdiction -- the primary revenue figure.';
COMMENT ON COLUMN ledger_records.current_month_collection IS
    'Gross tax collected before adjustments.';
COMMENT ON COLUMN ledger_records.fiscal_year IS
    'Oklahoma fiscal year (July-June). GENERATED: July 2025 -> FY 2026.';
COMMENT ON COLUMN ledger_records.calendar_year IS
    'Calendar year extracted from voucher_date. GENERATED column.';
COMMENT ON COLUMN ledger_records.calendar_month IS
    'Calendar month (1-12) extracted from voucher_date. GENERATED column.';
COMMENT ON COLUMN ledger_records.import_id IS
    'FK to data_imports -- which batch loaded this record.';

-- Create partitions for historical + future years
CREATE TABLE ledger_records_2019 PARTITION OF ledger_records
    FOR VALUES FROM ('2019-01-01') TO ('2020-01-01');
CREATE TABLE ledger_records_2020 PARTITION OF ledger_records
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE ledger_records_2021 PARTITION OF ledger_records
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE ledger_records_2022 PARTITION OF ledger_records
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE ledger_records_2023 PARTITION OF ledger_records
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE ledger_records_2024 PARTITION OF ledger_records
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE ledger_records_2025 PARTITION OF ledger_records
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE ledger_records_2026 PARTITION OF ledger_records
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE ledger_records_2027 PARTITION OF ledger_records
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE ledger_records_default PARTITION OF ledger_records DEFAULT;

-- Primary query pattern: copo + tax_type + date range (partition key is voucher_date)
CREATE INDEX idx_ledger_copo_type_date ON ledger_records (copo, tax_type, voucher_date DESC);

-- Time-series scans across all cities for a date range
CREATE INDEX idx_ledger_date_type ON ledger_records (voucher_date DESC, tax_type);

-- Fiscal-year rollups
CREATE INDEX idx_ledger_fiscal_year ON ledger_records (fiscal_year, copo, tax_type);

-- Fast lookups by import batch (for reprocessing / rollback)
CREATE INDEX idx_ledger_import ON ledger_records (import_id) WHERE import_id IS NOT NULL;


-- ---------------------------------------------------------------------------
-- naics_records  --  Monthly revenue by industry from OkTAP NAICS Report
--
-- Partitioned by year on report_date for the same benefits as ledger_records.
-- ---------------------------------------------------------------------------
CREATE TABLE naics_records (
    naics_record_id     BIGINT          GENERATED ALWAYS AS IDENTITY,
    copo                VARCHAR(4)      NOT NULL,
    tax_type            tax_type        NOT NULL,
    report_date         DATE            NOT NULL,
    activity_code       VARCHAR(6)      NOT NULL,
    tax_rate            NUMERIC(6,4)    NOT NULL,
    sector_total        NUMERIC(14,2)   NOT NULL DEFAULT 0,
    year_to_date        NUMERIC(14,2)   NOT NULL DEFAULT 0,
    import_id           UUID,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT now(),

    -- Derived columns
    sector              VARCHAR(2)      NOT NULL
        GENERATED ALWAYS AS (LEFT(activity_code, 2)) STORED,
    calendar_year       SMALLINT        NOT NULL
        GENERATED ALWAYS AS (EXTRACT(YEAR FROM report_date)::SMALLINT) STORED,
    calendar_month      SMALLINT        NOT NULL
        GENERATED ALWAYS AS (EXTRACT(MONTH FROM report_date)::SMALLINT) STORED,

    CONSTRAINT pk_naics_records         PRIMARY KEY (naics_record_id, report_date),
    CONSTRAINT fk_naics_jurisdiction    FOREIGN KEY (copo)          REFERENCES jurisdictions (copo),
    CONSTRAINT fk_naics_activity_code   FOREIGN KEY (activity_code) REFERENCES naics_codes (activity_code),
    CONSTRAINT fk_naics_import          FOREIGN KEY (import_id)     REFERENCES data_imports (import_id),
    CONSTRAINT ck_naics_tax_type        CHECK (tax_type IN ('sales', 'use')),
    CONSTRAINT ck_naics_tax_rate        CHECK (tax_rate > 0),
    CONSTRAINT uq_naics_natural_key     UNIQUE (copo, tax_type, report_date, activity_code)
) PARTITION BY RANGE (report_date);

COMMENT ON TABLE  naics_records IS
    'Monthly revenue by NAICS industry from OkTAP NAICS Reports. Sales and use tax only. '
    'One row per city per tax type per NAICS code per month. Partitioned by year.';
COMMENT ON COLUMN naics_records.report_date IS
    'First day of the report month (e.g. 2025-07-01 for the July 2025 report). Partition key.';
COMMENT ON COLUMN naics_records.activity_code IS
    'Six-digit NAICS code (FK to naics_codes). Identifies the business activity.';
COMMENT ON COLUMN naics_records.sector IS
    'Two-digit NAICS sector. GENERATED from activity_code for fast sector-level queries.';
COMMENT ON COLUMN naics_records.sector_total IS
    'Current month revenue amount for this NAICS code.';
COMMENT ON COLUMN naics_records.year_to_date IS
    'Calendar YTD cumulative revenue for this NAICS code.';

-- Partitions
CREATE TABLE naics_records_2019 PARTITION OF naics_records
    FOR VALUES FROM ('2019-01-01') TO ('2020-01-01');
CREATE TABLE naics_records_2020 PARTITION OF naics_records
    FOR VALUES FROM ('2020-01-01') TO ('2021-01-01');
CREATE TABLE naics_records_2021 PARTITION OF naics_records
    FOR VALUES FROM ('2021-01-01') TO ('2022-01-01');
CREATE TABLE naics_records_2022 PARTITION OF naics_records
    FOR VALUES FROM ('2022-01-01') TO ('2023-01-01');
CREATE TABLE naics_records_2023 PARTITION OF naics_records
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
CREATE TABLE naics_records_2024 PARTITION OF naics_records
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
CREATE TABLE naics_records_2025 PARTITION OF naics_records
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');
CREATE TABLE naics_records_2026 PARTITION OF naics_records
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');
CREATE TABLE naics_records_2027 PARTITION OF naics_records
    FOR VALUES FROM ('2027-01-01') TO ('2028-01-01');
CREATE TABLE naics_records_default PARTITION OF naics_records DEFAULT;

-- Primary: city + tax type + date range
CREATE INDEX idx_naics_copo_type_date ON naics_records (copo, tax_type, report_date DESC);

-- Cross-city lookup for a specific NAICS code
CREATE INDEX idx_naics_activity_date ON naics_records (activity_code, report_date DESC);

-- Sector-level aggregations
CREATE INDEX idx_naics_sector_date ON naics_records (sector, report_date DESC);

-- Import batch tracking
CREATE INDEX idx_naics_import ON naics_records (import_id) WHERE import_id IS NOT NULL;


-- ===========================  ANALYTICS TABLES  ============================

-- ---------------------------------------------------------------------------
-- anomalies  --  Detected revenue anomalies
-- ---------------------------------------------------------------------------
CREATE TABLE anomalies (
    anomaly_id      UUID                NOT NULL DEFAULT gen_random_uuid(),
    copo            VARCHAR(4)          NOT NULL,
    tax_type        tax_type            NOT NULL,
    anomaly_date    DATE                NOT NULL,
    activity_code   VARCHAR(6),
    anomaly_type    anomaly_type        NOT NULL,
    severity        anomaly_severity    NOT NULL,
    expected_value  NUMERIC(14,2),
    actual_value    NUMERIC(14,2),
    deviation_pct   NUMERIC(8,4)
        GENERATED ALWAYS AS (
            CASE WHEN expected_value IS NOT NULL AND expected_value != 0
                 THEN ((actual_value - expected_value) / ABS(expected_value)) * 100
                 ELSE NULL
            END
        ) STORED,
    description     TEXT,
    status          anomaly_status      NOT NULL DEFAULT 'new',
    investigated_by VARCHAR(100),
    resolution_note TEXT,
    detected_at     TIMESTAMPTZ         NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ         NOT NULL DEFAULT now(),

    CONSTRAINT pk_anomalies             PRIMARY KEY (anomaly_id),
    CONSTRAINT fk_anomaly_jurisdiction  FOREIGN KEY (copo)          REFERENCES jurisdictions (copo),
    CONSTRAINT fk_anomaly_naics         FOREIGN KEY (activity_code) REFERENCES naics_codes (activity_code),
    CONSTRAINT ck_anomaly_values        CHECK (
        (anomaly_type = 'missing_data')
        OR (expected_value IS NOT NULL AND actual_value IS NOT NULL)
    )
);

COMMENT ON TABLE  anomalies IS
    'Revenue anomalies detected by automated analysis. Tracks expected vs actual values, '
    'severity classification, and investigation lifecycle.';
COMMENT ON COLUMN anomalies.anomaly_date IS
    'The voucher/report month where the anomaly was detected.';
COMMENT ON COLUMN anomalies.activity_code IS
    'If the anomaly is at the NAICS level, the specific industry code. NULL for ledger-level anomalies.';
COMMENT ON COLUMN anomalies.expected_value IS
    'Model-predicted or historical-baseline expected revenue amount.';
COMMENT ON COLUMN anomalies.actual_value IS
    'Observed revenue amount from the OkTAP data.';
COMMENT ON COLUMN anomalies.deviation_pct IS
    'Percentage deviation from expected. GENERATED: ((actual - expected) / |expected|) * 100.';
COMMENT ON COLUMN anomalies.status IS
    'Investigation lifecycle: new -> investigating -> confirmed/dismissed/resolved.';
COMMENT ON COLUMN anomalies.resolution_note IS
    'Free-text explanation after investigation (e.g., "Large retailer opened Q3 2025").';

-- Open anomalies dashboard (filter out resolved/dismissed)
CREATE INDEX idx_anomalies_open ON anomalies (severity DESC, detected_at DESC)
    WHERE status NOT IN ('dismissed', 'resolved');

-- Anomalies for a specific jurisdiction
CREATE INDEX idx_anomalies_copo_date ON anomalies (copo, anomaly_date DESC);

-- Anomalies by type for pattern analysis
CREATE INDEX idx_anomalies_type_severity ON anomalies (anomaly_type, severity);

-- NAICS-specific anomaly lookups
CREATE INDEX idx_anomalies_naics ON anomalies (activity_code, anomaly_date DESC)
    WHERE activity_code IS NOT NULL;


-- ---------------------------------------------------------------------------
-- forecasts  --  Projected future revenue values
-- ---------------------------------------------------------------------------
CREATE TABLE forecasts (
    forecast_id         UUID                NOT NULL DEFAULT gen_random_uuid(),
    copo                VARCHAR(4)          NOT NULL,
    tax_type            tax_type            NOT NULL,
    activity_code       VARCHAR(6),
    target_date         DATE                NOT NULL,
    model_type          forecast_model_type NOT NULL,
    projected_value     NUMERIC(14,2)       NOT NULL,
    lower_bound         NUMERIC(14,2)       NOT NULL,
    upper_bound         NUMERIC(14,2)       NOT NULL,
    confidence_level    NUMERIC(5,4)        NOT NULL DEFAULT 0.9500,
    model_metadata      JSONB,
    basis_period_start  DATE,
    basis_period_end    DATE,
    created_at          TIMESTAMPTZ         NOT NULL DEFAULT now(),

    CONSTRAINT pk_forecasts             PRIMARY KEY (forecast_id),
    CONSTRAINT fk_forecast_jurisdiction FOREIGN KEY (copo)          REFERENCES jurisdictions (copo),
    CONSTRAINT fk_forecast_naics        FOREIGN KEY (activity_code) REFERENCES naics_codes (activity_code),
    CONSTRAINT ck_confidence_interval   CHECK (lower_bound <= projected_value AND projected_value <= upper_bound),
    CONSTRAINT ck_confidence_level      CHECK (confidence_level BETWEEN 0.5000 AND 0.9999),
    CONSTRAINT ck_basis_period          CHECK (
        (basis_period_start IS NULL AND basis_period_end IS NULL)
        OR (basis_period_start IS NOT NULL AND basis_period_end IS NOT NULL
            AND basis_period_start <= basis_period_end)
    )
);

COMMENT ON TABLE  forecasts IS
    'Revenue forecast projections produced by statistical models. Stores point estimates '
    'with confidence intervals for future months.';
COMMENT ON COLUMN forecasts.target_date IS
    'The future month being forecasted (first day of month).';
COMMENT ON COLUMN forecasts.model_type IS
    'Which forecasting model produced this projection.';
COMMENT ON COLUMN forecasts.projected_value IS
    'Point estimate of projected revenue.';
COMMENT ON COLUMN forecasts.lower_bound IS
    'Lower bound of the confidence interval.';
COMMENT ON COLUMN forecasts.upper_bound IS
    'Upper bound of the confidence interval.';
COMMENT ON COLUMN forecasts.confidence_level IS
    'Confidence level for the interval (e.g., 0.95 = 95%). Default: 95%.';
COMMENT ON COLUMN forecasts.model_metadata IS
    'JSONB blob with model hyperparameters, fit statistics (RMSE, MAPE), training details.';
COMMENT ON COLUMN forecasts.basis_period_start IS
    'Start of the historical data window used to train the model.';

-- Retrieve latest forecast for a city
CREATE INDEX idx_forecast_copo_date ON forecasts (copo, tax_type, target_date DESC);

-- Compare models
CREATE INDEX idx_forecast_model ON forecasts (model_type, target_date DESC);

-- NAICS-level forecasts
CREATE INDEX idx_forecast_naics ON forecasts (activity_code, target_date DESC)
    WHERE activity_code IS NOT NULL;


-- ===========================  MATERIALIZED VIEWS  ==========================

-- ---------------------------------------------------------------------------
-- mv_monthly_revenue_by_city
-- Aggregates all three tax types into one row per city per month.
-- Refresh after each data import cycle.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW mv_monthly_revenue_by_city AS
SELECT
    j.copo,
    j.name                                          AS jurisdiction_name,
    j.jurisdiction_type,
    j.county_name,
    l.voucher_date,
    l.calendar_year,
    l.calendar_month,
    l.fiscal_year,
    SUM(l.returned)                                 AS total_returned,
    SUM(l.returned) FILTER (WHERE l.tax_type = 'sales')   AS sales_returned,
    SUM(l.returned) FILTER (WHERE l.tax_type = 'use')     AS use_returned,
    SUM(l.returned) FILTER (WHERE l.tax_type = 'lodging') AS lodging_returned,
    SUM(l.current_month_collection)                 AS total_collected,
    SUM(l.refunded)                                 AS total_refunded,
    -- Per-capita (NULL when population unavailable)
    CASE WHEN j.population > 0
         THEN ROUND(SUM(l.returned) / j.population, 2)
         ELSE NULL
    END                                             AS returned_per_capita
FROM ledger_records l
JOIN jurisdictions j ON j.copo = l.copo
GROUP BY
    j.copo, j.name, j.jurisdiction_type, j.county_name, j.population,
    l.voucher_date, l.calendar_year, l.calendar_month, l.fiscal_year
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW mv_monthly_revenue_by_city IS
    'Pre-aggregated monthly revenue by city across all tax types. '
    'Includes per-capita metric. Refresh after every import.';

CREATE UNIQUE INDEX uidx_mv_monthly_rev_city
    ON mv_monthly_revenue_by_city (copo, voucher_date);
CREATE INDEX idx_mv_monthly_rev_date
    ON mv_monthly_revenue_by_city (voucher_date DESC);
CREATE INDEX idx_mv_monthly_rev_county
    ON mv_monthly_revenue_by_city (county_name, voucher_date DESC)
    WHERE county_name IS NOT NULL;


-- ---------------------------------------------------------------------------
-- mv_top_naics_by_city
-- Top NAICS industry drivers per city per month, ranked by sector_total.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW mv_top_naics_by_city AS
WITH ranked AS (
    SELECT
        n.copo,
        j.name                  AS jurisdiction_name,
        n.tax_type,
        n.report_date,
        n.calendar_year,
        n.calendar_month,
        n.activity_code,
        nc.description          AS activity_description,
        n.sector,
        nc.sector_description,
        n.sector_total,
        n.year_to_date,
        -- Rank within each city+tax_type+month
        ROW_NUMBER() OVER (
            PARTITION BY n.copo, n.tax_type, n.report_date
            ORDER BY n.sector_total DESC
        ) AS revenue_rank,
        -- Percentage of city total for this tax type + month
        ROUND(
            n.sector_total * 100.0
            / NULLIF(SUM(n.sector_total) OVER (
                PARTITION BY n.copo, n.tax_type, n.report_date
            ), 0),
            2
        ) AS pct_of_city_total
    FROM naics_records n
    JOIN jurisdictions j  ON j.copo = n.copo
    JOIN naics_codes   nc ON nc.activity_code = n.activity_code
)
SELECT *
FROM ranked
WHERE revenue_rank <= 25
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW mv_top_naics_by_city IS
    'Top 25 NAICS revenue drivers per city per tax type per month. '
    'Includes percentage-of-total and rank. Refresh after every import.';

CREATE UNIQUE INDEX uidx_mv_top_naics
    ON mv_top_naics_by_city (copo, tax_type, report_date, activity_code);
CREATE INDEX idx_mv_top_naics_date
    ON mv_top_naics_by_city (report_date DESC, copo);
CREATE INDEX idx_mv_top_naics_activity
    ON mv_top_naics_by_city (activity_code, report_date DESC);


-- ---------------------------------------------------------------------------
-- mv_yoy_comparison
-- Year-over-year revenue comparison for each city + tax type + calendar month.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW mv_yoy_comparison AS
WITH monthly AS (
    SELECT
        copo,
        tax_type,
        calendar_year,
        calendar_month,
        voucher_date,
        returned
    FROM ledger_records
),
with_prior AS (
    SELECT
        m.copo,
        j.name                  AS jurisdiction_name,
        m.tax_type,
        m.calendar_year,
        m.calendar_month,
        m.voucher_date,
        m.returned              AS current_returned,
        LAG(m.returned) OVER (
            PARTITION BY m.copo, m.tax_type, m.calendar_month
            ORDER BY m.calendar_year
        )                       AS prior_year_returned
    FROM monthly m
    JOIN jurisdictions j ON j.copo = m.copo
)
SELECT
    copo,
    jurisdiction_name,
    tax_type,
    calendar_year,
    calendar_month,
    voucher_date,
    current_returned,
    prior_year_returned,
    current_returned - prior_year_returned          AS yoy_change,
    CASE WHEN prior_year_returned IS NOT NULL AND prior_year_returned != 0
         THEN ROUND(
             ((current_returned - prior_year_returned) / ABS(prior_year_returned)) * 100,
             2
         )
         ELSE NULL
    END                                             AS yoy_change_pct
FROM with_prior
WHERE prior_year_returned IS NOT NULL
WITH NO DATA;

COMMENT ON MATERIALIZED VIEW mv_yoy_comparison IS
    'Year-over-year revenue comparison per city per tax type per calendar month. '
    'Shows absolute and percentage change. Refresh after every import.';

CREATE UNIQUE INDEX uidx_mv_yoy
    ON mv_yoy_comparison (copo, tax_type, calendar_year, calendar_month);
CREATE INDEX idx_mv_yoy_date
    ON mv_yoy_comparison (calendar_year DESC, calendar_month);
CREATE INDEX idx_mv_yoy_change
    ON mv_yoy_comparison (yoy_change_pct DESC NULLS LAST);


-- ===========================  HELPER FUNCTIONS  ============================

-- ---------------------------------------------------------------------------
-- Convenience function to refresh all materialized views.
-- Call this after every import cycle completes.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION refresh_materialized_views()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_revenue_by_city;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_top_naics_by_city;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_yoy_comparison;
END;
$$;

COMMENT ON FUNCTION refresh_materialized_views() IS
    'Refreshes all analytics materialized views concurrently (non-blocking). '
    'Call after each data import cycle completes.';


-- ---------------------------------------------------------------------------
-- Auto-update updated_at timestamp on jurisdictions and anomalies.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_jurisdictions_updated_at
    BEFORE UPDATE ON jurisdictions
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER trg_anomalies_updated_at
    BEFORE UPDATE ON anomalies
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();


-- ===========================  CONTACTS  ====================================

CREATE TABLE IF NOT EXISTS contacts (
    id                  SERIAL PRIMARY KEY,
    batch_id            VARCHAR(20)  NOT NULL,
    jurisdiction_type   VARCHAR(10)  NOT NULL CHECK (jurisdiction_type IN ('city', 'county')),
    jurisdiction_name   VARCHAR(255) NOT NULL,
    population_rank_2024 INTEGER,
    office_title        VARCHAR(255),
    district_or_ward    VARCHAR(100),
    person_name         VARCHAR(255),
    phone               VARCHAR(50),
    email               VARCHAR(255),
    contact_type        VARCHAR(30)  CHECK (contact_type IN ('direct', 'staff', 'general', 'general office')),
    source_url          TEXT,
    notes               TEXT,
    verified_date       DATE,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_contacts_jurisdiction ON contacts (jurisdiction_name);
CREATE INDEX idx_contacts_type ON contacts (jurisdiction_type);
CREATE INDEX idx_contacts_email ON contacts (email) WHERE email IS NOT NULL AND email != '';
CREATE INDEX idx_contacts_batch ON contacts (batch_id);

COMMENT ON TABLE contacts IS
    'Elected officials and staff contacts for Oklahoma cities and counties. '
    'Used for MuniRev GTM outreach. Source: official city/county websites.';

CREATE TRIGGER trg_contacts_updated_at
    BEFORE UPDATE ON contacts
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();


COMMIT;
