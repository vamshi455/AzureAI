# Databricks/Fabric Notebook: Silver Layer - Sales Orders Transformation
# Purpose: Transform raw bronze sales order data into cleaned, deduplicated,
#          schema-enforced silver delta tables with SCD Type 2 history tracking.
# Schedule: Runs after bronze ingestion pipeline completes (event-driven).
# Layer: Silver (cleaned, conformed, business-validated)

# COMMAND ----------

# MAGIC %md
# MAGIC # Sales Orders Transformation - Bronze to Silver
# MAGIC This notebook transforms raw ERP sales order data from bronze into the silver layer.
# MAGIC - **Source**: `lh_bronze.raw_sales_orders_header`, `lh_bronze.raw_sales_orders_item`
# MAGIC - **Target**: `lh_silver.cleaned_sales_orders`
# MAGIC - **Transformations**: Deduplication, type casting, SCD2, data quality checks

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame, Window
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
    BooleanType,
)
from delta.tables import DeltaTable
from datetime import datetime, timezone
from typing import Optional
import logging

# COMMAND ----------

# -- Configuration --

try:
    BRONZE_LAKEHOUSE = spark.conf.get("spark.custom.bronze_lakehouse", "lh_bronze")
    SILVER_LAKEHOUSE = spark.conf.get("spark.custom.silver_lakehouse", "lh_silver")
    PIPELINE_RUN_ID = spark.conf.get("spark.custom.pipeline_run_id", "manual_run")
    PROCESSING_DATE = spark.conf.get(
        "spark.custom.processing_date",
        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
except Exception:
    BRONZE_LAKEHOUSE = "lh_bronze"
    SILVER_LAKEHOUSE = "lh_silver"
    PIPELINE_RUN_ID = "manual_run"
    PROCESSING_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

PROCESSING_TIMESTAMP = datetime.now(timezone.utc)
SCD2_EFFECTIVE_DATE = PROCESSING_TIMESTAMP

# Data quality thresholds - fail the pipeline if breached
DQ_THRESHOLDS = {
    "null_rate_max": 0.05,         # Max 5% null rate for critical fields
    "duplicate_rate_max": 0.01,     # Max 1% duplicate rate after dedup
    "value_range_violation_max": 0.02,  # Max 2% out-of-range values
    "referential_integrity_min": 0.95,  # Min 95% referential integrity
}

logger = logging.getLogger("silver_sales_orders")
logger.setLevel(logging.INFO)

# COMMAND ----------

# -- Silver Schema Definition --

SILVER_SALES_ORDER_SCHEMA = StructType([
    StructField("sales_order_key", StringType(), False),       # Surrogate key
    StructField("sales_document_number", StringType(), False), # VBELN
    StructField("item_number", StringType(), False),           # POSNR
    StructField("order_date", DateType(), True),
    StructField("order_type", StringType(), True),
    StructField("sales_organization", StringType(), True),
    StructField("distribution_channel", StringType(), True),
    StructField("division", StringType(), True),
    StructField("customer_number", StringType(), True),
    StructField("customer_po_number", StringType(), True),
    StructField("customer_po_date", DateType(), True),
    StructField("material_number", StringType(), True),
    StructField("material_group", StringType(), True),
    StructField("item_description", StringType(), True),
    StructField("order_quantity", DecimalType(18, 3), True),
    StructField("sales_unit", StringType(), True),
    StructField("net_value_item", DecimalType(18, 2), True),
    StructField("net_value_header", DecimalType(18, 2), True),
    StructField("currency", StringType(), True),
    StructField("plant", StringType(), True),
    StructField("storage_location", StringType(), True),
    StructField("requested_delivery_date", DateType(), True),
    StructField("delivery_block", StringType(), True),
    StructField("billing_block", StringType(), True),
    StructField("rejection_reason", StringType(), True),
    StructField("rejection_status", StringType(), True),
    StructField("is_rejected", BooleanType(), True),
    StructField("created_by", StringType(), True),
    StructField("last_changed_date", DateType(), True),
    # SCD2 columns
    StructField("_effective_from", TimestampType(), False),
    StructField("_effective_to", TimestampType(), True),
    StructField("_is_current", BooleanType(), False),
    # Lineage columns
    StructField("_silver_processed_timestamp", TimestampType(), False),
    StructField("_silver_pipeline_run_id", StringType(), False),
    StructField("_silver_row_hash", StringType(), False),
    StructField("_bronze_batch_id", StringType(), True),
])

# COMMAND ----------

# -- Data Quality Framework --

class DataQualityChecker:
    """
    Validates silver-layer data quality rules and produces a quality report.
    Raises an exception if critical thresholds are breached.
    """

    def __init__(self, df: DataFrame, table_name: str, thresholds: dict):
        self.df = df
        self.table_name = table_name
        self.thresholds = thresholds
        self.results: list[dict] = []
        self.total_rows = df.count()

    def check_not_null(self, columns: list[str], severity: str = "critical") -> "DataQualityChecker":
        """Verify specified columns have no null values beyond threshold."""
        for col_name in columns:
            if col_name not in self.df.columns:
                self.results.append({
                    "check": "not_null",
                    "column": col_name,
                    "severity": severity,
                    "passed": False,
                    "message": f"Column {col_name} does not exist.",
                    "violation_rate": 1.0,
                })
                continue

            null_count = self.df.filter(F.col(col_name).isNull()).count()
            null_rate = null_count / self.total_rows if self.total_rows > 0 else 0.0
            passed = null_rate <= self.thresholds["null_rate_max"]

            self.results.append({
                "check": "not_null",
                "column": col_name,
                "severity": severity,
                "passed": passed,
                "message": f"Null rate: {null_rate:.4f} ({null_count}/{self.total_rows})",
                "violation_rate": null_rate,
            })
        return self

    def check_unique(self, columns: list[str], severity: str = "critical") -> "DataQualityChecker":
        """Verify uniqueness of specified column combination."""
        col_expr = [F.col(c) for c in columns]
        total = self.df.count()
        distinct = self.df.select(*col_expr).distinct().count()
        dup_count = total - distinct
        dup_rate = dup_count / total if total > 0 else 0.0
        passed = dup_rate <= self.thresholds["duplicate_rate_max"]

        self.results.append({
            "check": "unique",
            "column": ", ".join(columns),
            "severity": severity,
            "passed": passed,
            "message": f"Duplicate rate: {dup_rate:.4f} ({dup_count}/{total})",
            "violation_rate": dup_rate,
        })
        return self

    def check_value_range(
        self,
        column: str,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        severity: str = "warning",
    ) -> "DataQualityChecker":
        """Verify column values fall within expected range."""
        violations = self.df.filter(F.col(column).isNotNull())
        if min_val is not None:
            violations = violations.filter(F.col(column) < min_val)
        if max_val is not None:
            violations = violations.filter(F.col(column) > max_val)

        violation_count = violations.count()
        violation_rate = violation_count / self.total_rows if self.total_rows > 0 else 0.0
        passed = violation_rate <= self.thresholds["value_range_violation_max"]

        self.results.append({
            "check": "value_range",
            "column": column,
            "severity": severity,
            "passed": passed,
            "message": f"Out-of-range rate: {violation_rate:.4f} ({violation_count}/{self.total_rows}). Range: [{min_val}, {max_val}]",
            "violation_rate": violation_rate,
        })
        return self

    def check_referential_integrity(
        self,
        column: str,
        reference_df: DataFrame,
        reference_column: str,
        severity: str = "warning",
    ) -> "DataQualityChecker":
        """Verify foreign key references exist in the reference table."""
        source_distinct = self.df.select(column).distinct()
        ref_distinct = reference_df.select(F.col(reference_column).alias(column)).distinct()
        orphans = source_distinct.subtract(ref_distinct)
        orphan_count = orphans.count()
        total_distinct = source_distinct.count()
        integrity_rate = 1.0 - (orphan_count / total_distinct if total_distinct > 0 else 0.0)
        passed = integrity_rate >= self.thresholds["referential_integrity_min"]

        self.results.append({
            "check": "referential_integrity",
            "column": column,
            "severity": severity,
            "passed": passed,
            "message": f"Integrity rate: {integrity_rate:.4f}. Orphans: {orphan_count}/{total_distinct}",
            "violation_rate": 1.0 - integrity_rate,
        })
        return self

    def check_date_validity(
        self, column: str, min_date: str = "2000-01-01", max_date: str = "2030-12-31", severity: str = "warning"
    ) -> "DataQualityChecker":
        """Verify date column values are within a reasonable range."""
        violations = self.df.filter(
            F.col(column).isNotNull()
            & (
                (F.col(column) < F.lit(min_date))
                | (F.col(column) > F.lit(max_date))
            )
        )
        violation_count = violations.count()
        non_null_count = self.df.filter(F.col(column).isNotNull()).count()
        violation_rate = violation_count / non_null_count if non_null_count > 0 else 0.0
        passed = violation_rate <= self.thresholds["value_range_violation_max"]

        self.results.append({
            "check": "date_validity",
            "column": column,
            "severity": severity,
            "passed": passed,
            "message": f"Invalid date rate: {violation_rate:.4f} ({violation_count}/{non_null_count}). Range: [{min_date}, {max_date}]",
            "violation_rate": violation_rate,
        })
        return self

    def run(self) -> tuple[bool, list[dict]]:
        """
        Execute all checks and return (all_critical_passed, results).
        Raises RuntimeError if any critical check fails.
        """
        critical_failures = [
            r for r in self.results if not r["passed"] and r["severity"] == "critical"
        ]
        warnings = [
            r for r in self.results if not r["passed"] and r["severity"] == "warning"
        ]

        # Print report
        print(f"\n=== Data Quality Report: {self.table_name} ===")
        print(f"Total Rows: {self.total_rows}")
        print(f"{'Check':<25} {'Column':<35} {'Severity':<10} {'Passed':<8} {'Details'}")
        print("-" * 130)
        for r in self.results:
            status = "PASS" if r["passed"] else "FAIL"
            print(f"{r['check']:<25} {r['column']:<35} {r['severity']:<10} {status:<8} {r['message']}")

        if warnings:
            print(f"\nWARNINGS: {len(warnings)} quality check(s) below threshold.")
        if critical_failures:
            print(f"\nCRITICAL FAILURES: {len(critical_failures)} check(s) failed.")

        return len(critical_failures) == 0, self.results


# COMMAND ----------

# -- Transformation Functions --

def parse_sap_date(col_name: str, output_col: Optional[str] = None) -> F.Column:
    """Convert SAP date string (YYYYMMDD) to DateType, handling '00000000' as null."""
    target = output_col or col_name
    return (
        F.when(
            (F.col(col_name).isNull())
            | (F.col(col_name) == "00000000")
            | (F.col(col_name) == ""),
            F.lit(None).cast(DateType()),
        )
        .otherwise(F.to_date(F.col(col_name), "yyyyMMdd"))
        .alias(target)
    )


def clean_sap_number(col_name: str, output_col: Optional[str] = None) -> F.Column:
    """Strip leading zeros from SAP number fields (e.g., '0000001234' -> '1234')."""
    target = output_col or col_name
    return F.regexp_replace(F.col(col_name), r"^0+", "").alias(target)


def transform_bronze_to_silver(
    header_df: DataFrame, item_df: DataFrame
) -> DataFrame:
    """
    Join header and item data, apply business transformations, and produce
    the silver sales order dataset.
    """
    # -- Step 1: Deduplicate bronze data (keep latest by ingestion timestamp) --
    header_window = Window.partitionBy("VBELN").orderBy(
        F.col("_bronze_ingestion_timestamp").desc()
    )
    deduped_header = (
        header_df.withColumn("_row_num", F.row_number().over(header_window))
        .filter(F.col("_row_num") == 1)
        .drop("_row_num")
    )

    item_window = Window.partitionBy("VBELN", "POSNR").orderBy(
        F.col("_bronze_ingestion_timestamp").desc()
    )
    deduped_items = (
        item_df.withColumn("_row_num", F.row_number().over(item_window))
        .filter(F.col("_row_num") == 1)
        .drop("_row_num")
    )

    # -- Step 2: Join Header and Item --
    joined_df = deduped_items.alias("i").join(
        deduped_header.alias("h"),
        F.col("i.VBELN") == F.col("h.VBELN"),
        "inner",
    )

    # -- Step 3: Apply Transformations --
    transformed_df = joined_df.select(
        # Surrogate key: composite of document + item
        F.sha2(
            F.concat_ws("||", F.col("i.VBELN"), F.col("i.POSNR")), 256
        ).alias("sales_order_key"),
        # Business keys
        clean_sap_number("i.VBELN", "sales_document_number"),
        clean_sap_number("i.POSNR", "item_number"),
        # Dates
        parse_sap_date("h.ERDAT", "order_date"),
        # Header fields
        F.trim(F.col("h.AUART")).alias("order_type"),
        F.trim(F.col("h.VKORG")).alias("sales_organization"),
        F.trim(F.col("h.VTWEG")).alias("distribution_channel"),
        F.trim(F.col("h.SPART")).alias("division"),
        clean_sap_number("h.KUNNR", "customer_number"),
        F.trim(F.col("h.BSTNK")).alias("customer_po_number"),
        parse_sap_date("h.BSTDK", "customer_po_date"),
        # Item fields
        clean_sap_number("i.MATNR", "material_number"),
        F.trim(F.col("i.MATKL")).alias("material_group"),
        F.trim(F.col("i.ARKTX")).alias("item_description"),
        F.col("i.KWMENG").cast(DecimalType(18, 3)).alias("order_quantity"),
        F.trim(F.col("i.VRKME")).alias("sales_unit"),
        F.col("i.NETWR").cast(DecimalType(18, 2)).alias("net_value_item"),
        F.col("h.NETWR").cast(DecimalType(18, 2)).alias("net_value_header"),
        F.trim(F.coalesce(F.col("i.WAERK"), F.col("h.WAERK"))).alias("currency"),
        F.trim(F.col("i.WERKS")).alias("plant"),
        F.trim(F.col("i.LGORT")).alias("storage_location"),
        parse_sap_date("h.VDATU", "requested_delivery_date"),
        F.trim(F.col("h.LIFSK")).alias("delivery_block"),
        F.trim(F.col("h.FAKSK")).alias("billing_block"),
        F.trim(F.col("i.ABGRU")).alias("rejection_reason"),
        F.trim(F.col("h.ABSTK")).alias("rejection_status"),
        # Derived fields
        F.when(
            (F.col("i.ABGRU").isNotNull()) & (F.trim(F.col("i.ABGRU")) != ""),
            F.lit(True),
        )
        .otherwise(F.lit(False))
        .alias("is_rejected"),
        F.trim(F.col("h.ERNAM")).alias("created_by"),
        parse_sap_date(
            "i.AEDAT", "last_changed_date"
        ),
        # Bronze lineage
        F.col("i._bronze_batch_id").alias("_bronze_batch_id"),
    )

    # -- Step 4: Add Silver Metadata --
    silver_df = transformed_df.withColumn(
        "_silver_processed_timestamp", F.lit(PROCESSING_TIMESTAMP)
    ).withColumn(
        "_silver_pipeline_run_id", F.lit(PIPELINE_RUN_ID)
    ).withColumn(
        "_silver_row_hash",
        F.sha2(
            F.concat_ws(
                "||",
                F.col("sales_document_number"),
                F.col("item_number"),
                F.col("order_type"),
                F.col("customer_number"),
                F.col("material_number"),
                F.col("order_quantity").cast(StringType()),
                F.col("net_value_item").cast(StringType()),
                F.col("net_value_header").cast(StringType()),
                F.col("plant"),
                F.col("rejection_reason"),
                F.col("delivery_block"),
                F.col("billing_block"),
            ),
            256,
        ),
    )

    return silver_df


# COMMAND ----------

# -- SCD Type 2 Implementation --

def apply_scd_type_2(
    new_data: DataFrame,
    target_table: str,
    business_keys: list[str],
    hash_column: str = "_silver_row_hash",
) -> None:
    """
    Apply SCD Type 2 merge logic to maintain historical versions of records.

    - New records: Insert with _is_current=True
    - Changed records: Close existing row (set _effective_to, _is_current=False),
                       insert new version with _is_current=True
    - Unchanged records: Skip (no action)
    """
    full_table_name = f"{SILVER_LAKEHOUSE}.{target_table}"

    # Prepare new data with SCD2 columns
    new_with_scd = (
        new_data.withColumn("_effective_from", F.lit(SCD2_EFFECTIVE_DATE))
        .withColumn("_effective_to", F.lit(None).cast(TimestampType()))
        .withColumn("_is_current", F.lit(True))
    )

    # Check if target table exists
    try:
        target_dt = DeltaTable.forName(spark, full_table_name)
    except AnalysisException:
        # First load: write directly
        logger.info(f"Target table {full_table_name} does not exist. Creating with initial load.")
        new_with_scd.write.format("delta").mode("overwrite").saveAsTable(full_table_name)
        print(f"Created {full_table_name} with {new_with_scd.count()} initial records.")
        return

    # Build join condition on business keys
    join_condition = " AND ".join(
        [f"target.{key} = source.{key}" for key in business_keys]
    )

    # Identify changed records by comparing hash
    # Records where business key matches but hash differs = changed
    # Records with no match in target = new
    staged_updates = (
        new_with_scd.alias("source")
        .join(
            spark.read.table(full_table_name)
            .filter(F.col("_is_current") == True)
            .alias("target"),
            on=business_keys,
            how="left",
        )
        .select(
            "source.*",
            F.col(f"target.{hash_column}").alias("_existing_hash"),
        )
        .withColumn(
            "_merge_action",
            F.when(F.col("_existing_hash").isNull(), F.lit("INSERT"))  # New record
            .when(
                F.col("_existing_hash") != F.col(f"source.{hash_column}"),
                F.lit("UPDATE"),  # Changed record
            )
            .otherwise(F.lit("SKIP")),  # Unchanged
        )
    )

    inserts_df = staged_updates.filter(F.col("_merge_action").isin("INSERT", "UPDATE")).drop(
        "_existing_hash", "_merge_action"
    )
    updates_keys_df = staged_updates.filter(F.col("_merge_action") == "UPDATE").select(
        *business_keys
    )

    insert_count = inserts_df.count()
    update_count = updates_keys_df.count()
    skip_count = staged_updates.filter(F.col("_merge_action") == "SKIP").count()

    print(f"SCD2 Merge Plan: {insert_count} inserts, {update_count} updates, {skip_count} unchanged")

    if insert_count == 0 and update_count == 0:
        print("No changes detected. Skipping merge.")
        return

    # Step 1: Close existing records that have changed
    if update_count > 0:
        close_condition = " AND ".join(
            [f"target.{key} = updates.{key}" for key in business_keys]
        )
        updates_keys_df.createOrReplaceTempView("scd2_updates")

        spark.sql(f"""
            MERGE INTO {full_table_name} AS target
            USING scd2_updates AS updates
            ON {close_condition} AND target._is_current = true
            WHEN MATCHED THEN
                UPDATE SET
                    target._effective_to = '{SCD2_EFFECTIVE_DATE.isoformat()}',
                    target._is_current = false
        """)
        print(f"Closed {update_count} existing records.")

    # Step 2: Insert new and changed records
    if insert_count > 0:
        inserts_df.write.format("delta").mode("append").saveAsTable(full_table_name)
        print(f"Inserted {insert_count} new/updated records.")


# COMMAND ----------

# -- Main Execution --

print(f"=== Silver Sales Orders Transformation Started ===")
print(f"Processing Date : {PROCESSING_DATE}")
print(f"Pipeline Run    : {PIPELINE_RUN_ID}")
print(f"Bronze Source   : {BRONZE_LAKEHOUSE}")
print(f"Silver Target   : {SILVER_LAKEHOUSE}")
print(f"================================================")

# Step 1: Read bronze data
print("\n--- Step 1: Reading bronze data ---")
try:
    bronze_header = spark.read.table(f"{BRONZE_LAKEHOUSE}.raw_sales_orders_header")
    bronze_items = spark.read.table(f"{BRONZE_LAKEHOUSE}.raw_sales_orders_item")

    header_count = bronze_header.count()
    item_count = bronze_items.count()
    print(f"Bronze header records: {header_count}")
    print(f"Bronze item records  : {item_count}")
except AnalysisException as e:
    raise RuntimeError(f"Failed to read bronze tables: {str(e)}")

# Step 2: Transform
print("\n--- Step 2: Applying transformations ---")
silver_df = transform_bronze_to_silver(bronze_header, bronze_items)
silver_count = silver_df.count()
print(f"Transformed records: {silver_count}")

# Step 3: Data Quality Checks
print("\n--- Step 3: Running data quality checks ---")
dq_checker = DataQualityChecker(silver_df, "cleaned_sales_orders", DQ_THRESHOLDS)
dq_passed, dq_results = (
    dq_checker
    .check_not_null(
        ["sales_document_number", "item_number", "sales_order_key"],
        severity="critical",
    )
    .check_not_null(
        ["order_date", "customer_number", "material_number"],
        severity="warning",
    )
    .check_unique(
        ["sales_document_number", "item_number"],
        severity="critical",
    )
    .check_value_range("order_quantity", min_val=0, severity="warning")
    .check_value_range("net_value_item", min_val=-1000000, max_val=100000000, severity="warning")
    .check_date_validity("order_date", min_date="2015-01-01", severity="warning")
    .check_date_validity("requested_delivery_date", min_date="2015-01-01", severity="warning")
    .run()
)

# Persist DQ results
dq_results_df = spark.createDataFrame(
    [
        {
            **r,
            "table_name": "cleaned_sales_orders",
            "run_id": PIPELINE_RUN_ID,
            "check_timestamp": PROCESSING_TIMESTAMP.isoformat(),
        }
        for r in dq_results
    ]
)
dq_results_df.write.format("delta").mode("append").saveAsTable(
    f"{SILVER_LAKEHOUSE}.data_quality_results"
)

if not dq_passed:
    raise RuntimeError(
        "Data quality checks FAILED for cleaned_sales_orders. "
        "Check data_quality_results table for details."
    )

# Step 4: Apply SCD Type 2 Merge
print("\n--- Step 4: Applying SCD Type 2 merge ---")
apply_scd_type_2(
    new_data=silver_df,
    target_table="cleaned_sales_orders",
    business_keys=["sales_document_number", "item_number"],
    hash_column="_silver_row_hash",
)

# Step 5: Post-merge validation
print("\n--- Step 5: Post-merge validation ---")
final_table = spark.read.table(f"{SILVER_LAKEHOUSE}.cleaned_sales_orders")
total_records = final_table.count()
current_records = final_table.filter(F.col("_is_current") == True).count()
historical_records = total_records - current_records

print(f"Total records in silver table   : {total_records}")
print(f"Current (active) records        : {current_records}")
print(f"Historical (closed) records     : {historical_records}")

# COMMAND ----------

# -- Optimize Silver Table --

print("\n--- Optimizing silver table ---")
spark.sql(f"OPTIMIZE {SILVER_LAKEHOUSE}.cleaned_sales_orders ZORDER BY (sales_document_number, order_date)")
print("OPTIMIZE with ZORDER complete.")

print("\n=== Silver Sales Orders Transformation Complete ===")
