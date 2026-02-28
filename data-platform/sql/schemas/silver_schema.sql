-- =============================================================================
-- Silver Layer Schema Definitions
-- Purpose: Cleaned, conformed, and validated data with proper data types,
--          deduplication, and SCD Type 2 history tracking.
-- Platform: Microsoft Fabric Lakehouse (Delta Lake format)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- cleaned_sales_orders: Conformed sales order data with SCD2 history
-- Source: lh_bronze.raw_sales_orders_header + lh_bronze.raw_sales_orders_item
-- Grain: One row per sales document + item number + effective version
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_silver.cleaned_sales_orders (
    -- Surrogate Key
    sales_order_key             STRING          NOT NULL    COMMENT 'SHA-256 surrogate key (document + item)',

    -- Business Keys
    sales_document_number       STRING          NOT NULL    COMMENT 'Sales document number (leading zeros removed)',
    item_number                 STRING          NOT NULL    COMMENT 'Line item number (leading zeros removed)',

    -- Order Information
    order_date                  DATE                        COMMENT 'Sales order creation date',
    order_type                  STRING                      COMMENT 'Sales document type (ZOR=Standard, ZRE=Return, etc.)',
    sales_organization          STRING                      COMMENT 'Sales organization code',
    distribution_channel        STRING                      COMMENT 'Distribution channel code',
    division                    STRING                      COMMENT 'Product division code',

    -- Customer Information
    customer_number             STRING                      COMMENT 'Sold-to customer number',
    customer_po_number          STRING                      COMMENT 'Customer purchase order reference',
    customer_po_date            DATE                        COMMENT 'Customer PO date',

    -- Product Information
    material_number             STRING                      COMMENT 'Material/product number',
    material_group              STRING                      COMMENT 'Material group classification',
    item_description            STRING                      COMMENT 'Product short description',

    -- Quantity and Value
    order_quantity              DECIMAL(18, 3)              COMMENT 'Ordered quantity in sales unit',
    sales_unit                  STRING                      COMMENT 'Unit of measure for sales',
    net_value_item              DECIMAL(18, 2)              COMMENT 'Net value at line item level',
    net_value_header            DECIMAL(18, 2)              COMMENT 'Net value at header level',
    currency                    STRING                      COMMENT 'Document currency (ISO 4217)',

    -- Logistics
    plant                       STRING                      COMMENT 'Delivering plant code',
    storage_location            STRING                      COMMENT 'Storage location code',
    requested_delivery_date     DATE                        COMMENT 'Customer requested delivery date',

    -- Status and Blocks
    delivery_block              STRING                      COMMENT 'Delivery block code (null = not blocked)',
    billing_block               STRING                      COMMENT 'Billing block code (null = not blocked)',
    rejection_reason            STRING                      COMMENT 'Item rejection reason code',
    rejection_status            STRING                      COMMENT 'Header-level rejection status',
    is_rejected                 BOOLEAN                     COMMENT 'True if line item has been rejected',

    -- Audit
    created_by                  STRING                      COMMENT 'User who created the sales order',
    last_changed_date           DATE                        COMMENT 'Last modification date in SAP',

    -- SCD Type 2 Columns
    _effective_from             TIMESTAMP       NOT NULL    COMMENT 'Row effective start timestamp (UTC)',
    _effective_to               TIMESTAMP                   COMMENT 'Row effective end timestamp (UTC). NULL = current version',
    _is_current                 BOOLEAN         NOT NULL    COMMENT 'True if this is the current active version',

    -- Silver Lineage Metadata
    _silver_processed_timestamp TIMESTAMP       NOT NULL    COMMENT 'When this row was processed into silver',
    _silver_pipeline_run_id     STRING          NOT NULL    COMMENT 'Pipeline run that produced this row',
    _silver_row_hash            STRING          NOT NULL    COMMENT 'SHA-256 hash of business columns for change detection',
    _bronze_batch_id            STRING                      COMMENT 'Source bronze batch ID for traceability'
)
USING DELTA
COMMENT 'Cleaned and conformed sales orders with SCD Type 2 history. Grain: document + item + version.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'delta.logRetentionDuration' = 'interval 90 days',
    'delta.deletedFileRetentionDuration' = 'interval 14 days',
    'delta.columnMapping.mode' = 'name',
    'quality' = 'silver'
);

-- Optimize for common query patterns
-- OPTIMIZE lh_silver.cleaned_sales_orders ZORDER BY (sales_document_number, order_date);


