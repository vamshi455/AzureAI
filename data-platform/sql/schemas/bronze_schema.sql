-- =============================================================================
-- Bronze Layer Schema Definitions
-- Purpose: Raw landing zone tables preserving source data as-is.
--          All columns stored as strings to handle schema drift gracefully.
--          Metadata columns track lineage and ingestion provenance.
-- Platform: Microsoft Fabric Lakehouse (Delta Lake format)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- raw_sales_orders: Sales order headers and line items from ERP/SAP
-- Source: SAP S/4HANA tables VBAK (header) + VBAP (items)
-- Load pattern: Incremental CDC with watermark on AEDAT (last changed date)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_bronze.raw_sales_orders_header (
    -- SAP Header Fields (VBAK) - stored as-is from source
    VBELN                       STRING          NOT NULL    COMMENT 'Sales Document Number',
    ERDAT                       STRING                      COMMENT 'Created Date (YYYYMMDD)',
    ERZET                       STRING                      COMMENT 'Created Time (HHMMSS)',
    ERNAM                       STRING                      COMMENT 'Created By User',
    AUART                       STRING                      COMMENT 'Sales Document Type',
    VKORG                       STRING                      COMMENT 'Sales Organization',
    VTWEG                       STRING                      COMMENT 'Distribution Channel',
    SPART                       STRING                      COMMENT 'Division',
    KUNNR                       STRING                      COMMENT 'Sold-to Party (Customer Number)',
    BSTNK                       STRING                      COMMENT 'Customer Purchase Order Number',
    BSTDK                       STRING                      COMMENT 'Customer PO Date (YYYYMMDD)',
    NETWR                       STRING                      COMMENT 'Net Value (Header Level)',
    WAERK                       STRING                      COMMENT 'Document Currency',
    VDATU                       STRING                      COMMENT 'Requested Delivery Date (YYYYMMDD)',
    LIFSK                       STRING                      COMMENT 'Delivery Block',
    FAKSK                       STRING                      COMMENT 'Billing Block',
    ABSTK                       STRING                      COMMENT 'Rejection Status',
    AEDAT                       STRING                      COMMENT 'Last Changed Date (YYYYMMDD)',

    -- Bronze Metadata Columns
    _bronze_ingestion_timestamp TIMESTAMP       NOT NULL    COMMENT 'UTC timestamp when record was ingested',
    _bronze_batch_id            STRING          NOT NULL    COMMENT 'Unique batch identifier for this ingestion run',
    _bronze_pipeline_run_id     STRING          NOT NULL    COMMENT 'Pipeline run ID from Fabric Data Factory',
    _bronze_source_system       STRING          NOT NULL    COMMENT 'Source system identifier (ERP_SAP)',
    _bronze_source_table        STRING          NOT NULL    COMMENT 'Source table name in SAP',
    _bronze_load_type           STRING          NOT NULL    COMMENT 'Load type: full or incremental',
    _bronze_file_path           STRING                      COMMENT 'Source file path in landing zone',
    _bronze_row_hash            STRING          NOT NULL    COMMENT 'SHA-256 hash of all source columns for change detection'
)
USING DELTA
COMMENT 'Raw sales order headers from SAP S/4HANA. Append-only, immutable landing zone.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'delta.logRetentionDuration' = 'interval 30 days',
    'delta.deletedFileRetentionDuration' = 'interval 7 days',
    'quality' = 'bronze'
);


CREATE TABLE IF NOT EXISTS lh_bronze.raw_sales_orders_item (
    -- SAP Item Fields (VBAP) - stored as-is from source
    VBELN                       STRING          NOT NULL    COMMENT 'Sales Document Number',
    POSNR                       STRING          NOT NULL    COMMENT 'Item Number',
    MATNR                       STRING                      COMMENT 'Material Number',
    MATKL                       STRING                      COMMENT 'Material Group',
    ARKTX                       STRING                      COMMENT 'Short Text / Item Description',
    KWMENG                      STRING                      COMMENT 'Order Quantity',
    VRKME                       STRING                      COMMENT 'Sales Unit of Measure',
    NETWR                       STRING                      COMMENT 'Net Value (Item Level)',
    WAERK                       STRING                      COMMENT 'Currency',
    WERKS                       STRING                      COMMENT 'Plant',
    LGORT                       STRING                      COMMENT 'Storage Location',
    ABGRU                       STRING                      COMMENT 'Rejection Reason Code',
    AEDAT                       STRING                      COMMENT 'Last Changed Date (YYYYMMDD)',

    -- Bronze Metadata Columns
    _bronze_ingestion_timestamp TIMESTAMP       NOT NULL    COMMENT 'UTC timestamp when record was ingested',
    _bronze_batch_id            STRING          NOT NULL    COMMENT 'Unique batch identifier',
    _bronze_pipeline_run_id     STRING          NOT NULL    COMMENT 'Pipeline run ID',
    _bronze_source_system       STRING          NOT NULL    COMMENT 'Source system identifier',
    _bronze_source_table        STRING          NOT NULL    COMMENT 'Source table name',
    _bronze_load_type           STRING          NOT NULL    COMMENT 'Load type: full or incremental',
    _bronze_file_path           STRING                      COMMENT 'Source file path',
    _bronze_row_hash            STRING          NOT NULL    COMMENT 'SHA-256 hash of source columns'
)
USING DELTA
COMMENT 'Raw sales order line items from SAP S/4HANA. Append-only.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'bronze'
);


