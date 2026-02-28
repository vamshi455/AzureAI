"""
Analytics Routes - Endpoints for KPIs, demand forecasts, and pipeline status.
"""

import logging
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    KPIResponse,
    DemandForecastItem,
    DemandForecastResponse,
    PipelineStatusItem,
    PipelineStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/kpis", response_model=KPIResponse)
async def get_kpis(
    period: str = Query("monthly", description="KPI period: daily, weekly, monthly, quarterly"),
):
    """
    Get key performance indicators for sales, manufacturing, and operations.

    In production, this queries the Fabric lakehouse and PostgreSQL for
    aggregated metrics. The response includes current values and
    period-over-period change percentages.
    """
    try:
        # In production: query Fabric lakehouse via SQL endpoint or PostgreSQL
        # For now, return realistic sample data
        kpi_data = {
            "daily": {
                "total_revenue": 415200,
                "revenue_change": 3.2,
                "total_orders": 1148,
                "orders_change": 1.8,
                "production_output": 29748,
                "production_change": -0.5,
                "avg_order_value": 362,
                "avg_order_value_change": 1.4,
            },
            "weekly": {
                "total_revenue": 2906400,
                "revenue_change": 5.1,
                "total_orders": 8036,
                "orders_change": 3.7,
                "production_output": 208236,
                "production_change": 1.2,
                "avg_order_value": 362,
                "avg_order_value_change": 1.4,
            },
            "monthly": {
                "total_revenue": 12450000,
                "revenue_change": 8.3,
                "total_orders": 34521,
                "orders_change": 5.7,
                "production_output": 892400,
                "production_change": -2.1,
                "avg_order_value": 361,
                "avg_order_value_change": 3.2,
            },
            "quarterly": {
                "total_revenue": 37350000,
                "revenue_change": 12.1,
                "total_orders": 103563,
                "orders_change": 7.4,
                "production_output": 2677200,
                "production_change": 3.8,
                "avg_order_value": 361,
                "avg_order_value_change": 4.5,
            },
        }

        data = kpi_data.get(period, kpi_data["monthly"])

        return KPIResponse(
            total_revenue=data["total_revenue"],
            revenue_change=data["revenue_change"],
            total_orders=data["total_orders"],
            orders_change=data["orders_change"],
            production_output=data["production_output"],
            production_change=data["production_change"],
            avg_order_value=data["avg_order_value"],
            avg_order_value_change=data["avg_order_value_change"],
            period=period,
            as_of=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to fetch KPIs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve KPI data")


@router.get("/demand-forecast", response_model=DemandForecastResponse)
async def get_demand_forecast(
    horizon_weeks: int = Query(12, ge=1, le=52, description="Forecast horizon in weeks"),
    product_category: str = Query("all", description="Product category filter"),
):
    """
    Get demand forecast predictions with confidence intervals.

    In production, this retrieves predictions from the demand forecast
    pipeline output stored in PostgreSQL (forecasts.demand_predictions table).
    """
    try:
        forecast_items = []
        base_demand = 16000

        for week in range(1, horizon_weeks + 1):
            # Simulate seasonal pattern with trend
            seasonal_factor = 1.0 + 0.15 * (1 if week % 13 < 7 else -1)
            trend_factor = 1.0 + 0.002 * week
            noise = random.gauss(0, 0.05)

            predicted = int(base_demand * seasonal_factor * trend_factor * (1 + noise))
            actual = int(predicted * random.uniform(0.92, 1.08)) if week <= 6 else None

            # Confidence intervals widen with forecast horizon
            ci_width = 0.05 + 0.01 * week
            lower_bound = int(predicted * (1 - ci_width))
            upper_bound = int(predicted * (1 + ci_width))

            forecast_items.append(
                DemandForecastItem(
                    period=f"W{week}",
                    week_number=week,
                    actual=actual,
                    predicted=predicted,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound,
                    confidence_level=0.85,
                )
            )

        return DemandForecastResponse(
            forecast=forecast_items,
            model_version="2.4.1",
            product_category=product_category,
            generated_at=datetime.utcnow().isoformat(),
            horizon_weeks=horizon_weeks,
        )
    except Exception as e:
        logger.error(f"Failed to fetch demand forecast: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve forecast data")


@router.get("/pipeline-status", response_model=PipelineStatusResponse)
async def get_pipeline_status():
    """
    Get the current status of all data pipelines.

    In production, this queries the Microsoft Fabric REST API for
    pipeline run status and metrics.
    """
    try:
        now = datetime.utcnow()

        pipelines = [
            PipelineStatusItem(
                id="sales-ingestion",
                name="Sales Data Ingestion",
                status="succeeded",
                last_run_time=(now - timedelta(minutes=23)).isoformat(),
                duration_minutes=12,
                records_processed=245891,
                next_run_time=(now + timedelta(minutes=97)).isoformat(),
                schedule="Every 2 hours",
            ),
            PipelineStatusItem(
                id="manufacturing-telemetry",
                name="Manufacturing Telemetry",
                status="running",
                last_run_time=(now - timedelta(minutes=3)).isoformat(),
                duration_minutes=3,
                records_processed=512340,
                next_run_time=(now + timedelta(minutes=2)).isoformat(),
                schedule="Every 5 minutes",
            ),
            PipelineStatusItem(
                id="demand-forecast",
                name="Demand Forecast Pipeline",
                status="succeeded",
                last_run_time=(now - timedelta(hours=2, minutes=15)).isoformat(),
                duration_minutes=28,
                records_processed=18420,
                next_run_time=(now + timedelta(hours=21, minutes=45)).isoformat(),
                schedule="Daily at 6 AM ET",
            ),
            PipelineStatusItem(
                id="inventory-sync",
                name="Inventory Sync",
                status="succeeded",
                last_run_time=(now - timedelta(minutes=45)).isoformat(),
                duration_minutes=8,
                records_processed=8930,
                next_run_time=(now + timedelta(minutes=15)).isoformat(),
                schedule="Every hour",
            ),
            PipelineStatusItem(
                id="customer-360",
                name="Customer 360 ETL",
                status="failed",
                last_run_time=(now - timedelta(minutes=18)).isoformat(),
                duration_minutes=0,
                records_processed=0,
                next_run_time=(now + timedelta(minutes=42)).isoformat(),
                schedule="Every hour",
                error_message="PostgreSQL connection timeout after 30s",
            ),
            PipelineStatusItem(
                id="quality-metrics",
                name="Quality Metrics Aggregation",
                status="succeeded",
                last_run_time=(now - timedelta(hours=1, minutes=10)).isoformat(),
                duration_minutes=15,
                records_processed=34210,
                next_run_time=(now + timedelta(minutes=50)).isoformat(),
                schedule="Every 2 hours",
            ),
        ]

        succeeded = sum(1 for p in pipelines if p.status == "succeeded")
        running = sum(1 for p in pipelines if p.status == "running")
        failed = sum(1 for p in pipelines if p.status == "failed")

        return PipelineStatusResponse(
            pipelines=pipelines,
            summary={
                "total": len(pipelines),
                "succeeded": succeeded,
                "running": running,
                "failed": failed,
                "success_rate": round(succeeded / len(pipelines) * 100, 1),
            },
            as_of=now.isoformat(),
        )
    except Exception as e:
        logger.error(f"Failed to fetch pipeline status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve pipeline status")
