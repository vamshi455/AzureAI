-- =============================================================================
-- Gold Layer Schema Definitions
-- Purpose: Curated, business-ready tables optimized for analytics, BI
--          dashboards, and ML model consumption. Star schema design with
--          fact and dimension tables.
-- Platform: Microsoft Fabric Lakehouse (Delta Lake format)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- dim_date: Calendar and fiscal date dimension
-- Grain: One row per calendar day
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.dim_date (
    date_key                    DATE            NOT NULL    COMMENT 'Calendar date (primary key)',
    date_id                     INT             NOT NULL    COMMENT 'Integer date key YYYYMMDD for fact table joins',

    -- Calendar Attributes
    calendar_year               INT             NOT NULL    COMMENT 'Calendar year (e.g., 2026)',
    calendar_quarter            INT             NOT NULL    COMMENT 'Calendar quarter (1-4)',
    calendar_month              INT             NOT NULL    COMMENT 'Calendar month (1-12)',
    calendar_week               INT             NOT NULL    COMMENT 'ISO week number (1-53)',
    day_of_month                INT             NOT NULL    COMMENT 'Day of month (1-31)',
    day_of_week                 INT             NOT NULL    COMMENT 'Day of week (1=Sun, 7=Sat)',
    day_of_year                 INT             NOT NULL    COMMENT 'Day of year (1-366)',
    day_name                    STRING          NOT NULL    COMMENT 'Day name (Monday, Tuesday, etc.)',
    month_name                  STRING          NOT NULL    COMMENT 'Month name (January, February, etc.)',
    month_year_label            STRING          NOT NULL    COMMENT 'Month-Year label (Jan-2026)',

    -- Fiscal Calendar (July - June fiscal year)
    fiscal_year                 INT             NOT NULL    COMMENT 'Fiscal year (Jul-Jun, e.g., FY2026)',
    fiscal_quarter              INT             NOT NULL    COMMENT 'Fiscal quarter (1-4, Q1=Jul-Sep)',

    -- Flags
    is_weekend                  BOOLEAN         NOT NULL    COMMENT 'True if Saturday or Sunday',
    iso_week_label              STRING          NOT NULL    COMMENT 'ISO week label (2026-W05)',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp'
)
USING DELTA
COMMENT 'Date dimension table with calendar and fiscal year attributes. Grain: one row per day.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'gold'
);


-- ---------------------------------------------------------------------------
-- dim_product: Product/material dimension
-- Grain: One row per unique material number (current state)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.dim_product (
    product_key                 STRING          NOT NULL    COMMENT 'SHA-256 surrogate key on material_number',
    material_number             STRING          NOT NULL    COMMENT 'SAP Material Number (business key)',
    material_group              STRING                      COMMENT 'Material group / product category',
    product_name                STRING                      COMMENT 'Product short description',
    product_division            STRING                      COMMENT 'Product division code',
    base_unit_of_measure        STRING                      COMMENT 'Base unit of measure for the product',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp'
)
USING DELTA
COMMENT 'Product dimension derived from sales order master data. Grain: one row per material.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'gold'
);


-- ---------------------------------------------------------------------------
-- dim_customer: Customer dimension
-- Grain: One row per unique customer (current state)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.dim_customer (
    customer_key                STRING          NOT NULL    COMMENT 'SHA-256 surrogate key on customer_number',
    customer_number             STRING          NOT NULL    COMMENT 'SAP Customer Number (business key)',
    sales_organization          STRING                      COMMENT 'Primary sales organization',
    distribution_channel        STRING                      COMMENT 'Primary distribution channel',
    customer_division           STRING                      COMMENT 'Customer division assignment',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp'
)
USING DELTA
COMMENT 'Customer dimension derived from sales data. Grain: one row per customer.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'gold'
);


