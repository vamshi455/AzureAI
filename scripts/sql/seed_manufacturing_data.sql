-- =============================================================================
-- Seed Manufacturing Data for manufacturing_db
-- =============================================================================
-- Purpose:  Generate realistic synthetic manufacturing data (equipment health,
--           IoT telemetry, lifecycle events) purely in SQL using generate_series
--           and random().  Data distributions match the ML pipeline output:
--             ~87% Low risk, ~8% Medium, ~3% Critical, ~2% High
--
-- Target:   manufacturing_db (PostgreSQL 15+)
-- Usage:    psql -d manufacturing_db -f seed_manufacturing_data.sql
-- Idempotent: Yes -- drops and recreates all tables.
-- =============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 0. Deterministic seed for repeatable random data
-- ---------------------------------------------------------------------------
SELECT setseed(0.42);

-- ---------------------------------------------------------------------------
-- 1. Equipment Health table
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS iot_telemetry CASCADE;
DROP TABLE IF EXISTS equipment_lifecycle_events CASCADE;
DROP TABLE IF EXISTS equipment_health CASCADE;

CREATE TABLE equipment_health (
    equipment_id            TEXT PRIMARY KEY,
    plant_code              TEXT NOT NULL,
    production_line         TEXT,
    device_ids              TEXT,
    health_score            NUMERIC(5,2),
    failure_risk            TEXT CHECK (failure_risk IN ('Low', 'Medium', 'High', 'Critical')),
    failure_probability     NUMERIC(5,4),
    estimated_rul_days      INTEGER,
    last_maintenance_date   DATE,
    next_recommended_date   DATE,
    recommended_action      TEXT,
    anomaly_count_30d       INTEGER DEFAULT 0,
    top_risk_factors        JSONB,
    sensor_summary          JSONB,
    model_version           TEXT,
    computed_at             TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_eq_health_plant ON equipment_health (plant_code);
CREATE INDEX idx_eq_health_risk  ON equipment_health (failure_risk);
CREATE INDEX idx_eq_health_score ON equipment_health (health_score);

-- ---------------------------------------------------------------------------
-- 2. IoT Telemetry table
-- ---------------------------------------------------------------------------
CREATE TABLE iot_telemetry (
    id                      BIGSERIAL PRIMARY KEY,
    equipment_id            TEXT NOT NULL,
    device_id               TEXT NOT NULL,
    sensor_type             TEXT NOT NULL,
    reading_value           NUMERIC(10,4),
    reading_unit            TEXT,
    quality_flag            TEXT DEFAULT 'GOOD',
    reading_timestamp       TIMESTAMPTZ NOT NULL,
    plant_code              TEXT,
    production_line         TEXT
);

CREATE INDEX idx_telemetry_equip_time
    ON iot_telemetry (equipment_id, reading_timestamp DESC);
CREATE INDEX idx_telemetry_sensor
    ON iot_telemetry (sensor_type, reading_timestamp DESC);
CREATE INDEX idx_telemetry_anomaly
    ON iot_telemetry (quality_flag) WHERE quality_flag != 'GOOD';
CREATE INDEX idx_telemetry_plant
    ON iot_telemetry (plant_code);

-- ---------------------------------------------------------------------------
-- 3. Equipment Lifecycle Events table
-- ---------------------------------------------------------------------------
CREATE TABLE equipment_lifecycle_events (
    id                      BIGSERIAL PRIMARY KEY,
    equipment_id            TEXT NOT NULL,
    event_type              TEXT NOT NULL,
    from_state              TEXT,
    to_state                TEXT,
    event_timestamp         TIMESTAMPTZ NOT NULL,
    plant_code              TEXT
);

CREATE INDEX idx_lifecycle_equip
    ON equipment_lifecycle_events (equipment_id, event_timestamp DESC);

-- ---------------------------------------------------------------------------
-- 4. Helper: equipment inventory CTE (200 machines)
--    4 plants x 4 lines x ~13 machines  = 208  (we trim to 200)
-- ---------------------------------------------------------------------------
-- Plants: 1100, 1200, 2100, 2200  (skip 3100 Distribution Center)
-- Lines:  LINE-A .. LINE-D
-- Machines per line: 13 (with a few lines having 12 to hit exactly 200)

-- We build the cartesian product and use row_number to keep exactly 200.

-- ---------------------------------------------------------------------------
-- 5. Populate equipment_health  (200 rows)
-- ---------------------------------------------------------------------------

INSERT INTO equipment_health (
    equipment_id, plant_code, production_line, device_ids,
    health_score, failure_risk, failure_probability,
    estimated_rul_days, last_maintenance_date, next_recommended_date,
    recommended_action, anomaly_count_30d, top_risk_factors,
    sensor_summary, model_version
)
SELECT
    -- equipment_id:  EQ-{plant}-{line_letter}-{seq 001..013}
    'EQ-' || plant || '-' || line_letter || '-' || LPAD(machine::TEXT, 3, '0') AS equipment_id,
    plant::TEXT AS plant_code,
    'LINE-' || line_letter AS production_line,

    -- device_ids: comma-separated list of 3 device ids per equipment
    'DEV-' || plant || '-' || line_letter || '-' || LPAD(machine::TEXT,3,'0') || '-01,' ||
    'DEV-' || plant || '-' || line_letter || '-' || LPAD(machine::TEXT,3,'0') || '-02,' ||
    'DEV-' || plant || '-' || line_letter || '-' || LPAD(machine::TEXT,3,'0') || '-03'
    AS device_ids,

    -- health_score: weighted random matching ~87% Good(80-100), ~8% Fair(60-79), ~3% Critical(20-59), ~2% High-risk(0-19)
    CASE
        WHEN rnd < 0.02  THEN ROUND((random() * 19)::NUMERIC, 2)                     -- 0-19  (2% Failed/Failing)
        WHEN rnd < 0.05  THEN ROUND((20 + random() * 39)::NUMERIC, 2)                -- 20-59 (3% Poor/Critical)
        WHEN rnd < 0.13  THEN ROUND((60 + random() * 19)::NUMERIC, 2)                -- 60-79 (8% Fair)
        ELSE                  ROUND((80 + random() * 20)::NUMERIC, 2)                 -- 80-100 (87% Good)
    END AS health_score,

    -- failure_risk derived from health_score bucket
    CASE
        WHEN rnd < 0.02  THEN 'Critical'
        WHEN rnd < 0.05  THEN 'High'
        WHEN rnd < 0.13  THEN 'Medium'
        ELSE                  'Low'
    END AS failure_risk,

    -- failure_probability correlated with risk
    CASE
        WHEN rnd < 0.02  THEN ROUND((0.70 + random() * 0.30)::NUMERIC, 4)
        WHEN rnd < 0.05  THEN ROUND((0.40 + random() * 0.30)::NUMERIC, 4)
        WHEN rnd < 0.13  THEN ROUND((0.15 + random() * 0.25)::NUMERIC, 4)
        ELSE                  ROUND((0.01 + random() * 0.14)::NUMERIC, 4)
    END AS failure_probability,

    -- estimated_rul_days (remaining useful life)
    CASE
        WHEN rnd < 0.02  THEN (random() * 14)::INTEGER
        WHEN rnd < 0.05  THEN (15 + random() * 45)::INTEGER
        WHEN rnd < 0.13  THEN (60 + random() * 120)::INTEGER
        ELSE                  (180 + random() * 365)::INTEGER
    END AS estimated_rul_days,

    -- last_maintenance_date: random date in last 180 days
    (CURRENT_DATE - (random() * 180)::INTEGER)::DATE AS last_maintenance_date,

    -- next_recommended_date: correlated with risk
    CASE
        WHEN rnd < 0.02  THEN (CURRENT_DATE + (random() * 3)::INTEGER)::DATE          -- within 3 days
        WHEN rnd < 0.05  THEN (CURRENT_DATE + (3 + random() * 14)::INTEGER)::DATE     -- 3-17 days
        WHEN rnd < 0.13  THEN (CURRENT_DATE + (14 + random() * 60)::INTEGER)::DATE    -- 14-74 days
        ELSE                  (CURRENT_DATE + (60 + random() * 180)::INTEGER)::DATE    -- 60-240 days
    END AS next_recommended_date,

    -- recommended_action
    CASE
        WHEN rnd < 0.02  THEN (ARRAY[
            'EMERGENCY: Immediate shutdown and inspection required',
            'EMERGENCY: Replace failing bearing assembly immediately',
            'EMERGENCY: Critical motor overheating — isolate and inspect'
        ])[1 + (random() * 2)::INTEGER]
        WHEN rnd < 0.05  THEN (ARRAY[
            'Schedule urgent maintenance within 2 weeks — vibration exceeds threshold',
            'Plan bearing replacement — degradation trend detected',
            'Inspect cooling system — temperature readings trending high',
            'Replace worn drive belt — power consumption anomaly detected'
        ])[1 + (random() * 3)::INTEGER]
        WHEN rnd < 0.13  THEN (ARRAY[
            'Monitor closely — minor vibration increase observed',
            'Schedule lubrication during next planned downtime',
            'Review sensor calibration — occasional uncertain readings',
            'Plan filter replacement at next maintenance window'
        ])[1 + (random() * 3)::INTEGER]
        ELSE (ARRAY[
            'Continue routine monitoring — all parameters nominal',
            'No action required — equipment operating within normal range',
            'Standard preventive maintenance per schedule',
            'Routine inspection at next planned downtime'
        ])[1 + (random() * 3)::INTEGER]
    END AS recommended_action,

    -- anomaly_count_30d: correlated with risk
    CASE
        WHEN rnd < 0.02  THEN (15 + random() * 35)::INTEGER
        WHEN rnd < 0.05  THEN (5 + random() * 15)::INTEGER
        WHEN rnd < 0.13  THEN (1 + random() * 8)::INTEGER
        ELSE                  (random() * 3)::INTEGER
    END AS anomaly_count_30d,

    -- top_risk_factors (JSONB array)
    CASE
        WHEN rnd < 0.05  THEN '["high_vibration_trend", "temperature_exceedance", "bearing_wear_indicator", "power_consumption_anomaly"]'::JSONB
        WHEN rnd < 0.13  THEN '["minor_vibration_increase", "humidity_fluctuation"]'::JSONB
        ELSE                  '["none"]'::JSONB
    END AS top_risk_factors,

    -- sensor_summary (JSONB object with latest reading per sensor type)
    jsonb_build_object(
        'temperature', jsonb_build_object(
            'value', ROUND((35 + random() * 20)::NUMERIC, 1),
            'unit', '°C',
            'status', CASE WHEN rnd < 0.05 THEN 'WARNING' ELSE 'NORMAL' END
        ),
        'vibration', jsonb_build_object(
            'value', ROUND((1 + random() * 3)::NUMERIC, 2),
            'unit', 'mm/s',
            'status', CASE WHEN rnd < 0.05 THEN 'WARNING' ELSE 'NORMAL' END
        ),
        'pressure', jsonb_build_object(
            'value', ROUND((2 + random() * 4)::NUMERIC, 2),
            'unit', 'bar',
            'status', 'NORMAL'
        ),
        'humidity', jsonb_build_object(
            'value', ROUND((30 + random() * 30)::NUMERIC, 1),
            'unit', '%RH',
            'status', 'NORMAL'
        ),
        'flow_rate', jsonb_build_object(
            'value', ROUND((50 + random() * 150)::NUMERIC, 1),
            'unit', 'L/min',
            'status', 'NORMAL'
        ),
        'power', jsonb_build_object(
            'value', ROUND((1 + random() * 9)::NUMERIC, 2),
            'unit', 'kW',
            'status', 'NORMAL'
        )
    ) AS sensor_summary,

    'v2.1-rf-39features' AS model_version

FROM (
    SELECT
        plant,
        line_letter,
        machine,
        random() AS rnd,
        ROW_NUMBER() OVER () AS rn
    FROM
        (SELECT unnest(ARRAY[1100, 1200, 2100, 2200]) AS plant) p
        CROSS JOIN (SELECT unnest(ARRAY['A','B','C','D']) AS line_letter) l
        CROSS JOIN generate_series(1, 13) AS machine
    ORDER BY plant, line_letter, machine
) eq
WHERE rn <= 200;

-- ---------------------------------------------------------------------------
-- 6. Populate iot_telemetry  (500,000 rows)
-- ---------------------------------------------------------------------------
-- Strategy: generate 500k rows by picking random equipment from the 200 we
-- just inserted, random sensor types, realistic values per type, and
-- timestamps spanning the last 2 years (2024-01-01 to 2025-12-31).

INSERT INTO iot_telemetry (
    equipment_id, device_id, sensor_type, reading_value, reading_unit,
    quality_flag, reading_timestamp, plant_code, production_line
)
SELECT
    eq.equipment_id,
    -- pick one of the 3 device IDs (simulate via suffix)
    'DEV' || SUBSTRING(eq.equipment_id FROM 3) || '-0' || (1 + (random() * 2)::INTEGER)::TEXT AS device_id,

    sensor.sensor_type,

    -- reading_value: realistic ranges per sensor type
    CASE sensor.sensor_type
        WHEN 'temperature' THEN ROUND((35 + random() * 20)::NUMERIC, 2)                       -- 35-55 C
        WHEN 'vibration'   THEN ROUND((1 + random() * 3)::NUMERIC, 3)                         -- 1-4 mm/s
        WHEN 'pressure'    THEN ROUND((2 + random() * 4)::NUMERIC, 2)                         -- 2-6 bar
        WHEN 'humidity'    THEN ROUND((30 + random() * 30)::NUMERIC, 1)                        -- 30-60 %RH
        WHEN 'flow_rate'   THEN ROUND((50 + random() * 150)::NUMERIC, 1)                      -- 50-200 L/min
        WHEN 'power'       THEN ROUND((1 + random() * 9)::NUMERIC, 2)                         -- 1-10 kW
    END AS reading_value,

    -- reading_unit
    CASE sensor.sensor_type
        WHEN 'temperature' THEN '°C'
        WHEN 'vibration'   THEN 'mm/s'
        WHEN 'pressure'    THEN 'bar'
        WHEN 'humidity'    THEN '%RH'
        WHEN 'flow_rate'   THEN 'L/min'
        WHEN 'power'       THEN 'kW'
    END AS reading_unit,

    -- quality_flag: 95% GOOD, 3% UNCERTAIN, 2% BAD
    CASE
        WHEN qf_rnd < 0.02 THEN 'BAD'
        WHEN qf_rnd < 0.05 THEN 'UNCERTAIN'
        ELSE 'GOOD'
    END AS quality_flag,

    -- reading_timestamp: random within 2024-01-01 to 2025-12-31  (730 days)
    '2024-01-01 00:00:00+00'::TIMESTAMPTZ
        + (random() * 730 * 24 * 3600)::INTEGER * INTERVAL '1 second'
    AS reading_timestamp,

    eq.plant_code,
    eq.production_line

FROM (
    -- Generate 500,000 row stubs
    SELECT
        -- Pick a random equipment row number (1..200)
        (1 + (random() * 199)::INTEGER) AS eq_idx,
        -- Pick a random sensor type (1..6)
        (1 + (random() * 5)::INTEGER)   AS sensor_idx,
        random() AS qf_rnd
    FROM generate_series(1, 500000)
) g
-- Map eq_idx to an actual equipment_id
JOIN LATERAL (
    SELECT equipment_id, plant_code, production_line
    FROM equipment_health
    ORDER BY equipment_id
    LIMIT 1 OFFSET g.eq_idx - 1
) eq ON TRUE
-- Map sensor_idx to a sensor type
JOIN LATERAL (
    SELECT (ARRAY['temperature','vibration','pressure','humidity','flow_rate','power'])[g.sensor_idx] AS sensor_type
) sensor ON TRUE;

-- ---------------------------------------------------------------------------
-- 7. Populate equipment_lifecycle_events
-- ---------------------------------------------------------------------------
-- Generate ~2-8 lifecycle events per equipment (state machine transitions).
-- States: HEALTHY -> DEGRADING -> WARNING -> CRITICAL -> FAILED -> MAINTAINED -> HEALTHY

INSERT INTO equipment_lifecycle_events (
    equipment_id, event_type, from_state, to_state,
    event_timestamp, plant_code
)
SELECT
    eq.equipment_id,
    evt.event_type,
    evt.from_state,
    evt.to_state,
    evt.event_timestamp,
    eq.plant_code
FROM equipment_health eq
CROSS JOIN LATERAL (
    -- Each piece of equipment gets a chain of lifecycle events
    -- Start with initial commissioning, then random transitions
    SELECT * FROM (
        VALUES
        -- Event 1: Initial deployment (always)
        (
            'commissioning',
            NULL::TEXT,
            'HEALTHY',
            '2024-01-01'::TIMESTAMPTZ + (random() * 30)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 2: First degradation (some equipment)
        (
            'state_change',
            'HEALTHY',
            'DEGRADING',
            '2024-02-01'::TIMESTAMPTZ + (random() * 90)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 3: Warning (some equipment)
        (
            'state_change',
            'DEGRADING',
            'WARNING',
            '2024-05-01'::TIMESTAMPTZ + (random() * 60)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 4: Maintenance started
        (
            'maintenance_start',
            'WARNING',
            'MAINTAINED',
            '2024-07-01'::TIMESTAMPTZ + (random() * 60)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 5: Maintenance complete -> back to HEALTHY
        (
            'maintenance_complete',
            'MAINTAINED',
            'HEALTHY',
            '2024-09-01'::TIMESTAMPTZ + (random() * 60)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 6: Second cycle degradation (subset)
        (
            'state_change',
            'HEALTHY',
            'DEGRADING',
            '2025-01-01'::TIMESTAMPTZ + (random() * 90)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 7: Some go to CRITICAL
        (
            'state_change',
            'DEGRADING',
            'CRITICAL',
            '2025-05-01'::TIMESTAMPTZ + (random() * 60)::INTEGER * INTERVAL '1 day'
        ),
        -- Event 8: Failure (rare)
        (
            'failure',
            'CRITICAL',
            'FAILED',
            '2025-07-01'::TIMESTAMPTZ + (random() * 90)::INTEGER * INTERVAL '1 day'
        )
    ) AS t(event_type, from_state, to_state, event_timestamp)
    -- Include subset of events based on equipment risk level to make it realistic
    WHERE
        -- All equipment gets commissioning (row 1) and first degradation cycle (rows 2-5)
        (t.event_type = 'commissioning')
        OR (t.from_state = 'HEALTHY' AND t.to_state = 'DEGRADING' AND random() < 0.6)
        OR (t.from_state = 'DEGRADING' AND t.to_state = 'WARNING' AND random() < 0.4)
        OR (t.event_type = 'maintenance_start' AND random() < 0.35)
        OR (t.event_type = 'maintenance_complete' AND random() < 0.35)
        OR (t.from_state = 'HEALTHY' AND t.to_state = 'DEGRADING' AND t.event_timestamp > '2025-01-01' AND random() < 0.3)
        OR (t.from_state = 'DEGRADING' AND t.to_state = 'CRITICAL' AND random() < 0.08)
        OR (t.event_type = 'failure' AND random() < 0.03)
) evt;

-- ---------------------------------------------------------------------------
-- 8. Summary statistics
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    eq_count   BIGINT;
    iot_count  BIGINT;
    lce_count  BIGINT;
BEGIN
    SELECT COUNT(*) INTO eq_count  FROM equipment_health;
    SELECT COUNT(*) INTO iot_count FROM iot_telemetry;
    SELECT COUNT(*) INTO lce_count FROM equipment_lifecycle_events;

    RAISE NOTICE '=== Seed Manufacturing Data Complete ===';
    RAISE NOTICE 'equipment_health:           % rows', eq_count;
    RAISE NOTICE 'iot_telemetry:              % rows', iot_count;
    RAISE NOTICE 'equipment_lifecycle_events: % rows', lce_count;

    -- Distribution check
    RAISE NOTICE '';
    RAISE NOTICE '--- Health Score Distribution ---';
END $$;

-- Print risk distribution
SELECT
    failure_risk,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM equipment_health
GROUP BY failure_risk
ORDER BY
    CASE failure_risk
        WHEN 'Low' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'High' THEN 3
        WHEN 'Critical' THEN 4
    END;

-- Print quality flag distribution
SELECT
    quality_flag,
    COUNT(*) AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM iot_telemetry
GROUP BY quality_flag
ORDER BY count DESC;

COMMIT;

-- =============================================================================
-- Done. The manufacturing_db now contains:
--   - 200 equipment_health rows (4 plants x 4 lines x ~13 machines)
--   - 500,000 iot_telemetry rows (6 sensor types, 2-year span)
--   - ~600-800 equipment_lifecycle_events (state machine transitions)
-- =============================================================================