-- ---------------------------------------------------------------------------
-- cleaned_inventory: Cleaned inventory snapshots with proper types
-- Source: lh_bronze.raw_inventory
-- Grain: One row per material + plant + storage location + snapshot date
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_silver.cleaned_inventory (
    -- Surrogate Key
    inventory_key               STRING          NOT NULL    COMMENT 'SHA-256 surrogate key',

    -- Business Keys
    material_number             STRING          NOT NULL    COMMENT 'Material number (cleaned)',
    plant                       STRING          NOT NULL    COMMENT 'Plant code',
    storage_location            STRING          NOT NULL    COMMENT 'Storage location code',
    snapshot_date               DATE            NOT NULL    COMMENT 'Date of this inventory snapshot',

    -- Stock Quantities (all in base unit of measure)
    unrestricted_stock          DECIMAL(18, 3)              COMMENT 'Unrestricted use / available stock',
    transfer_stock              DECIMAL(18, 3)              COMMENT 'Stock in transfer between locations',
    quality_inspection_stock    DECIMAL(18, 3)              COMMENT 'Stock in quality inspection',
    restricted_stock            DECIMAL(18, 3)              COMMENT 'Restricted-use stock',
    blocked_stock               DECIMAL(18, 3)              COMMENT 'Blocked stock (defective, holds)',
    returns_stock               DECIMAL(18, 3)              COMMENT 'Customer returns stock',

    -- Derived Measures
    total_stock                 DECIMAL(18, 3)              COMMENT 'Sum of all stock categories',
    available_stock             DECIMAL(18, 3)              COMMENT 'Unrestricted + transfer stock',

    -- SCD Type 2
    _effective_from             TIMESTAMP       NOT NULL,
    _effective_to               TIMESTAMP,
    _is_current                 BOOLEAN         NOT NULL,

    -- Lineage
    _silver_processed_timestamp TIMESTAMP       NOT NULL,
    _silver_pipeline_run_id     STRING          NOT NULL,
    _silver_row_hash            STRING          NOT NULL,
    _bronze_batch_id            STRING
)
USING DELTA
COMMENT 'Cleaned inventory stock levels. Grain: material + plant + storage location + snapshot date.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'silver'
);


-- ---------------------------------------------------------------------------
-- cleaned_customers: Conformed customer master data
-- Source: lh_bronze.raw_customers (CRM) cross-referenced with SAP KUNNR
-- Grain: One row per customer + effective version (SCD2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_silver.cleaned_customers (
    -- Surrogate Key
    customer_key                STRING          NOT NULL    COMMENT 'SHA-256 surrogate key',

    -- Business Keys
    crm_account_id              STRING          NOT NULL    COMMENT 'CRM Account ID (GUID)',
    customer_number             STRING                      COMMENT 'SAP Customer Number (cross-referenced)',
    account_number              STRING                      COMMENT 'CRM Account Number',

    -- Customer Details
    company_name                STRING                      COMMENT 'Company / Account name',
    industry_code               STRING                      COMMENT 'Industry classification code',
    industry_name               STRING                      COMMENT 'Industry name (looked up from code)',
    customer_type               STRING                      COMMENT 'Customer type: Prospect, Customer, Former',
    annual_revenue              DECIMAL(18, 2)              COMMENT 'Annual revenue in local currency',
    employee_count              INT                         COMMENT 'Number of employees',

    -- Address (standardized)
    address_line_1              STRING                      COMMENT 'Street address line 1',
    address_line_2              STRING                      COMMENT 'Street address line 2',
    city                        STRING                      COMMENT 'City',
    state_province              STRING                      COMMENT 'State or province',
    postal_code                 STRING                      COMMENT 'Postal / ZIP code',
    country                     STRING                      COMMENT 'Country (ISO 3166-1 alpha-2)',

    -- Contact
    primary_phone               STRING                      COMMENT 'Primary phone number (normalized)',
    primary_email               STRING                      COMMENT 'Primary email address (lowercased)',

    -- CRM Status
    is_active                   BOOLEAN                     COMMENT 'True if CRM status is Active',
    crm_created_date            TIMESTAMP                   COMMENT 'Record creation date in CRM',
    crm_modified_date           TIMESTAMP                   COMMENT 'Last modified date in CRM',

    -- Sales Org Mapping
    sales_organization          STRING                      COMMENT 'Primary sales organization',
    distribution_channel        STRING                      COMMENT 'Primary distribution channel',

    -- SCD Type 2
    _effective_from             TIMESTAMP       NOT NULL,
    _effective_to               TIMESTAMP,
    _is_current                 BOOLEAN         NOT NULL,

    -- Lineage
    _silver_processed_timestamp TIMESTAMP       NOT NULL,
    _silver_pipeline_run_id     STRING          NOT NULL,
    _silver_row_hash            STRING          NOT NULL,
    _bronze_batch_id            STRING
)
USING DELTA
COMMENT 'Cleaned customer master data merged from CRM and SAP. SCD Type 2.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact' = 'true',
    'quality' = 'silver'
);


-- ---------------------------------------------------------------------------
-- Data Quality Results (shared across all silver tables)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lh_silver.data_quality_results (
    table_name                  STRING          NOT NULL    COMMENT 'Table that was checked',
    check_name                  STRING          NOT NULL    COMMENT 'Name of the DQ check (not_null, unique, etc.)',
    column_name                 STRING                      COMMENT 'Column that was checked',
    severity                    STRING          NOT NULL    COMMENT 'Check severity: critical, warning, info',
    passed                      BOOLEAN         NOT NULL    COMMENT 'Whether the check passed',
    message                     STRING                      COMMENT 'Human-readable check result',
    violation_rate              DOUBLE                      COMMENT 'Rate of violations (0.0 to 1.0)',
    run_id                      STRING          NOT NULL    COMMENT 'Pipeline run ID',
    check_timestamp             TIMESTAMP       NOT NULL    COMMENT 'When the check was executed'
)
USING DELTA
COMMENT 'Data quality check results for silver layer tables.'
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'quality' = 'silver'
);