-- ---------------------------------------------------------------------------
-- fact_sales: Sales order fact table
-- Grain: One row per sales order line item (current version only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.fact_sales (
    -- Dimension Foreign Keys
    product_key                 STRING          NOT NULL    COMMENT 'FK to dim_product',
    customer_key                STRING          NOT NULL    COMMENT 'FK to dim_customer',
    order_date_key              INT                         COMMENT 'FK to dim_date (order date YYYYMMDD)',
    delivery_date_key           INT                         COMMENT 'FK to dim_date (requested delivery date)',

    -- Degenerate Dimensions (order identifiers kept on fact)
    sales_document_number       STRING          NOT NULL    COMMENT 'Sales document number',
    item_number                 STRING          NOT NULL    COMMENT 'Line item number',
    sales_order_key             STRING          NOT NULL    COMMENT 'Composite key (document + item)',

    -- Descriptive Attributes
    order_type                  STRING                      COMMENT 'Sales document type',
    sales_organization          STRING                      COMMENT 'Sales organization',
    distribution_channel        STRING                      COMMENT 'Distribution channel',
    plant                       STRING                      COMMENT 'Delivering plant',
    storage_location            STRING                      COMMENT 'Storage location',
    is_rejected                 BOOLEAN                     COMMENT 'Whether line item is rejected',

    -- Measures
    order_quantity              DECIMAL(18, 3)              COMMENT 'Ordered quantity',
    net_value                   DECIMAL(18, 2)              COMMENT 'Net value of line item',
    currency                    STRING                      COMMENT 'Document currency',
    unit_price                  DECIMAL(18, 2)              COMMENT 'Calculated unit price (net_value / quantity)',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp',
    _gold_pipeline_run_id       STRING                      COMMENT 'Pipeline run that created this record'
)
USING DELTA
COMMENT 'Sales order fact table. Grain: one row per order line item (current versions only).'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'gold'
);

-- OPTIMIZE lh_gold.fact_sales ZORDER BY (order_date_key, product_key);


-- ---------------------------------------------------------------------------
-- agg_demand_forecast: Pre-computed demand forecast features for ML
-- Grain: One row per material + plant + day
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.agg_demand_forecast (
    -- Keys
    material_number             STRING          NOT NULL    COMMENT 'Material/product number',
    plant                       STRING          NOT NULL    COMMENT 'Plant code',
    order_date                  DATE            NOT NULL    COMMENT 'Aggregation date',

    -- Base Daily Metrics
    daily_quantity              DOUBLE                      COMMENT 'Total quantity ordered on this day',
    daily_revenue               DOUBLE                      COMMENT 'Total revenue on this day',
    daily_order_count           INT                         COMMENT 'Number of distinct orders',
    daily_unique_customers      INT                         COMMENT 'Number of unique customers',

    -- Rolling Window Features
    rolling_avg_qty_7d          DOUBLE                      COMMENT '7-day rolling average quantity',
    rolling_avg_qty_30d         DOUBLE                      COMMENT '30-day rolling average quantity',
    rolling_avg_qty_90d         DOUBLE                      COMMENT '90-day rolling average quantity',
    rolling_sum_qty_7d          DOUBLE                      COMMENT '7-day rolling total quantity',
    rolling_sum_qty_30d         DOUBLE                      COMMENT '30-day rolling total quantity',
    rolling_std_qty_30d         DOUBLE                      COMMENT '30-day rolling std dev of quantity',
    rolling_avg_revenue_30d     DOUBLE                      COMMENT '30-day rolling average revenue',
    rolling_avg_orders_30d      DOUBLE                      COMMENT '30-day rolling average order count',

    -- Lag Features
    lag_qty_1d                  DOUBLE                      COMMENT 'Previous day quantity',
    lag_qty_7d                  DOUBLE                      COMMENT 'Same day last week quantity',
    lag_qty_30d                 DOUBLE                      COMMENT 'Same day last month quantity',

    -- Temporal Features
    day_of_week                 INT                         COMMENT 'Day of week (1-7)',
    day_of_month                INT                         COMMENT 'Day of month (1-31)',
    week_of_year                INT                         COMMENT 'Week of year (1-53)',
    month                       INT                         COMMENT 'Month (1-12)',
    quarter                     INT                         COMMENT 'Quarter (1-4)',
    is_weekend                  INT                         COMMENT '1 if weekend, 0 otherwise',
    is_month_start              INT                         COMMENT '1 if first 3 days of month',
    is_month_end                INT                         COMMENT '1 if last 3 days of month',
    is_quarter_end              INT                         COMMENT '1 if last week of quarter',

    -- Derived Indicators
    demand_cv_30d               DOUBLE                      COMMENT 'Coefficient of variation (30d) - demand variability',
    trend_indicator             DOUBLE                      COMMENT 'Trend: (30d_avg - 90d_avg) / 90d_avg',
    avg_daily_demand_90d        DOUBLE                      COMMENT 'Overall 90-day average daily demand',
    product_velocity            STRING                      COMMENT 'A_FAST, B_MEDIUM, C_SLOW, D_VERY_SLOW',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp',
    _gold_pipeline_run_id       STRING                      COMMENT 'Pipeline run ID',
    _forecast_horizon_days      INT                         COMMENT 'Configured forecast horizon in days',
    _feature_version            STRING                      COMMENT 'Feature engineering version (for model tracking)'
)
USING DELTA
COMMENT 'Pre-computed demand forecast features for ML consumption. Grain: material + plant + day.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'gold'
);