-- ---------------------------------------------------------------------------
-- raw_inventory: Stock levels from ERP/SAP
-- Source: SAP table MARD (storage location level inventory)
-- Load pattern: Full snapshot daily
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_bronze.raw_inventory (
    MATNR                       STRING          NOT NULL    COMMENT 'Material Number',
    WERKS                       STRING          NOT NULL    COMMENT 'Plant',
    LGORT                       STRING          NOT NULL    COMMENT 'Storage Location',
    LABST                       STRING                      COMMENT 'Unrestricted Stock Quantity',
    UMLME                       STRING                      COMMENT 'Stock in Transfer',
    INSME                       STRING                      COMMENT 'Quality Inspection Stock',
    EINME                       STRING                      COMMENT 'Restricted-Use Stock',
    SPEME                       STRING                      COMMENT 'Blocked Stock',
    RETME                       STRING                      COMMENT 'Returns Stock',
    AEDAT                       STRING                      COMMENT 'Last Changed Date (YYYYMMDD)',

    -- Bronze Metadata
    _bronze_ingestion_timestamp TIMESTAMP       NOT NULL    COMMENT 'UTC ingestion timestamp',
    _bronze_batch_id            STRING          NOT NULL    COMMENT 'Batch identifier',
    _bronze_pipeline_run_id     STRING          NOT NULL    COMMENT 'Pipeline run ID',
    _bronze_source_system       STRING          NOT NULL    COMMENT 'Source system (ERP_SAP)',
    _bronze_source_table        STRING          NOT NULL    COMMENT 'Source table (MARD)',
    _bronze_load_type           STRING          NOT NULL    COMMENT 'Load type',
    _bronze_file_path           STRING                      COMMENT 'Source file path',
    _bronze_row_hash            STRING          NOT NULL    COMMENT 'Row hash for change detection'
)
USING DELTA
COMMENT 'Raw inventory stock levels from SAP. Daily full snapshots.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'bronze'
);


-- ---------------------------------------------------------------------------
-- raw_iot_telemetry: IoT sensor data from manufacturing equipment
-- Source: Azure IoT Hub -> Event Hub -> ADLS Gen2 (JSON)
-- Load pattern: Near real-time micro-batch (every 5 minutes)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_bronze.raw_iot_telemetry (
    device_id                   STRING          NOT NULL    COMMENT 'IoT device/sensor identifier',
    device_type                 STRING                      COMMENT 'Device type (temperature, pressure, vibration, etc.)',
    plant_code                  STRING                      COMMENT 'Manufacturing plant code',
    production_line             STRING                      COMMENT 'Production line identifier',
    equipment_id                STRING                      COMMENT 'Equipment/machine identifier',
    measurement_type            STRING                      COMMENT 'Type of measurement',
    measurement_value           STRING                      COMMENT 'Sensor reading value (stored as string)',
    measurement_unit            STRING                      COMMENT 'Unit of measurement',
    event_timestamp             STRING                      COMMENT 'Sensor event timestamp (ISO 8601)',
    event_enqueued_timestamp    STRING                      COMMENT 'Event Hub enqueue timestamp',
    quality_flag                STRING                      COMMENT 'Data quality indicator from device',
    raw_payload                 STRING                      COMMENT 'Full JSON payload from IoT device',

    -- Bronze Metadata
    _bronze_ingestion_timestamp TIMESTAMP       NOT NULL    COMMENT 'UTC ingestion timestamp',
    _bronze_batch_id            STRING          NOT NULL    COMMENT 'Batch identifier',
    _bronze_pipeline_run_id     STRING          NOT NULL    COMMENT 'Pipeline run ID',
    _bronze_source_system       STRING          NOT NULL    COMMENT 'Source system (IOT)',
    _bronze_source_table        STRING          NOT NULL    COMMENT 'Source topic/stream',
    _bronze_load_type           STRING          NOT NULL    COMMENT 'Load type (streaming)',
    _bronze_file_path           STRING                      COMMENT 'Source file path in ADLS',
    _bronze_row_hash            STRING          NOT NULL    COMMENT 'Row hash'
)
USING DELTA
PARTITIONED BY (plant_code)
COMMENT 'Raw IoT sensor telemetry from manufacturing equipment. Near real-time ingestion.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'delta.logRetentionDuration' = 'interval 14 days',
    'quality' = 'bronze'
);


