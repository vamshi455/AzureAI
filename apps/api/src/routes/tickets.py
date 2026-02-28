"""
Tickets Routes - Plane API integration for ticket creation, listing, and updates.
"""

import os
import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    TicketResponse,
    TicketListResponse,
    CreateTicketRequest,
    UpdateTicketRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Plane API configuration
PLANE_API_BASE = os.getenv("PLANE_API_BASE", "https://plane.company.com/api/v1")
PLANE_API_KEY = os.getenv("PLANE_API_KEY", "")
PLANE_WORKSPACE_SLUG = os.getenv("PLANE_WORKSPACE_SLUG", "data-platform")
PLANE_PROJECT_ID = os.getenv("PLANE_PROJECT_ID", "")

# Priority mapping: our system -> Plane
PRIORITY_MAP = {
    "urgent": "urgent",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "none",
}

# Status mapping: our system -> Plane state groups
STATUS_MAP = {
    "backlog": "backlog",
    "todo": "unstarted",
    "in_progress": "started",
    "done": "completed",
    "cancelled": "cancelled",
}


def _get_plane_headers() -> dict:
    """Get authorization headers for Plane API."""
    if not PLANE_API_KEY:
        logger.warning("PLANE_API_KEY not configured, Plane integration will use mock data")
        return {}
    return {
        "X-API-Key": PLANE_API_KEY,
        "Content-Type": "application/json",
    }


def _plane_url(path: str) -> str:
    """Build a Plane API URL."""
    return f"{PLANE_API_BASE}/workspaces/{PLANE_WORKSPACE_SLUG}/projects/{PLANE_PROJECT_ID}{path}"


# --- In-memory store for demo mode when Plane is not configured ---
_demo_tickets: list[dict] = [
    {
        "id": "TICKET-001",
        "title": "Customer 360 ETL pipeline failing on PostgreSQL connection timeout",
        "description": (
            "The Customer 360 ETL pipeline has been intermittently failing due to "
            "PostgreSQL connection timeouts. The issue started after the latest "
            "database maintenance window."
        ),
        "status": "in_progress",
        "priority": "high",
        "assignee": "data-team@company.com",
        "labels": ["bug", "data-pipeline"],
        "created_at": "2026-02-27T14:30:00Z",
        "updated_at": "2026-02-28T09:15:00Z",
    },
    {
        "id": "TICKET-002",
        "title": "Add streaming response support to AI Chat in production",
        "description": (
            "Enable SSE streaming for AI chat responses in the production environment. "
            "Currently only enabled in Dev and QA."
        ),
        "status": "todo",
        "priority": "medium",
        "assignee": "ml-engineer@company.com",
        "labels": ["feature-request", "ai-agent"],
        "created_at": "2026-02-26T10:00:00Z",
        "updated_at": "2026-02-26T10:00:00Z",
    },
    {
        "id": "TICKET-003",
        "title": "Manufacturing QA Agent latency exceeds SLA threshold",
        "description": (
            "The Manufacturing QA Agent has average latency of 1200ms, exceeding the "
            "1000ms SLA. Need to investigate model performance and optimize prompts."
        ),
        "status": "in_progress",
        "priority": "urgent",
        "assignee": "ml-engineer@company.com",
        "labels": ["performance", "ai-agent"],
        "created_at": "2026-02-28T08:00:00Z",
        "updated_at": "2026-02-28T11:30:00Z",
    },
    {
        "id": "TICKET-004",
        "title": "Set up auto-scaling for App Service production instances",
        "description": (
            "Configure auto-scaling rules for the production App Service plan "
            "based on CPU and memory metrics."
        ),
        "status": "backlog",
        "priority": "medium",
        "assignee": "platform@company.com",
        "labels": ["infrastructure"],
        "created_at": "2026-02-25T16:00:00Z",
        "updated_at": "2026-02-25T16:00:00Z",
    },
    {
        "id": "TICKET-005",
        "title": "Implement pgvector index optimization for semantic search",
        "description": (
            "The current IVFFlat index on the embeddings table needs to be replaced "
            "with HNSW for better recall at scale."
        ),
        "status": "done",
        "priority": "high",
        "assignee": "data-team@company.com",
        "labels": ["performance", "data-pipeline"],
        "created_at": "2026-02-20T09:00:00Z",
        "updated_at": "2026-02-27T17:00:00Z",
    },
]