-- OPTIMIZE lh_gold.agg_demand_forecast ZORDER BY (material_number, order_date);


-- ---------------------------------------------------------------------------
-- agg_product_metrics: Monthly product performance aggregations
-- Grain: One row per material + plant + sales org + month
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.agg_product_metrics (
    -- Keys
    material_number             STRING          NOT NULL    COMMENT 'Material number',
    plant                       STRING          NOT NULL    COMMENT 'Plant code',
    sales_organization          STRING          NOT NULL    COMMENT 'Sales organization',
    month_start                 DATE            NOT NULL    COMMENT 'First day of the month',

    -- Volume Metrics
    total_quantity              DECIMAL(18, 3)              COMMENT 'Total quantity ordered in month',
    total_revenue               DECIMAL(18, 2)              COMMENT 'Total net revenue in month',
    line_item_count             BIGINT                      COMMENT 'Number of order line items',
    order_count                 BIGINT                      COMMENT 'Number of distinct sales orders',
    unique_customers            BIGINT                      COMMENT 'Number of unique customers',

    -- Price Metrics
    avg_unit_price              DECIMAL(18, 2)              COMMENT 'Average unit price in month',
    min_unit_price              DECIMAL(18, 2)              COMMENT 'Minimum unit price in month',
    max_unit_price              DECIMAL(18, 2)              COMMENT 'Maximum unit price in month',

    -- Rejection Metrics
    rejected_line_items         BIGINT                      COMMENT 'Count of rejected line items',
    rejected_value              DECIMAL(18, 2)              COMMENT 'Total value of rejected items',

    -- Year-over-Year Comparison
    prev_year_revenue           DECIMAL(18, 2)              COMMENT 'Same month prior year revenue',
    prev_year_quantity          DECIMAL(18, 3)              COMMENT 'Same month prior year quantity',
    yoy_revenue_growth          DOUBLE                      COMMENT 'YoY revenue growth rate',
    yoy_quantity_growth         DOUBLE                      COMMENT 'YoY quantity growth rate',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp',
    _gold_pipeline_run_id       STRING                      COMMENT 'Pipeline run ID'
)
USING DELTA
COMMENT 'Monthly product performance metrics with YoY comparison. Grain: material + plant + org + month.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'gold'
);


