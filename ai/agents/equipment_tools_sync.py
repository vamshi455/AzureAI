"""
Equipment Health Agent Tools - Synchronous psycopg2 implementation.
Each method corresponds to a function tool the Equipment Health Agent can call.
Used by the Azure AI Foundry Agent Service client for caller-side tool execution.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


class EquipmentToolsSync:
    """Synchronous tool implementations for the Equipment Health Agent."""

    def __init__(self, conn_params: dict | None = None):
        self._conn_params = conn_params or {
            "host": os.getenv("PGHOST", "dp-psql-dev.postgres.database.azure.com"),
            "port": int(os.getenv("PGPORT", "5432")),
            "user": os.getenv("PGUSER", "dpadmin"),
            "password": os.getenv("PGPASSWORD", ""),
            "dbname": os.getenv("PGDATABASE", "manufacturing_db"),
            "sslmode": os.getenv("PGSSLMODE", "require"),
        }
        self._conn = None

    def connect(self):
        self._conn = psycopg2.connect(**self._conn_params)
        self._conn.autocommit = True
        logger.info("Connected to PostgreSQL: %s/%s", self._conn_params["host"], self._conn_params["dbname"])

    def close(self):
        if self._conn:
            self._conn.close()

    def _query(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def _query_one(self, sql: str, params: tuple = ()) -> dict | None:
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def get_equipment_status(self, equipment_id: str) -> dict:
        """Get current health status for a specific equipment."""
        row = self._query_one(
            """
            SELECT equipment_id, plant_code, production_line, health_score,
                   failure_risk, failure_probability, estimated_rul_days,
                   last_maintenance_date, next_recommended_date,
                   recommended_action, anomaly_count_30d,
                   top_risk_factors, sensor_summary,
                   model_version, computed_at
            FROM equipment_health
            WHERE equipment_id = %s
            """,
            (equipment_id,),
        )
        if not row:
            return {"error": f"Equipment '{equipment_id}' not found."}

        return {
            "equipment_id": row["equipment_id"],
            "plant_code": row["plant_code"],
            "production_line": row["production_line"],
            "health_score": float(row["health_score"]) if row["health_score"] else None,
            "failure_risk": row["failure_risk"],
            "failure_probability": float(row["failure_probability"]) if row["failure_probability"] else None,
            "estimated_rul_days": row["estimated_rul_days"],
            "last_maintenance_date": row["last_maintenance_date"].isoformat() if row["last_maintenance_date"] else None,
            "next_recommended_date": row["next_recommended_date"].isoformat() if row["next_recommended_date"] else None,
            "recommended_action": row["recommended_action"],
            "anomaly_count_30d": row["anomaly_count_30d"],
            "top_risk_factors": json.loads(row["top_risk_factors"]) if row["top_risk_factors"] else [],
            "sensor_summary": json.loads(row["sensor_summary"]) if row["sensor_summary"] else {},
            "model_version": row["model_version"],
            "computed_at": row["computed_at"].isoformat() if row["computed_at"] else None,
        }

    def list_equipment_by_risk(self, risk_level: str, plant_code: str | None = None, limit: int = 20) -> dict:
        """List equipment filtered by failure risk level."""
        sql = """
            SELECT equipment_id, plant_code, production_line, health_score,
                   failure_risk, failure_probability, estimated_rul_days,
                   recommended_action
            FROM equipment_health
            WHERE failure_risk = %s
        """
        params: list = [risk_level]

        if plant_code:
            sql += " AND plant_code = %s"
            params.append(plant_code)

        sql += " ORDER BY failure_probability DESC LIMIT %s"
        params.append(limit)

        rows = self._query(sql, tuple(params))
        return {
            "risk_level": risk_level,
            "plant_code": plant_code,
            "count": len(rows),
            "equipment": [
                {
                    "equipment_id": r["equipment_id"],
                    "plant_code": r["plant_code"],
                    "production_line": r["production_line"],
                    "health_score": float(r["health_score"]) if r["health_score"] else None,
                    "failure_probability": float(r["failure_probability"]) if r["failure_probability"] else None,
                    "estimated_rul_days": r["estimated_rul_days"],
                    "recommended_action": r["recommended_action"],
                }
                for r in rows
            ],
        }

    def get_sensor_readings(self, equipment_id: str, sensor_type: str | None = None, hours_back: int = 24) -> dict:
        """Get recent sensor readings for an equipment."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        sql = """
            SELECT device_id, sensor_type, reading_value, reading_unit,
                   quality_flag, reading_timestamp
            FROM iot_telemetry
            WHERE equipment_id = %s AND reading_timestamp >= %s
        """
        params: list = [equipment_id, cutoff]

        if sensor_type:
            sql += " AND sensor_type = %s"
            params.append(sensor_type)

        sql += " ORDER BY reading_timestamp DESC LIMIT 200"

        rows = self._query(sql, tuple(params))
        return {
            "equipment_id": equipment_id,
            "sensor_type": sensor_type or "all",
            "hours_back": hours_back,
            "reading_count": len(rows),
            "readings": [
                {
                    "device_id": r["device_id"],
                    "sensor_type": r["sensor_type"],
                    "reading_value": float(r["reading_value"]) if r["reading_value"] else None,
                    "reading_unit": r["reading_unit"],
                    "quality_flag": r["quality_flag"],
                    "reading_timestamp": r["reading_timestamp"].isoformat(),
                }
                for r in rows
            ],
        }

    def get_equipment_anomalies(self, equipment_id: str, days_back: int = 30, sensor_type: str | None = None) -> dict:
        """Find anomalous sensor readings for an equipment."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)

        sql = """
            SELECT device_id, sensor_type, reading_value, reading_unit,
                   quality_flag, reading_timestamp
            FROM iot_telemetry
            WHERE equipment_id = %s
              AND reading_timestamp >= %s
              AND quality_flag != 'GOOD'
        """
        params: list = [equipment_id, cutoff]

        if sensor_type:
            sql += " AND sensor_type = %s"
            params.append(sensor_type)

        sql += " ORDER BY reading_timestamp DESC LIMIT 100"

        rows = self._query(sql, tuple(params))
        return {
            "equipment_id": equipment_id,
            "days_back": days_back,
            "sensor_type": sensor_type or "all",
            "anomaly_count": len(rows),
            "anomalies": [
                {
                    "device_id": r["device_id"],
                    "sensor_type": r["sensor_type"],
                    "reading_value": float(r["reading_value"]) if r["reading_value"] else None,
                    "reading_unit": r["reading_unit"],
                    "quality_flag": r["quality_flag"],
                    "reading_timestamp": r["reading_timestamp"].isoformat(),
                }
                for r in rows
            ],
        }

    def search_maintenance_docs(self, query: str, equipment_id: str | None = None, top_k: int = 5) -> dict:
        """Search equipment health documents using keyword search."""
        # Switch to vector_db for document search
        vector_params = {**self._conn_params, "dbname": "vector_db"}
        with psycopg2.connect(**vector_params) as conn:
            conn.autocommit = True
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                sql = """
                    SELECT id, document_id, content, metadata, source_file,
                           ts_rank_cd(content_tsv, plainto_tsquery('english', %s)) AS rank_score
                    FROM document_embeddings
                    WHERE document_type = 'equipment_health'
                      AND content_tsv @@ plainto_tsquery('english', %s)
                """
                params: list = [query, query]

                if equipment_id:
                    metadata_filter = json.dumps({"equipment_id": equipment_id})
                    sql += " AND metadata @> %s::jsonb"
                    params.append(metadata_filter)

                sql += " ORDER BY rank_score DESC LIMIT %s"
                params.append(top_k)

                cur.execute(sql, tuple(params))
                rows = [dict(r) for r in cur.fetchall()]

        return {
            "query": query,
            "equipment_id": equipment_id,
            "result_count": len(rows),
            "results": [
                {
                    "document_id": r["document_id"],
                    "content": r["content"][:500],
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                    "source_file": r["source_file"],
                    "relevance_score": float(r["rank_score"]),
                }
                for r in rows
            ],
        }
