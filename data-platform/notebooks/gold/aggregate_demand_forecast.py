# Databricks/Fabric Notebook: Gold Layer - Demand Forecast Aggregation
# Purpose: Build demand forecasting features, sales KPIs, and product metrics
#          from silver-layer data into consumption-ready gold tables.
# Schedule: Daily at 06:00 UTC after silver transformations complete.
# Layer: Gold (curated, business-ready, optimized for analytics and ML)

# COMMAND ----------

# MAGIC %md
# MAGIC # Gold Layer - Demand Forecast Features & Sales KPIs
# MAGIC Build aggregated, business-ready datasets for:
# MAGIC 1. **Demand Forecast Features** - ML input features for demand prediction
# MAGIC 2. **Sales KPIs** - Fact table for BI dashboards
# MAGIC 3. **Product Metrics** - Product performance aggregations

# COMMAND ----------

from pyspark.sql import SparkSession, DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DecimalType,
    IntegerType,
    DateType,
    StringType,
    DoubleType,
    TimestampType,
)
from delta.tables import DeltaTable
from datetime import datetime, timezone, timedelta
import logging

# COMMAND ----------

# -- Configuration --

try:
    SILVER_LAKEHOUSE = spark.conf.get("spark.custom.silver_lakehouse", "lh_silver")
    GOLD_LAKEHOUSE = spark.conf.get("spark.custom.gold_lakehouse", "lh_gold")
    PIPELINE_RUN_ID = spark.conf.get("spark.custom.pipeline_run_id", "manual_run")
    FORECAST_HORIZON_DAYS = int(spark.conf.get("spark.custom.forecast_horizon", "90"))
    LOOKBACK_DAYS = int(spark.conf.get("spark.custom.lookback_days", "365"))
except Exception:
    SILVER_LAKEHOUSE = "lh_silver"
    GOLD_LAKEHOUSE = "lh_gold"
    PIPELINE_RUN_ID = "manual_run"
    FORECAST_HORIZON_DAYS = 90
    LOOKBACK_DAYS = 365

