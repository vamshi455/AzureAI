# Databricks/Fabric Notebook: Bronze Layer - ERP/SAP Data Ingestion
# Purpose: Ingest raw ERP data (sales orders, inventory, BOMs, production orders)
#          into bronze delta tables with schema validation, error handling, and audit logging.
# Schedule: Runs every 15 minutes for incremental loads; daily for full loads.
# Layer: Bronze (raw, append-only, immutable landing zone)

# COMMAND ----------

# MAGIC %md
# MAGIC # ERP/SAP Data Ingestion - Bronze Layer
# MAGIC This notebook ingests raw ERP data into the bronze lakehouse.
# MAGIC - **Source**: SAP S/4HANA via OData / RFC connectors
# MAGIC - **Target**: Bronze Delta tables (append-only)
# MAGIC - **Pattern**: CDC with watermark-based incremental extraction

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    IntegerType,
    DecimalType,
    TimestampType,
    DateType,
    DoubleType,
    LongType,
    BooleanType,
)
from pyspark.sql.utils import AnalysisException
from delta.tables import DeltaTable
from datetime import datetime, timezone
from typing import Optional
import json
import logging
import traceback

# COMMAND ----------

# -- Configuration Parameters (set via pipeline or widget) --

# In Microsoft Fabric, these would be set as notebook parameters from the pipeline
try:
    LAKEHOUSE_NAME = spark.conf.get("spark.databricks.lakehouse.name", "lh_bronze")
    LOAD_TYPE = spark.conf.get("spark.custom.load_type", "incremental")  # full | incremental
    WATERMARK_VALUE = spark.conf.get("spark.custom.watermark", "1900-01-01T00:00:00Z")
    PIPELINE_RUN_ID = spark.conf.get("spark.custom.pipeline_run_id", "manual_run")
    ENVIRONMENT = spark.conf.get("spark.custom.environment", "dev")
except Exception:
    LAKEHOUSE_NAME = "lh_bronze"
    LOAD_TYPE = "incremental"
    WATERMARK_VALUE = "1900-01-01T00:00:00Z"
    PIPELINE_RUN_ID = "manual_run"
    ENVIRONMENT = "dev"

INGESTION_TIMESTAMP = datetime.now(timezone.utc)
BATCH_ID = f"erp_{INGESTION_TIMESTAMP.strftime('%Y%m%d_%H%M%S')}"

# COMMAND ----------

# -- Logging Setup --

class IngestionLogger:
    """Structured logging for ERP data ingestion with audit trail persistence."""

    def __init__(self, spark: SparkSession, lakehouse: str, batch_id: str):
        self.spark = spark
        self.lakehouse = lakehouse
        self.batch_id = batch_id
        self.log_entries: list[dict] = []
        self.logger = logging.getLogger("erp_ingestion")
        self.logger.setLevel(logging.INFO)

    def log(
        self,
        level: str,
        source_table: str,
        target_table: str,
        message: str,
        rows_read: int = 0,
        rows_written: int = 0,
        error_detail: Optional[str] = None,
    ) -> None:
        """Record a structured log entry."""
        entry = {
            "batch_id": self.batch_id,
            "pipeline_run_id": PIPELINE_RUN_ID,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "source_system": "ERP_SAP",
            "source_table": source_table,
            "target_table": target_table,
            "message": message,
            "rows_read": rows_read,
            "rows_written": rows_written,
            "error_detail": error_detail,
            "environment": ENVIRONMENT,
        }
        self.log_entries.append(entry)
        log_msg = f"[{level}] {source_table} -> {target_table}: {message}"
        if level == "ERROR":
            self.logger.error(log_msg)
        elif level == "WARN":
            self.logger.warning(log_msg)
        else:
            self.logger.info(log_msg)

    def persist_logs(self) -> None:
        """Write accumulated log entries to the audit log delta table."""
        if not self.log_entries:
            return
        log_df = self.spark.createDataFrame(self.log_entries)
        log_df.write.format("delta").mode("append").saveAsTable(
            f"{self.lakehouse}.bronze_ingestion_audit_log"
        )
        self.logger.info(f"Persisted {len(self.log_entries)} audit log entries.")