-- ---------------------------------------------------------------------------
-- iot_equipment_health: Predictive maintenance health scores per equipment
-- Grain: One row per equipment (latest prediction)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.iot_equipment_health (
    -- Keys
    equipment_id                STRING          NOT NULL    COMMENT 'Equipment identifier (business key)',

    -- Dimension Attributes
    plant_code                  STRING          NOT NULL    COMMENT 'SAP plant code',
    production_line             STRING          NOT NULL    COMMENT 'Production line identifier',
    device_ids                  STRING                      COMMENT 'Comma-separated sensor device IDs',

    -- Health Metrics (from ML model)
    health_score                DECIMAL(5, 2)               COMMENT 'Overall health score 0-100 (100 = perfect)',
    failure_risk                STRING                      COMMENT 'Risk category: Low / Medium / High / Critical',
    failure_probability         DECIMAL(5, 4)               COMMENT 'Probability of failure within prediction horizon',
    estimated_rul_days          INT                         COMMENT 'Estimated remaining useful life in days',

    -- Maintenance
    last_maintenance_date       DATE                        COMMENT 'Date of last maintenance event',
    next_recommended_date       DATE                        COMMENT 'Recommended next maintenance date',
    recommended_action          STRING                      COMMENT 'Recommended maintenance action text',

    -- Sensor & Anomaly Summary
    anomaly_count_30d           INT                         COMMENT 'Anomaly count in last 30 days',
    top_risk_factors            STRING                      COMMENT 'JSON array of top risk factor descriptions',
    sensor_summary              STRING                      COMMENT 'JSON object: latest readings per sensor type',

    -- Model Metadata
    model_version               STRING                      COMMENT 'ML model version used for predictions',
    computed_at                 TIMESTAMP                   COMMENT 'Timestamp when predictions were computed',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp',
    _gold_pipeline_run_id       STRING                      COMMENT 'Pipeline run ID'
)
USING DELTA
COMMENT 'Equipment health predictions from predictive maintenance ML model. Grain: one row per equipment.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'gold'
);


-- ---------------------------------------------------------------------------
-- agg_equipment_metrics: Monthly equipment health and sensor aggregations
-- Grain: One row per equipment + month
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_gold.agg_equipment_metrics (
    -- Keys
    equipment_id                STRING          NOT NULL    COMMENT 'Equipment identifier',
    plant_code                  STRING          NOT NULL    COMMENT 'Plant code',
    month_start                 DATE            NOT NULL    COMMENT 'First day of the month',

    -- Sensor Metrics (monthly aggregates)
    avg_temperature             DOUBLE                      COMMENT 'Monthly average temperature reading (C)',
    avg_vibration               DOUBLE                      COMMENT 'Monthly average vibration reading (mm/s)',
    avg_pressure                DOUBLE                      COMMENT 'Monthly average pressure reading (bar)',
    avg_power                   DOUBLE                      COMMENT 'Monthly average power consumption (kW)',
    max_vibration               DOUBLE                      COMMENT 'Monthly maximum vibration peak (mm/s)',
    max_temperature             DOUBLE                      COMMENT 'Monthly maximum temperature peak (C)',

    -- Quality & Anomaly Metrics
    total_readings              BIGINT                      COMMENT 'Total sensor readings in month',
    anomaly_count               BIGINT                      COMMENT 'Readings with quality_flag != GOOD',
    bad_reading_pct             DOUBLE                      COMMENT 'Percentage of BAD quality readings',

    -- Health Tracking
    avg_health_score            DOUBLE                      COMMENT 'Average health score over month',
    min_health_score            DOUBLE                      COMMENT 'Minimum health score in month',
    maintenance_events          INT                         COMMENT 'Number of maintenance events in month',

    -- Metadata
    _gold_loaded_at             TIMESTAMP                   COMMENT 'Gold layer load timestamp',
    _gold_pipeline_run_id       STRING                      COMMENT 'Pipeline run ID'
)
USING DELTA
COMMENT 'Monthly equipment health and sensor metrics for trend analysis. Grain: equipment + month.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'gold'
);
