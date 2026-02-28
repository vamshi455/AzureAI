"""
Pydantic Models - Request/response schemas for all API endpoints.
"""

from pydantic import BaseModel, Field
from typing import Any


# ---------------------------------------------------------------
# Chat Schemas
# ---------------------------------------------------------------

class ChatMessageSchema(BaseModel):
    """A single message in a chat conversation."""
    role: str = Field(..., description="Message role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message content text")


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""
    agent_id: str = Field(
        ...,
        description="ID of the AI agent to query",
        examples=["sales-forecast-agent", "customer-support-agent"],
    )
    messages: list[ChatMessageSchema] = Field(
        ...,
        description="Conversation messages including history",
        min_length=1,
    )
    stream: bool = Field(
        default=False,
        description="Whether to stream the response via SSE",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Temperature override (uses agent default if not set)",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        le=16384,
        description="Max tokens override (uses agent default if not set)",
    )


class CitationSchema(BaseModel):
    """A source citation for an AI response."""
    title: str = Field(..., description="Citation title")
    source: str = Field(..., description="Source system or database")
    url: str = Field(..., description="URL or path to the source")


class ChatResponse(BaseModel):
    """Response body for non-streaming chat completions."""
    id: str = Field(..., description="Response ID from AI Foundry")
    content: str = Field(..., description="Generated response text")
    agent_id: str = Field(..., description="ID of the responding agent")
    model: str = Field(..., description="Model deployment name used")
    citations: list[CitationSchema] = Field(
        default_factory=list,
        description="Source citations for the response",
    )
    usage: dict[str, int] = Field(
        default_factory=dict,
        description="Token usage: prompt_tokens, completion_tokens, total_tokens",
    )
    finish_reason: str = Field(
        default="stop",
        description="Completion finish reason",
    )


class ChatStreamEvent(BaseModel):
    """A single event in the SSE chat stream."""
    type: str = Field(..., description="Event type: 'content', 'citations', 'error', 'done'")
    content: str = Field(default="", description="Content chunk (for type='content')")
    citations: list[CitationSchema] | None = Field(
        default=None,
        description="Citations (for type='citations')",
    )
    message: str | None = Field(
        default=None,
        description="Error message (for type='error')",
    )


# ---------------------------------------------------------------
# Analytics Schemas
# ---------------------------------------------------------------

class KPIResponse(BaseModel):
    """Key Performance Indicators response."""
    total_revenue: float = Field(..., description="Total revenue in USD")
    revenue_change: float = Field(..., description="Revenue change percentage vs previous period")
    total_orders: int = Field(..., description="Total number of orders")
    orders_change: float = Field(..., description="Orders change percentage vs previous period")
    production_output: int = Field(..., description="Total production output units")
    production_change: float = Field(..., description="Production change percentage")
    avg_order_value: float = Field(..., description="Average order value in USD")
    avg_order_value_change: float = Field(..., description="AOV change percentage")
    period: str = Field(..., description="KPI aggregation period")
    as_of: str = Field(..., description="Timestamp of data")


class DemandForecastItem(BaseModel):
    """A single forecast data point."""
    period: str = Field(..., description="Forecast period label (e.g., 'W1')")
    week_number: int = Field(..., description="Week number in the forecast horizon")
    actual: int | None = Field(None, description="Actual demand (null for future periods)")
    predicted: int = Field(..., description="Predicted demand")
    lower_bound: int = Field(..., description="Lower confidence bound")
    upper_bound: int = Field(..., description="Upper confidence bound")
    confidence_level: float = Field(default=0.85, description="Confidence interval level")


class DemandForecastResponse(BaseModel):
    """Demand forecast response with metadata."""
    forecast: list[DemandForecastItem] = Field(..., description="Forecast data points")
    model_version: str = Field(..., description="Forecast model version")
    product_category: str = Field(..., description="Product category filter applied")
    generated_at: str = Field(..., description="When the forecast was generated")
    horizon_weeks: int = Field(..., description="Forecast horizon in weeks")


class PipelineStatusItem(BaseModel):
    """Status of a single data pipeline."""
    id: str = Field(..., description="Pipeline identifier")
    name: str = Field(..., description="Pipeline display name")
    status: str = Field(
        ...,
        description="Pipeline status: succeeded, running, failed, queued",
    )
    last_run_time: str = Field(..., description="Last run start time (ISO 8601)")
    duration_minutes: int = Field(..., description="Last run duration in minutes")
    records_processed: int = Field(..., description="Records processed in last run")
    next_run_time: str | None = Field(None, description="Scheduled next run time")
    schedule: str | None = Field(None, description="Schedule description")
    error_message: str | None = Field(None, description="Error message if status is 'failed'")


class PipelineStatusResponse(BaseModel):
    """Response with all pipeline statuses and summary."""
    pipelines: list[PipelineStatusItem] = Field(..., description="List of pipeline statuses")
    summary: dict[str, Any] = Field(
        ...,
        description="Summary counts: total, succeeded, running, failed, success_rate",
    )
    as_of: str = Field(..., description="Timestamp of status check")


# ---------------------------------------------------------------
# Ticket Schemas (Plane Integration)
# ---------------------------------------------------------------

class CreateTicketRequest(BaseModel):
    """Request to create a new support ticket."""
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Ticket title",
    )
    description: str | None = Field(
        None,
        max_length=10000,
        description="Detailed ticket description",
    )
    priority: str = Field(
        default="medium",
        description="Priority: urgent, high, medium, low, none",
    )
    labels: list[str] | None = Field(
        None,
        description="Labels to apply to the ticket",
    )
    assignee: str | None = Field(
        None,
        description="Assignee email or user ID",
    )


class UpdateTicketRequest(BaseModel):
    """Request to update an existing ticket."""
    title: str | None = Field(None, max_length=500, description="Updated title")
    description: str | None = Field(None, max_length=10000, description="Updated description")
    status: str | None = Field(
        None,
        description="Updated status: backlog, todo, in_progress, done, cancelled",
    )
    priority: str | None = Field(
        None,
        description="Updated priority: urgent, high, medium, low, none",
    )
    labels: list[str] | None = Field(None, description="Updated labels")
    assignee: str | None = Field(None, description="Updated assignee")


class TicketResponse(BaseModel):
    """Response for a single ticket."""
    id: str = Field(..., description="Ticket identifier")
    title: str = Field(..., description="Ticket title")
    description: str | None = Field(None, description="Ticket description")
    status: str = Field(..., description="Current status")
    priority: str = Field(..., description="Priority level")
    assignee: str | None = Field(None, description="Assigned user")
    labels: list[str] | None = Field(None, description="Applied labels")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class TicketListResponse(BaseModel):
    """Response for listing tickets with pagination."""
    tickets: list[TicketResponse] = Field(..., description="List of tickets")
    total: int = Field(..., description="Total number of matching tickets")
    limit: int = Field(..., description="Requested page size")
    offset: int = Field(..., description="Pagination offset")


# ---------------------------------------------------------------
# Common Schemas
# ---------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status: healthy, degraded, unhealthy")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    environment: str = Field(..., description="Deployment environment")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    timestamp: str = Field(..., description="Current timestamp")


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str = Field(..., description="Error description")
    type: str | None = Field(None, description="Error type")
    status_code: int = Field(..., description="HTTP status code")
