"""
Load Equipment Health Data into PostgreSQL.
Reads Parquet files from synthetic-data output and inserts into PostgreSQL tables.

Usage:
    python load_equipment_data.py
    python load_equipment_data.py --pg-host dp-psql-dev.postgres.database.azure.com
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("load_equipment_data")

# Default paths (relative to repo root)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = REPO_ROOT / "data-platform" / "synthetic-data" / "output"
SCHEMA_FILE = REPO_ROOT / "data-platform" / "sql" / "schemas" / "equipment_health_pg.sql"

# Data file paths
HEALTH_SCORES_PARQUET = DATA_DIR / "gold" / "equipment_health_scores.parquet"
IOT_TELEMETRY_PARQUET = DATA_DIR / "bronze" / "iot" / "telemetry" / "iot_telemetry.parquet"
LIFECYCLE_EVENTS_PARQUET = DATA_DIR / "bronze" / "iot" / "telemetry" / "equipment_lifecycle_events.parquet"


def get_connection(args) -> psycopg2.extensions.connection:
    """Create a PostgreSQL connection from args or environment variables."""
    conn = psycopg2.connect(
        host=args.pg_host or os.getenv("PGHOST", "localhost"),
        port=args.pg_port or int(os.getenv("PGPORT", "5432")),
        dbname=args.pg_dbname or os.getenv("PGDATABASE", "postgres"),
        user=args.pg_user or os.getenv("PGUSER", "postgres"),
        password=args.pg_password or os.getenv("PGPASSWORD", ""),
        sslmode=args.pg_sslmode or os.getenv("PGSSLMODE", "require"),
    )
    conn.autocommit = False
    return conn


def create_schema(conn):
    """Create tables from the SQL schema file."""
    logger.info(f"Applying schema from {SCHEMA_FILE}")
    sql = SCHEMA_FILE.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("Schema applied successfully.")


def load_equipment_health(conn, batch_size: int = 200):
    """Load equipment health scores from Parquet into PostgreSQL."""
    if not HEALTH_SCORES_PARQUET.exists():
        logger.warning(f"File not found: {HEALTH_SCORES_PARQUET}")
        return

    logger.info(f"Reading {HEALTH_SCORES_PARQUET}")
    df = pd.read_parquet(HEALTH_SCORES_PARQUET)
    logger.info(f"Loaded {len(df)} equipment health records.")

    # Normalize column names (Parquet may use different casing)
    col_map = {}
    for col in df.columns:
        col_map[col] = col.lower().replace(" ", "_")
    df = df.rename(columns=col_map)

    # Truncate existing data and reload
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE equipment_health CASCADE")

        columns = [
            "equipment_id", "plant_code", "production_line", "device_ids",
            "health_score", "failure_risk", "failure_probability",
            "estimated_rul_days", "last_maintenance_date", "next_recommended_date",
            "recommended_action", "anomaly_count_30d", "top_risk_factors",
            "sensor_summary", "model_version",
        ]

        # Only use columns that exist in the DataFrame
        available = [c for c in columns if c in df.columns]

        rows = []
        for _, row in df.iterrows():
            values = []
            for col in available:
                val = row.get(col)
                if pd.isna(val):
                    values.append(None)
                elif col in ("top_risk_factors", "sensor_summary"):
                    values.append(json.dumps(val) if not isinstance(val, str) else val)
                else:
                    values.append(val)
            rows.append(tuple(values))

        cols_str = ", ".join(available)
        template = "(" + ", ".join(["%s"] * len(available)) + ")"

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            execute_values(
                cur,
                f"INSERT INTO equipment_health ({cols_str}) VALUES %s",
                batch,
                template=template,
            )
            logger.info(f"  Inserted batch {i // batch_size + 1} ({len(batch)} rows)")

    conn.commit()
    logger.info(f"Loaded {len(rows)} rows into equipment_health.")


def load_iot_telemetry(conn, batch_size: int = 5000, limit: int | None = None):
    """Load IoT telemetry from Parquet into PostgreSQL."""
    if not IOT_TELEMETRY_PARQUET.exists():
        logger.warning(f"File not found: {IOT_TELEMETRY_PARQUET}")
        return

    logger.info(f"Reading {IOT_TELEMETRY_PARQUET}")
    df = pd.read_parquet(IOT_TELEMETRY_PARQUET)
    logger.info(f"Loaded {len(df)} telemetry records from Parquet.")

    col_map = {col: col.lower().replace(" ", "_") for col in df.columns}
    df = df.rename(columns=col_map)

    if limit:
        df = df.head(limit)
        logger.info(f"Limited to {limit} rows.")

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE iot_telemetry CASCADE")

        columns = [
            "equipment_id", "device_id", "sensor_type", "reading_value",
            "reading_unit", "quality_flag", "reading_timestamp",
            "plant_code", "production_line",
        ]
        available = [c for c in columns if c in df.columns]

        rows = []
        for _, row in df.iterrows():
            values = []
            for col in available:
                val = row.get(col)
                if pd.isna(val):
                    values.append(None)
                else:
                    values.append(val)
            rows.append(tuple(values))

        cols_str = ", ".join(available)
        template = "(" + ", ".join(["%s"] * len(available)) + ")"

        total_batches = (len(rows) + batch_size - 1) // batch_size
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            execute_values(
                cur,
                f"INSERT INTO iot_telemetry ({cols_str}) VALUES %s",
                batch,
                template=template,
            )
            batch_num = i // batch_size + 1
            if batch_num % 20 == 0 or batch_num == total_batches:
                logger.info(f"  Telemetry batch {batch_num}/{total_batches} ({len(batch)} rows)")

    conn.commit()
    logger.info(f"Loaded {len(rows)} rows into iot_telemetry.")


def load_lifecycle_events(conn, batch_size: int = 1000):
    """Load equipment lifecycle events from Parquet into PostgreSQL."""
    if not LIFECYCLE_EVENTS_PARQUET.exists():
        logger.warning(f"File not found: {LIFECYCLE_EVENTS_PARQUET}")
        return

    logger.info(f"Reading {LIFECYCLE_EVENTS_PARQUET}")
    df = pd.read_parquet(LIFECYCLE_EVENTS_PARQUET)
    logger.info(f"Loaded {len(df)} lifecycle event records.")

    col_map = {col: col.lower().replace(" ", "_") for col in df.columns}
    df = df.rename(columns=col_map)

    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE equipment_lifecycle_events CASCADE")

        columns = [
            "equipment_id", "event_type", "from_state", "to_state",
            "event_timestamp", "plant_code",
        ]
        available = [c for c in columns if c in df.columns]

        rows = []
        for _, row in df.iterrows():
            values = []
            for col in available:
                val = row.get(col)
                if pd.isna(val):
                    values.append(None)
                else:
                    values.append(val)
            rows.append(tuple(values))

        cols_str = ", ".join(available)
        template = "(" + ", ".join(["%s"] * len(available)) + ")"

        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            execute_values(
                cur,
                f"INSERT INTO equipment_lifecycle_events ({cols_str}) VALUES %s",
                batch,
                template=template,
            )

    conn.commit()
    logger.info(f"Loaded {len(rows)} rows into equipment_lifecycle_events.")


def main():
    parser = argparse.ArgumentParser(description="Load equipment data into PostgreSQL")
    parser.add_argument("--pg-host", default=None)
    parser.add_argument("--pg-port", type=int, default=None)
    parser.add_argument("--pg-dbname", default=None)
    parser.add_argument("--pg-user", default=None)
    parser.add_argument("--pg-password", default=None)
    parser.add_argument("--pg-sslmode", default=None)
    parser.add_argument("--telemetry-limit", type=int, default=None,
                        help="Limit number of telemetry rows (for dev/testing)")
    parser.add_argument("--skip-schema", action="store_true",
                        help="Skip creating tables (assume they exist)")
    args = parser.parse_args()

    logger.info("=== Equipment Data Loader ===")
    conn = get_connection(args)

    try:
        if not args.skip_schema:
            create_schema(conn)

        load_equipment_health(conn)
        load_iot_telemetry(conn, limit=args.telemetry_limit)
        load_lifecycle_events(conn)

        # Print summary
        with conn.cursor() as cur:
            for table in ["equipment_health", "iot_telemetry", "equipment_lifecycle_events"]:
                cur.execute(f"SELECT count(*) FROM {table}")
                count = cur.fetchone()[0]
                logger.info(f"  {table}: {count:,} rows")

        logger.info("=== Data loading complete ===")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