audit_logger = IngestionLogger(spark, LAKEHOUSE_NAME, BATCH_ID)

# COMMAND ----------

# -- Schema Definitions for ERP Source Tables --

ERP_SCHEMAS: dict[str, StructType] = {
    "VBAK": StructType([  # Sales Order Header
        StructField("VBELN", StringType(), False),       # Sales Document Number
        StructField("ERDAT", StringType(), True),        # Created Date
        StructField("ERZET", StringType(), True),        # Created Time
        StructField("ERNAM", StringType(), True),        # Created By
        StructField("AUART", StringType(), True),        # Sales Document Type
        StructField("VKORG", StringType(), True),        # Sales Organization
        StructField("VTWEG", StringType(), True),        # Distribution Channel
        StructField("SPART", StringType(), True),        # Division
        StructField("KUNNR", StringType(), True),        # Sold-to Party
        StructField("BSTNK", StringType(), True),        # Customer PO Number
        StructField("BSTDK", StringType(), True),        # Customer PO Date
        StructField("NETWR", StringType(), True),        # Net Value
        StructField("WAERK", StringType(), True),        # Currency
        StructField("VDATU", StringType(), True),        # Requested Delivery Date
        StructField("LIFSK", StringType(), True),        # Delivery Block
        StructField("FAKSK", StringType(), True),        # Billing Block
        StructField("ABSTK", StringType(), True),        # Rejection Status
        StructField("AEDAT", StringType(), True),        # Last Changed Date
    ]),
    "VBAP": StructType([  # Sales Order Item
        StructField("VBELN", StringType(), False),       # Sales Document Number
        StructField("POSNR", StringType(), False),       # Item Number
        StructField("MATNR", StringType(), True),        # Material Number
        StructField("MATKL", StringType(), True),        # Material Group
        StructField("ARKTX", StringType(), True),        # Item Description
        StructField("KWMENG", StringType(), True),       # Order Quantity
        StructField("VRKME", StringType(), True),        # Sales Unit
        StructField("NETWR", StringType(), True),        # Net Value
        StructField("WAERK", StringType(), True),        # Currency
        StructField("WERKS", StringType(), True),        # Plant
        StructField("LGORT", StringType(), True),        # Storage Location
        StructField("ABGRU", StringType(), True),        # Rejection Reason
        StructField("AEDAT", StringType(), True),        # Last Changed Date
    ]),
    "MARD": StructType([  # Inventory (Storage Location Level)
        StructField("MATNR", StringType(), False),       # Material Number
        StructField("WERKS", StringType(), False),       # Plant
        StructField("LGORT", StringType(), False),       # Storage Location
        StructField("LABST", StringType(), True),        # Unrestricted Stock
        StructField("UMLME", StringType(), True),        # Stock in Transfer
        StructField("INSME", StringType(), True),        # Quality Inspection Stock
        StructField("EINME", StringType(), True),        # Restricted Stock
        StructField("SPEME", StringType(), True),        # Blocked Stock
        StructField("RETME", StringType(), True),        # Returns Stock
        StructField("AEDAT", StringType(), True),        # Last Changed Date
    ]),
    "AFKO": StructType([  # Production Order Header
        StructField("AUFNR", StringType(), False),       # Order Number
        StructField("AUFART", StringType(), True),       # Order Type
        StructField("PLNBEZ", StringType(), True),       # Material Number
        StructField("GAMNG", StringType(), True),        # Total Order Quantity
        StructField("GMEIN", StringType(), True),        # Unit of Measure
        StructField("GSTRP", StringType(), True),        # Scheduled Start Date
        StructField("GLTRP", StringType(), True),        # Scheduled Finish Date
        StructField("FTRMS", StringType(), True),        # Scheduled Release Date
        StructField("DESSION", StringType(), True),      # System Status
        StructField("AEDAT", StringType(), True),        # Last Changed Date
    ]),
}