-- ---------------------------------------------------------------------------
-- raw_customers: Customer master data from CRM
-- Source: Dynamics 365 CRM / Dataverse
-- Load pattern: Daily incremental by modifiedon
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_bronze.raw_customers (
    accountid                   STRING          NOT NULL    COMMENT 'CRM Account ID (GUID)',
    accountnumber               STRING                      COMMENT 'Account Number',
    name                        STRING                      COMMENT 'Account / Company Name',
    address1_line1              STRING                      COMMENT 'Address Line 1',
    address1_line2              STRING                      COMMENT 'Address Line 2',
    address1_city               STRING                      COMMENT 'City',
    address1_stateorprovince    STRING                      COMMENT 'State / Province',
    address1_postalcode         STRING                      COMMENT 'Postal Code',
    address1_country            STRING                      COMMENT 'Country',
    telephone1                  STRING                      COMMENT 'Primary Phone',
    emailaddress1               STRING                      COMMENT 'Primary Email',
    industrycode                STRING                      COMMENT 'Industry Code',
    customertypecode            STRING                      COMMENT 'Customer Type (Prospect, Customer, etc.)',
    revenue                     STRING                      COMMENT 'Annual Revenue',
    numberofemployees           STRING                      COMMENT 'Number of Employees',
    ownerid                     STRING                      COMMENT 'Record Owner ID',
    createdon                   STRING                      COMMENT 'Created On (ISO 8601)',
    modifiedon                  STRING                      COMMENT 'Modified On (ISO 8601)',
    statecode                   STRING                      COMMENT 'Status (0=Active, 1=Inactive)',
    statuscode                  STRING                      COMMENT 'Status Reason',
    sap_customer_number         STRING                      COMMENT 'Linked SAP Customer Number (KUNNR)',

    -- Bronze Metadata
    _bronze_ingestion_timestamp TIMESTAMP       NOT NULL    COMMENT 'UTC ingestion timestamp',
    _bronze_batch_id            STRING          NOT NULL    COMMENT 'Batch identifier',
    _bronze_pipeline_run_id     STRING          NOT NULL    COMMENT 'Pipeline run ID',
    _bronze_source_system       STRING          NOT NULL    COMMENT 'Source system (CRM)',
    _bronze_source_table        STRING          NOT NULL    COMMENT 'Source entity (account)',
    _bronze_load_type           STRING          NOT NULL    COMMENT 'Load type',
    _bronze_file_path           STRING                      COMMENT 'Source file path',
    _bronze_row_hash            STRING          NOT NULL    COMMENT 'Row hash'
)
USING DELTA
COMMENT 'Raw customer master data from Dynamics 365 CRM.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'bronze'
);


-- ---------------------------------------------------------------------------
-- Audit and Watermark Tables
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_bronze.bronze_ingestion_audit_log (
    batch_id                    STRING          NOT NULL,
    pipeline_run_id             STRING          NOT NULL,
    timestamp                   STRING          NOT NULL,
    level                       STRING          NOT NULL,
    source_system               STRING,
    source_table                STRING,
    target_table                STRING,
    message                     STRING,
    rows_read                   BIGINT,
    rows_written                BIGINT,
    error_detail                STRING,
    environment                 STRING
)
USING DELTA
COMMENT 'Audit log for bronze ingestion pipeline runs.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'bronze'
);


CREATE TABLE IF NOT EXISTS lh_bronze.ingestion_watermarks (
    source_table                STRING          NOT NULL,
    target_table                STRING          NOT NULL,
    watermark_column            STRING          NOT NULL,
    watermark_value             STRING          NOT NULL,
    updated_at                  STRING          NOT NULL
)
USING DELTA
COMMENT 'Watermark tracking for incremental data extraction.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'bronze'
);