_next_ticket_number = 6


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    status: str | None = Query(None, description="Filter by status"),
    priority: str | None = Query(None, description="Filter by priority"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of tickets"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """
    List tickets from Plane project management.

    Supports filtering by status and priority, with pagination.
    Falls back to demo data when Plane API is not configured.
    """
    if PLANE_API_KEY:
        # Call Plane API
        try:
            params = {"limit": limit, "offset": offset}
            if status:
                params["state_group"] = STATUS_MAP.get(status, status)
            if priority:
                params["priority"] = PRIORITY_MAP.get(priority, priority)

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    _plane_url("/issues/"),
                    headers=_get_plane_headers(),
                    params=params,
                )
                response.raise_for_status()

            data = response.json()
            issues = data.get("results", data) if isinstance(data, dict) else data

            tickets = [
                TicketResponse(
                    id=issue.get("identifier", issue.get("id", "")),
                    title=issue.get("name", ""),
                    description=issue.get("description_stripped", issue.get("description", "")),
                    status=_reverse_status_map(issue.get("state_detail", {}).get("group", "backlog")),
                    priority=issue.get("priority", "none"),
                    assignee=_get_assignee_name(issue.get("assignee_detail")),
                    labels=[l.get("name", "") for l in issue.get("label_detail", [])],
                    created_at=issue.get("created_at", ""),
                    updated_at=issue.get("updated_at", ""),
                )
                for issue in issues
            ]

            return TicketListResponse(
                tickets=tickets,
                total=data.get("total_count", len(tickets)) if isinstance(data, dict) else len(tickets),
                limit=limit,
                offset=offset,
            )
        except httpx.HTTPError as e:
            logger.error(f"Plane API request failed: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Plane API communication failed: {str(e)}")
    else:
        # Demo mode
        filtered = _demo_tickets.copy()
        if status:
            filtered = [t for t in filtered if t["status"] == status]
        if priority:
            filtered = [t for t in filtered if t["priority"] == priority]

        paginated = filtered[offset : offset + limit]

        return TicketListResponse(
            tickets=[TicketResponse(**t) for t in paginated],
            total=len(filtered),
            limit=limit,
            offset=offset,
        )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: str):
    """Get a specific ticket by ID."""
    if PLANE_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(
                    _plane_url(f"/issues/{ticket_id}/"),
                    headers=_get_plane_headers(),
                )
                response.raise_for_status()

            issue = response.json()
            return TicketResponse(
                id=issue.get("identifier", issue.get("id", "")),
                title=issue.get("name", ""),
                description=issue.get("description_stripped", issue.get("description", "")),
                status=_reverse_status_map(issue.get("state_detail", {}).get("group", "backlog")),
                priority=issue.get("priority", "none"),
                assignee=_get_assignee_name(issue.get("assignee_detail")),
                labels=[l.get("name", "") for l in issue.get("label_detail", [])],
                created_at=issue.get("created_at", ""),
                updated_at=issue.get("updated_at", ""),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
            raise HTTPException(status_code=502, detail=f"Plane API error: {str(e)}")
    else:
        ticket = next((t for t in _demo_tickets if t["id"] == ticket_id), None)
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
        return TicketResponse(**ticket)


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket(request: CreateTicketRequest):
    """
    Create a new ticket in Plane.

    Automatically assigns default project labels and notifies
    via Slack when configured.
    """
    global _next_ticket_number

    if PLANE_API_KEY:
        try:
            payload = {
                "name": request.title,
                "description": request.description or "",
                "priority": PRIORITY_MAP.get(request.priority, "medium"),
            }

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    _plane_url("/issues/"),
                    headers=_get_plane_headers(),
                    json=payload,
                )
                response.raise_for_status()

            issue = response.json()
            logger.info(f"Created Plane issue: {issue.get('identifier', issue.get('id'))}")

            return TicketResponse(
                id=issue.get("identifier", issue.get("id", "")),
                title=issue.get("name", ""),
                description=issue.get("description_stripped", issue.get("description", "")),
                status="backlog",
                priority=issue.get("priority", "medium"),
                labels=request.labels or [],
                created_at=issue.get("created_at", datetime.utcnow().isoformat()),
                updated_at=issue.get("updated_at", datetime.utcnow().isoformat()),
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to create Plane issue: {e}", exc_info=True)
            raise HTTPException(status_code=502, detail=f"Failed to create ticket in Plane: {str(e)}")
    else:
        # Demo mode
        ticket_id = f"TICKET-{_next_ticket_number:03d}"
        _next_ticket_number += 1

        now = datetime.utcnow().isoformat() + "Z"
        new_ticket = {
            "id": ticket_id,
            "title": request.title,
            "description": request.description or "",
            "status": "backlog",
            "priority": request.priority,
            "labels": request.labels or [],
            "created_at": now,
            "updated_at": now,
        }
        _demo_tickets.insert(0, new_ticket)
        logger.info(f"Created demo ticket: {ticket_id}")

        return TicketResponse(**new_ticket)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(ticket_id: str, request: UpdateTicketRequest):
    """Update an existing ticket."""
    if PLANE_API_KEY:
        try:
            payload = {}
            if request.title is not None:
                payload["name"] = request.title
            if request.description is not None:
                payload["description"] = request.description
            if request.status is not None:
                payload["state_group"] = STATUS_MAP.get(request.status, request.status)
            if request.priority is not None:
                payload["priority"] = PRIORITY_MAP.get(request.priority, request.priority)

            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.patch(
                    _plane_url(f"/issues/{ticket_id}/"),
                    headers=_get_plane_headers(),
                    json=payload,
                )
                response.raise_for_status()

            issue = response.json()
            return TicketResponse(
                id=issue.get("identifier", issue.get("id", "")),
                title=issue.get("name", ""),
                description=issue.get("description_stripped", issue.get("description", "")),
                status=_reverse_status_map(issue.get("state_detail", {}).get("group", "backlog")),
                priority=issue.get("priority", "none"),
                assignee=_get_assignee_name(issue.get("assignee_detail")),
                labels=[l.get("name", "") for l in issue.get("label_detail", [])],
                created_at=issue.get("created_at", ""),
                updated_at=issue.get("updated_at", ""),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")
            raise HTTPException(status_code=502, detail=f"Plane API error: {str(e)}")
    else:
        # Demo mode
        ticket = next((t for t in _demo_tickets if t["id"] == ticket_id), None)
        if not ticket:
            raise HTTPException(status_code=404, detail=f"Ticket '{ticket_id}' not found")

        if request.title is not None:
            ticket["title"] = request.title
        if request.description is not None:
            ticket["description"] = request.description
        if request.status is not None:
            ticket["status"] = request.status
        if request.priority is not None:
            ticket["priority"] = request.priority
        if request.labels is not None:
            ticket["labels"] = request.labels
        ticket["updated_at"] = datetime.utcnow().isoformat() + "Z"

        return TicketResponse(**ticket)


# --- Helper functions ---

def _reverse_status_map(state_group: str) -> str:
    """Map Plane state group back to our status."""
    reverse_map = {v: k for k, v in STATUS_MAP.items()}
    return reverse_map.get(state_group, "backlog")


def _get_assignee_name(assignee_detail: dict | list | None) -> str | None:
    """Extract assignee name from Plane assignee detail."""
    if not assignee_detail:
        return None
    if isinstance(assignee_detail, list) and len(assignee_detail) > 0:
        return assignee_detail[0].get("display_name", assignee_detail[0].get("email"))
    if isinstance(assignee_detail, dict):
        return assignee_detail.get("display_name", assignee_detail.get("email"))
    return None