# Mapping of SAP source tables to bronze target tables
TABLE_MAPPING: dict[str, str] = {
    "VBAK": "raw_sales_orders_header",
    "VBAP": "raw_sales_orders_item",
    "MARD": "raw_inventory",
    "AFKO": "raw_production_orders",
}

# COMMAND ----------

# -- Schema Validation --

def validate_schema(
    df: DataFrame, expected_schema: StructType, source_table: str
) -> tuple[DataFrame, DataFrame]:
    """
    Validate incoming dataframe against expected schema.

    Returns a tuple of (valid_records, rejected_records).
    Records are rejected if required (non-nullable) fields are null.
    """
    required_fields = [
        field.name for field in expected_schema.fields if not field.nullable
    ]

    # Build rejection condition: any required field is null
    if required_fields:
        rejection_condition = F.lit(False)
        for field_name in required_fields:
            if field_name in df.columns:
                rejection_condition = rejection_condition | F.col(field_name).isNull()

        valid_df = df.filter(~rejection_condition)
        rejected_df = df.filter(rejection_condition).withColumn(
            "_rejection_reason",
            F.lit(f"Null value in required field(s): {', '.join(required_fields)}"),
        )
    else:
        valid_df = df
        rejected_df = spark.createDataFrame([], df.schema)

    # Validate no unexpected columns (schema drift detection)
    expected_columns = {field.name for field in expected_schema.fields}
    actual_columns = set(df.columns)
    extra_columns = actual_columns - expected_columns
    missing_columns = expected_columns - actual_columns

    if extra_columns:
        audit_logger.log(
            "WARN",
            source_table,
            TABLE_MAPPING.get(source_table, "unknown"),
            f"Schema drift detected - extra columns: {extra_columns}",
        )

    if missing_columns:
        audit_logger.log(
            "WARN",
            source_table,
            TABLE_MAPPING.get(source_table, "unknown"),
            f"Schema drift detected - missing columns: {missing_columns}",
        )
        # Add missing columns as null to maintain schema consistency
        for col_name in missing_columns:
            valid_df = valid_df.withColumn(col_name, F.lit(None).cast(StringType()))

    return valid_df, rejected_df


# COMMAND ----------

# -- Metadata Enrichment --

def add_bronze_metadata(df: DataFrame, source_table: str) -> DataFrame:
    """
    Add standard bronze layer metadata columns to the dataframe.

    These columns provide lineage and traceability for all records
    in the bronze layer.
    """
    return (
        df.withColumn("_bronze_ingestion_timestamp", F.lit(INGESTION_TIMESTAMP))
        .withColumn("_bronze_batch_id", F.lit(BATCH_ID))
        .withColumn("_bronze_pipeline_run_id", F.lit(PIPELINE_RUN_ID))
        .withColumn("_bronze_source_system", F.lit("ERP_SAP"))
        .withColumn("_bronze_source_table", F.lit(source_table))
        .withColumn("_bronze_load_type", F.lit(LOAD_TYPE))
        .withColumn(
            "_bronze_file_path",
            F.input_file_name() if "_bronze_file_path" not in df.columns else F.col("_bronze_file_path"),
        )
        .withColumn("_bronze_row_hash", F.sha2(F.concat_ws("||", *df.columns), 256))
    )


# COMMAND ----------

# -- Core Ingestion Function --