PROCESSING_TIMESTAMP = datetime.now(timezone.utc)
CUTOFF_DATE = (PROCESSING_TIMESTAMP - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")

logger = logging.getLogger("gold_demand_forecast")
logger.setLevel(logging.INFO)

# COMMAND ----------

# -- Dimension Table Builders --

def build_dim_date(start_date: str = "2020-01-01", end_date: str = "2027-12-31") -> DataFrame:
    """
    Generate a comprehensive date dimension table covering the specified range.
    Includes fiscal calendar aligned to a July-June fiscal year common in manufacturing.
    """
    date_df = spark.sql(f"""
        SELECT explode(sequence(
            to_date('{start_date}'),
            to_date('{end_date}'),
            interval 1 day
        )) AS date_key
    """)

    dim_date = date_df.select(
        F.col("date_key"),
        F.date_format("date_key", "yyyyMMdd").cast(IntegerType()).alias("date_id"),
        F.year("date_key").alias("calendar_year"),
        F.quarter("date_key").alias("calendar_quarter"),
        F.month("date_key").alias("calendar_month"),
        F.weekofyear("date_key").alias("calendar_week"),
        F.dayofmonth("date_key").alias("day_of_month"),
        F.dayofweek("date_key").alias("day_of_week"),
        F.dayofyear("date_key").alias("day_of_year"),
        F.date_format("date_key", "EEEE").alias("day_name"),
        F.date_format("date_key", "MMMM").alias("month_name"),
        F.date_format("date_key", "MMM-yyyy").alias("month_year_label"),
        # Fiscal year (Jul-Jun)
        F.when(F.month("date_key") >= 7, F.year("date_key") + 1)
        .otherwise(F.year("date_key"))
        .alias("fiscal_year"),
        F.when(F.month("date_key").between(7, 9), 1)
        .when(F.month("date_key").between(10, 12), 2)
        .when(F.month("date_key").between(1, 3), 3)
        .otherwise(4)
        .alias("fiscal_quarter"),
        # Flags
        F.when(F.dayofweek("date_key").isin(1, 7), True)
        .otherwise(False)
        .alias("is_weekend"),
        # ISO week for international reporting
        F.date_format("date_key", "yyyy-'W'ww").alias("iso_week_label"),
    )

    return dim_date


def build_dim_product(silver_sales: DataFrame) -> DataFrame:
    """
    Build product dimension from silver sales order data.
    Extracts distinct product attributes with the latest values.
    """
    product_window = Window.partitionBy("material_number").orderBy(
        F.col("_silver_processed_timestamp").desc()
    )

    dim_product = (
        silver_sales.filter(F.col("_is_current") == True)
        .filter(F.col("material_number").isNotNull())
        .withColumn("_rn", F.row_number().over(product_window))
        .filter(F.col("_rn") == 1)
        .select(
            F.sha2(F.col("material_number"), 256).alias("product_key"),
            F.col("material_number"),
            F.col("material_group"),
            F.col("item_description").alias("product_name"),
            F.col("division").alias("product_division"),
            F.col("sales_unit").alias("base_unit_of_measure"),
        )
        .withColumn("_gold_loaded_at", F.lit(PROCESSING_TIMESTAMP))
    )

    return dim_product


def build_dim_customer(silver_sales: DataFrame) -> DataFrame:
    """
    Build customer dimension from silver sales data.
    Extracts distinct customer attributes.
    """
    customer_window = Window.partitionBy("customer_number").orderBy(
        F.col("_silver_processed_timestamp").desc()
    )

    dim_customer = (
        silver_sales.filter(F.col("_is_current") == True)
        .filter(F.col("customer_number").isNotNull())
        .withColumn("_rn", F.row_number().over(customer_window))
        .filter(F.col("_rn") == 1)
        .select(
            F.sha2(F.col("customer_number"), 256).alias("customer_key"),
            F.col("customer_number"),
            F.col("sales_organization"),
            F.col("distribution_channel"),
            F.col("division").alias("customer_division"),
        )
        .withColumn("_gold_loaded_at", F.lit(PROCESSING_TIMESTAMP))
    )

    return dim_customer


# COMMAND ----------

# -- Fact Table Builder --

def build_fact_sales(silver_sales: DataFrame) -> DataFrame:
    """
    Build the fact_sales table from silver sales orders.
    Contains one row per order line item with measures and dimension keys.
    """
    fact = (
        silver_sales.filter(F.col("_is_current") == True)
        .select(
            # Surrogate keys for dimensions
            F.sha2(F.col("material_number"), 256).alias("product_key"),
            F.sha2(F.col("customer_number"), 256).alias("customer_key"),
            F.date_format("order_date", "yyyyMMdd").cast(IntegerType()).alias("order_date_key"),
            F.date_format("requested_delivery_date", "yyyyMMdd")
            .cast(IntegerType())
            .alias("delivery_date_key"),
            # Business keys (degenerate dimensions)
            F.col("sales_document_number"),
            F.col("item_number"),
            F.col("sales_order_key"),
            # Descriptive attributes
            F.col("order_type"),
            F.col("sales_organization"),
            F.col("distribution_channel"),
            F.col("plant"),
            F.col("storage_location"),
            F.col("is_rejected"),
            # Measures
            F.col("order_quantity"),
            F.col("net_value_item").alias("net_value"),
            F.col("currency"),
            # Derived measures
            F.when(F.col("order_quantity") > 0, F.col("net_value_item") / F.col("order_quantity"))
            .otherwise(F.lit(None))
            .cast(DecimalType(18, 2))
            .alias("unit_price"),
            # Lineage
            F.lit(PROCESSING_TIMESTAMP).alias("_gold_loaded_at"),
            F.lit(PIPELINE_RUN_ID).alias("_gold_pipeline_run_id"),
        )
    )

    return fact


# COMMAND ----------

# -- Demand Forecast Feature Engineering --

def build_demand_forecast_features(silver_sales: DataFrame) -> DataFrame:
    """
    Build feature table for demand forecasting ML model.

    Features include:
    - Temporal aggregations (daily, weekly, monthly sales)
    - Rolling statistics (7d, 30d, 90d moving averages)
    - Lag features (previous period demand)
    - Trend and seasonality indicators
    - Product velocity classification
    """
    # Filter to current, non-rejected orders within lookback window
    base = (
        silver_sales.filter(F.col("_is_current") == True)
        .filter(F.col("is_rejected") == False)
        .filter(F.col("order_date") >= F.lit(CUTOFF_DATE))
        .filter(F.col("order_date").isNotNull())
        .filter(F.col("material_number").isNotNull())
    )

    # -- Daily aggregation per product-plant --
    daily_demand = (
        base.groupBy("material_number", "plant", "order_date")
        .agg(
            F.sum("order_quantity").cast(DoubleType()).alias("daily_quantity"),
            F.sum("net_value_item").cast(DoubleType()).alias("daily_revenue"),
            F.countDistinct("sales_document_number").alias("daily_order_count"),
            F.countDistinct("customer_number").alias("daily_unique_customers"),
        )
    )

    # -- Window specifications for rolling features --
    days_7 = (
        Window.partitionBy("material_number", "plant")
        .orderBy(F.col("order_date").cast("long"))
        .rangeBetween(-6 * 86400, 0)
    )
    days_30 = (
        Window.partitionBy("material_number", "plant")
        .orderBy(F.col("order_date").cast("long"))
        .rangeBetween(-29 * 86400, 0)
    )
    days_90 = (
        Window.partitionBy("material_number", "plant")
        .orderBy(F.col("order_date").cast("long"))
        .rangeBetween(-89 * 86400, 0)
    )

    # Row-based windows for lag features
    row_window = (
        Window.partitionBy("material_number", "plant")
        .orderBy("order_date")
    )

    # -- Add rolling features --
    features_df = daily_demand.select(
        "*",
        # Rolling averages
        F.avg("daily_quantity").over(days_7).alias("rolling_avg_qty_7d"),
        F.avg("daily_quantity").over(days_30).alias("rolling_avg_qty_30d"),
        F.avg("daily_quantity").over(days_90).alias("rolling_avg_qty_90d"),
        # Rolling sums
        F.sum("daily_quantity").over(days_7).alias("rolling_sum_qty_7d"),
        F.sum("daily_quantity").over(days_30).alias("rolling_sum_qty_30d"),
        # Rolling standard deviation (volatility)
        F.stddev("daily_quantity").over(days_30).alias("rolling_std_qty_30d"),
        # Rolling revenue
        F.avg("daily_revenue").over(days_30).alias("rolling_avg_revenue_30d"),
        # Lag features
        F.lag("daily_quantity", 1).over(row_window).alias("lag_qty_1d"),
        F.lag("daily_quantity", 7).over(row_window).alias("lag_qty_7d"),
        F.lag("daily_quantity", 30).over(row_window).alias("lag_qty_30d"),
        # Order count features
        F.avg("daily_order_count").over(days_30).alias("rolling_avg_orders_30d"),
    )

    # -- Add temporal features --
    features_df = features_df.withColumns({
        "day_of_week": F.dayofweek("order_date"),
        "day_of_month": F.dayofmonth("order_date"),
        "week_of_year": F.weekofyear("order_date"),
        "month": F.month("order_date"),
        "quarter": F.quarter("order_date"),
        "is_weekend": F.when(F.dayofweek("order_date").isin(1, 7), 1).otherwise(0),
        "is_month_start": F.when(F.dayofmonth("order_date") <= 3, 1).otherwise(0),
        "is_month_end": F.when(F.dayofmonth("order_date") >= 28, 1).otherwise(0),
        "is_quarter_end": F.when(
            (F.month("order_date").isin(3, 6, 9, 12)) & (F.dayofmonth("order_date") >= 25),
            1,
        ).otherwise(0),
    })

    # -- Coefficient of Variation (demand variability) --
    features_df = features_df.withColumn(
        "demand_cv_30d",
        F.when(
            F.col("rolling_avg_qty_30d") > 0,
            F.col("rolling_std_qty_30d") / F.col("rolling_avg_qty_30d"),
        ).otherwise(F.lit(None)),
    )

    # -- Trend indicator (30d avg vs 90d avg) --
    features_df = features_df.withColumn(
        "trend_indicator",
        F.when(
            (F.col("rolling_avg_qty_90d").isNotNull())
            & (F.col("rolling_avg_qty_90d") > 0),
            (F.col("rolling_avg_qty_30d") - F.col("rolling_avg_qty_90d"))
            / F.col("rolling_avg_qty_90d"),
        ).otherwise(F.lit(0.0)),
    )

    # -- Product velocity classification --
    # Based on average daily demand over 90 days
    product_velocity_window = Window.partitionBy("material_number", "plant")
    features_df = features_df.withColumn(
        "avg_daily_demand_90d",
        F.avg("daily_quantity").over(product_velocity_window),
    ).withColumn(
        "product_velocity",
        F.when(F.col("avg_daily_demand_90d") >= 100, F.lit("A_FAST"))
        .when(F.col("avg_daily_demand_90d") >= 10, F.lit("B_MEDIUM"))
        .when(F.col("avg_daily_demand_90d") >= 1, F.lit("C_SLOW"))
        .otherwise(F.lit("D_VERY_SLOW")),
    )

    # -- Add metadata --
    features_df = features_df.withColumns({
        "_gold_loaded_at": F.lit(PROCESSING_TIMESTAMP),
        "_gold_pipeline_run_id": F.lit(PIPELINE_RUN_ID),
        "_forecast_horizon_days": F.lit(FORECAST_HORIZON_DAYS),
        "_feature_version": F.lit("v2.1"),
    })

    return features_df


# COMMAND ----------

# -- Product Performance Metrics --

def build_product_metrics(silver_sales: DataFrame) -> DataFrame:
    """
    Build aggregated product performance metrics for BI and reporting.
    Includes monthly and quarterly rollups with YoY comparisons.
    """
    current_orders = (
        silver_sales.filter(F.col("_is_current") == True)
        .filter(F.col("order_date").isNotNull())
        .filter(F.col("material_number").isNotNull())
    )

    monthly_metrics = current_orders.groupBy(
        "material_number",
        "plant",
        "sales_organization",
        F.date_trunc("month", "order_date").alias("month_start"),
    ).agg(
        # Volume metrics
        F.sum("order_quantity").cast(DecimalType(18, 3)).alias("total_quantity"),
        F.sum("net_value_item").cast(DecimalType(18, 2)).alias("total_revenue"),
        F.count("*").alias("line_item_count"),
        F.countDistinct("sales_document_number").alias("order_count"),
        F.countDistinct("customer_number").alias("unique_customers"),
        # Price metrics
        F.avg(
            F.when(F.col("order_quantity") > 0, F.col("net_value_item") / F.col("order_quantity"))
        )
        .cast(DecimalType(18, 2))
        .alias("avg_unit_price"),
        F.min(
            F.when(F.col("order_quantity") > 0, F.col("net_value_item") / F.col("order_quantity"))
        )
        .cast(DecimalType(18, 2))
        .alias("min_unit_price"),
        F.max(
            F.when(F.col("order_quantity") > 0, F.col("net_value_item") / F.col("order_quantity"))
        )
        .cast(DecimalType(18, 2))
        .alias("max_unit_price"),
        # Rejection metrics
        F.sum(F.when(F.col("is_rejected") == True, 1).otherwise(0)).alias("rejected_line_items"),
        F.sum(
            F.when(F.col("is_rejected") == True, F.col("net_value_item")).otherwise(0)
        )
        .cast(DecimalType(18, 2))
        .alias("rejected_value"),
    )

    # Add YoY comparison via self-join
    yoy_window = Window.partitionBy(
        "material_number", "plant", "sales_organization", F.month("month_start")
    ).orderBy(F.year("month_start"))

    monthly_metrics = monthly_metrics.withColumn(
        "prev_year_revenue",
        F.lag("total_revenue", 1).over(yoy_window),
    ).withColumn(
        "prev_year_quantity",
        F.lag("total_quantity", 1).over(yoy_window),
    ).withColumn(
        "yoy_revenue_growth",
        F.when(
            F.col("prev_year_revenue") > 0,
            (F.col("total_revenue") - F.col("prev_year_revenue")) / F.col("prev_year_revenue"),
        ).otherwise(F.lit(None)),
    ).withColumn(
        "yoy_quantity_growth",
        F.when(
            F.col("prev_year_quantity") > 0,
            (F.col("total_quantity") - F.col("prev_year_quantity")) / F.col("prev_year_quantity"),
        ).otherwise(F.lit(None)),
    ).withColumns({
        "_gold_loaded_at": F.lit(PROCESSING_TIMESTAMP),
        "_gold_pipeline_run_id": F.lit(PIPELINE_RUN_ID),
    })

    return monthly_metrics


# COMMAND ----------

# -- Main Execution --

print(f"=== Gold Layer Aggregation Started ===")
print(f"Pipeline Run    : {PIPELINE_RUN_ID}")
print(f"Silver Source    : {SILVER_LAKEHOUSE}")
print(f"Gold Target      : {GOLD_LAKEHOUSE}")
print(f"Lookback Days   : {LOOKBACK_DAYS}")
print(f"Forecast Horizon: {FORECAST_HORIZON_DAYS}")
print(f"Cutoff Date     : {CUTOFF_DATE}")
print(f"======================================")

# Read silver sales orders
print("\n--- Reading silver data ---")
silver_sales = spark.read.table(f"{SILVER_LAKEHOUSE}.cleaned_sales_orders")
total_silver_records = silver_sales.count()
current_records = silver_sales.filter(F.col("_is_current") == True).count()
print(f"Total silver records: {total_silver_records}")
print(f"Current records     : {current_records}")

# COMMAND ----------

# Build and write dim_date
print("\n--- Building dim_date ---")
dim_date = build_dim_date()
dim_date.write.format("delta").mode("overwrite").saveAsTable(f"{GOLD_LAKEHOUSE}.dim_date")
print(f"dim_date: {dim_date.count()} rows written.")

# COMMAND ----------

# Build and write dim_product
print("\n--- Building dim_product ---")
dim_product = build_dim_product(silver_sales)
dim_product.write.format("delta").mode("overwrite").saveAsTable(f"{GOLD_LAKEHOUSE}.dim_product")
print(f"dim_product: {dim_product.count()} rows written.")

# COMMAND ----------

# Build and write dim_customer
print("\n--- Building dim_customer ---")
dim_customer = build_dim_customer(silver_sales)
dim_customer.write.format("delta").mode("overwrite").saveAsTable(f"{GOLD_LAKEHOUSE}.dim_customer")
print(f"dim_customer: {dim_customer.count()} rows written.")

# COMMAND ----------

# Build and write fact_sales
print("\n--- Building fact_sales ---")
fact_sales = build_fact_sales(silver_sales)
fact_sales.write.format("delta").mode("overwrite").saveAsTable(f"{GOLD_LAKEHOUSE}.fact_sales")
print(f"fact_sales: {fact_sales.count()} rows written.")

# COMMAND ----------

# Build and write demand forecast features
print("\n--- Building demand forecast features ---")
forecast_features = build_demand_forecast_features(silver_sales)
forecast_features.write.format("delta").mode("overwrite").option(
    "overwriteSchema", "true"
).saveAsTable(f"{GOLD_LAKEHOUSE}.agg_demand_forecast")
print(f"agg_demand_forecast: {forecast_features.count()} rows written.")

# COMMAND ----------

# Build and write product metrics
print("\n--- Building product metrics ---")
product_metrics = build_product_metrics(silver_sales)
product_metrics.write.format("delta").mode("overwrite").saveAsTable(
    f"{GOLD_LAKEHOUSE}.agg_product_metrics"
)
print(f"agg_product_metrics: {product_metrics.count()} rows written.")

# COMMAND ----------

# -- Optimize Gold Tables --
print("\n--- Optimizing gold tables ---")
gold_tables_optimize = {
    "fact_sales": "order_date_key, product_key",
    "agg_demand_forecast": "material_number, order_date",
    "agg_product_metrics": "material_number, month_start",
}

for table_name, zorder_cols in gold_tables_optimize.items():
    try:
        spark.sql(f"OPTIMIZE {GOLD_LAKEHOUSE}.{table_name} ZORDER BY ({zorder_cols})")
        print(f"  Optimized: {table_name} (ZORDER: {zorder_cols})")
    except Exception as e:
        print(f"  Optimize skipped for {table_name}: {str(e)}")

# COMMAND ----------

# -- Summary --
print("\n=== Gold Layer Aggregation Summary ===")
for table in ["dim_date", "dim_product", "dim_customer", "fact_sales", "agg_demand_forecast", "agg_product_metrics"]:
    try:
        count = spark.read.table(f"{GOLD_LAKEHOUSE}.{table}").count()
        print(f"  {table:<30} : {count:>10} rows")
    except Exception:
        print(f"  {table:<30} : TABLE NOT FOUND")

print(f"\nPipeline Run: {PIPELINE_RUN_ID}")
print(f"Completed at: {datetime.now(timezone.utc).isoformat()}")
print("=== Gold Layer Aggregation Complete ===")