def ingest_erp_table(
    source_table: str,
    target_table: str,
    schema: StructType,
    load_type: str = "incremental",
    watermark_column: str = "AEDAT",
    watermark_value: str = "19000101",
) -> dict:
    """
    Ingest a single ERP/SAP table into the bronze lakehouse.

    Args:
        source_table: SAP table name (e.g., VBAK, VBAP)
        target_table: Bronze delta table name (e.g., raw_sales_orders_header)
        schema: Expected PySpark schema for validation
        load_type: 'full' or 'incremental'
        watermark_column: Column used for incremental extraction
        watermark_value: Last extracted watermark value (YYYYMMDD)

    Returns:
        Dictionary with ingestion statistics.
    """
    stats = {
        "source_table": source_table,
        "target_table": target_table,
        "rows_read": 0,
        "rows_written": 0,
        "rows_rejected": 0,
        "status": "FAILED",
    }

    try:
        audit_logger.log(
            "INFO",
            source_table,
            target_table,
            f"Starting {load_type} ingestion. Watermark: {watermark_value}",
        )

        # -- Step 1: Read from source --
        # In Fabric, data may arrive via the pipeline Copy activity into Files/
        # or via a direct connector. Here we read from the staged landing zone.
        landing_path = (
            f"Files/landing/erp/{source_table}/"
            f"{INGESTION_TIMESTAMP.strftime('%Y/%m/%d')}/"
        )

        try:
            raw_df = (
                spark.read.format("parquet")
                .schema(schema)
                .option("mergeSchema", "false")
                .option("pathGlobFilter", "*.parquet")
                .load(landing_path)
            )
        except AnalysisException as e:
            if "Path does not exist" in str(e):
                audit_logger.log(
                    "WARN",
                    source_table,
                    target_table,
                    f"No data files found at {landing_path}. Skipping.",
                )
                stats["status"] = "SKIPPED"
                return stats
            raise

        stats["rows_read"] = raw_df.count()
        audit_logger.log(
            "INFO",
            source_table,
            target_table,
            f"Read {stats['rows_read']} rows from landing zone.",
            rows_read=stats["rows_read"],
        )

        if stats["rows_read"] == 0:
            audit_logger.log(
                "INFO", source_table, target_table, "No new records to ingest."
            )
            stats["status"] = "SKIPPED"
            return stats

        # -- Step 2: Schema Validation --
        valid_df, rejected_df = validate_schema(raw_df, schema, source_table)
        stats["rows_rejected"] = rejected_df.count()

        if stats["rows_rejected"] > 0:
            audit_logger.log(
                "WARN",
                source_table,
                target_table,
                f"Rejected {stats['rows_rejected']} records due to schema validation.",
                rows_read=stats["rows_read"],
            )
            # Persist rejected records for investigation
            rejected_with_meta = add_bronze_metadata(rejected_df, source_table)
            rejected_with_meta.write.format("delta").mode("append").saveAsTable(
                f"{LAKEHOUSE_NAME}.{target_table}_rejected"
            )

        # -- Step 3: Deduplicate within batch --
        # Remove exact duplicates that may arise from retry/redelivery
        valid_df = valid_df.dropDuplicates()

        # -- Step 4: Add Bronze Metadata --
        enriched_df = add_bronze_metadata(valid_df, source_table)

        # -- Step 5: Write to Bronze Delta Table --
        # Bronze is always append-only to preserve the raw history
        enriched_df.write.format("delta").mode("append").option(
            "mergeSchema", "true"
        ).partitionBy("_bronze_source_table").saveAsTable(
            f"{LAKEHOUSE_NAME}.{target_table}"
        )

        stats["rows_written"] = valid_df.count()
        stats["status"] = "SUCCEEDED"

        audit_logger.log(
            "INFO",
            source_table,
            target_table,
            f"Successfully ingested {stats['rows_written']} rows.",
            rows_read=stats["rows_read"],
            rows_written=stats["rows_written"],
        )

        # -- Step 6: Update Watermark --
        if load_type == "incremental" and watermark_column in valid_df.columns:
            new_watermark = valid_df.agg(F.max(watermark_column)).collect()[0][0]
            if new_watermark:
                watermark_df = spark.createDataFrame(
                    [
                        {
                            "source_table": source_table,
                            "target_table": target_table,
                            "watermark_column": watermark_column,
                            "watermark_value": str(new_watermark),
                            "updated_at": INGESTION_TIMESTAMP.isoformat(),
                        }
                    ]
                )
                watermark_df.write.format("delta").mode("append").saveAsTable(
                    f"{LAKEHOUSE_NAME}.ingestion_watermarks"
                )
                audit_logger.log(
                    "INFO",
                    source_table,
                    target_table,
                    f"Updated watermark to {new_watermark}.",
                )

    except Exception as e:
        error_msg = traceback.format_exc()
        audit_logger.log(
            "ERROR",
            source_table,
            target_table,
            f"Ingestion failed: {str(e)}",
            error_detail=error_msg,
        )
        stats["status"] = "FAILED"
        raise

    return stats


# COMMAND ----------

# -- Execute Ingestion for All ERP Tables --

print(f"=== ERP Bronze Ingestion Started ===")
print(f"Batch ID     : {BATCH_ID}")
print(f"Load Type    : {LOAD_TYPE}")
print(f"Watermark    : {WATERMARK_VALUE}")
print(f"Pipeline Run : {PIPELINE_RUN_ID}")
print(f"Environment  : {ENVIRONMENT}")
print(f"Timestamp    : {INGESTION_TIMESTAMP.isoformat()}")
print(f"===================================")

ingestion_results: list[dict] = []

for sap_table, bronze_table in TABLE_MAPPING.items():
    try:
        result = ingest_erp_table(
            source_table=sap_table,
            target_table=bronze_table,
            schema=ERP_SCHEMAS[sap_table],
            load_type=LOAD_TYPE,
            watermark_column="AEDAT",
            watermark_value=WATERMARK_VALUE.replace("-", "")[:8],
        )
        ingestion_results.append(result)
    except Exception as e:
        ingestion_results.append(
            {
                "source_table": sap_table,
                "target_table": bronze_table,
                "rows_read": 0,
                "rows_written": 0,
                "rows_rejected": 0,
                "status": "FAILED",
            }
        )
        print(f"FAILED: {sap_table} -> {bronze_table}: {str(e)}")

# COMMAND ----------

# -- Persist Audit Logs and Print Summary --

audit_logger.persist_logs()

# Print summary report
print("\n=== Ingestion Summary ===")
print(f"{'Source Table':<20} {'Target Table':<30} {'Read':>8} {'Written':>8} {'Rejected':>8} {'Status':<10}")
print("-" * 100)

total_read = 0
total_written = 0
total_rejected = 0
all_succeeded = True

for result in ingestion_results:
    total_read += result["rows_read"]
    total_written += result["rows_written"]
    total_rejected += result["rows_rejected"]
    if result["status"] == "FAILED":
        all_succeeded = False

    print(
        f"{result['source_table']:<20} "
        f"{result['target_table']:<30} "
        f"{result['rows_read']:>8} "
        f"{result['rows_written']:>8} "
        f"{result['rows_rejected']:>8} "
        f"{result['status']:<10}"
    )

print("-" * 100)
print(f"{'TOTAL':<20} {'':<30} {total_read:>8} {total_written:>8} {total_rejected:>8}")
print(f"\nOverall Status: {'SUCCEEDED' if all_succeeded else 'COMPLETED WITH ERRORS'}")

# Raise an error if any table failed so the pipeline detects the failure
if not all_succeeded:
    failed_tables = [r["source_table"] for r in ingestion_results if r["status"] == "FAILED"]
    raise RuntimeError(
        f"ERP ingestion failed for tables: {', '.join(failed_tables)}. "
        "Check bronze_ingestion_audit_log for details."
    )

# COMMAND ----------

# -- Optimize Bronze Tables (run periodically, not every micro-batch) --

if LOAD_TYPE == "full":
    print("\nRunning OPTIMIZE on bronze tables...")
    for bronze_table in TABLE_MAPPING.values():
        try:
            spark.sql(f"OPTIMIZE {LAKEHOUSE_NAME}.{bronze_table}")
            print(f"  Optimized: {bronze_table}")
        except Exception as e:
            print(f"  Optimize skipped for {bronze_table}: {str(e)}")

print("\n=== ERP Bronze Ingestion Complete ===")
