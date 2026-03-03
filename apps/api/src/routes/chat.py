"""
Chat Route - Proxies chat requests to AI Foundry agents.
Supports both standard request/response and streaming via SSE.
"""

import logging
import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest, ChatResponse, ChatStreamEvent
from services.ai_service import AIFoundryService
from services.agent_executor import AgentExecutor

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize AI service (singleton)
ai_service = AIFoundryService()

# Agent-to-deployment mapping
AGENT_DEPLOYMENTS = {
    "sales-forecast-agent": {
        "deployment_name": "gpt-4o",
        "system_prompt": (
            "You are a sales forecasting analyst. Analyze historical sales data, "
            "seasonal trends, and market indicators to provide accurate demand forecasts. "
            "Always cite your data sources and provide confidence intervals for predictions. "
            "Format numerical outputs in tables when appropriate."
        ),
        "temperature": 0.3,
        "max_tokens": 2048,
    },
    "customer-support-agent": {
        "deployment_name": "gpt-4o",
        "system_prompt": (
            "You are a customer support assistant for a manufacturing and sales company. "
            "Help customers with order inquiries, product information, warranty claims, "
            "and technical support. Be empathetic, concise, and always confirm understanding "
            "before providing solutions. Escalate to human agents when confidence is low."
        ),
        "temperature": 0.5,
        "max_tokens": 1024,
    },
    "manufacturing-qa-agent": {
        "deployment_name": "gpt-4o-mini",
        "system_prompt": (
            "You are a manufacturing quality assurance specialist. Analyze sensor data, "
            "production metrics, and quality control reports to identify defects, predict "
            "equipment failures, and recommend corrective actions. Provide structured "
            "reports with severity classifications and root cause analysis."
        ),
        "temperature": 0.2,
        "max_tokens": 4096,
    },
    "inventory-optimization-agent": {
        "deployment_name": "gpt-4o-mini",
        "system_prompt": (
            "You are an inventory optimization specialist. Analyze stock levels, "
            "reorder points, lead times, and demand patterns to recommend optimal "
            "inventory strategies. Consider carrying costs, stockout risks, and "
            "supplier reliability. Provide actionable recommendations with expected ROI."
        ),
        "temperature": 0.3,
        "max_tokens": 2048,
    },
    "equipment-health-agent": {
        "deployment_name": "gpt-4o",
        "system_prompt_file": "ai/prompts/system/equipment_health.md",
        "temperature": 0.1,
        "max_tokens": 4096,
        "tools": True,  # Uses function-calling tools via AgentExecutor
        "mcp_server": "pg",  # Prefer PostgreSQL MCP server for tool discovery
    },
}


# Tool definitions for equipment-health-agent
EQUIPMENT_HEALTH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_equipment_status",
            "description": "Get current health status for a specific equipment including health score, failure risk, estimated remaining useful life, and recommended actions.",
            "parameters": {
                "type": "object",
                "required": ["equipment_id"],
                "properties": {
                    "equipment_id": {"type": "string", "description": "Equipment identifier (e.g., EQ-1100-A-001)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_equipment_by_risk",
            "description": "List equipment filtered by failure risk level, sorted by failure probability.",
            "parameters": {
                "type": "object",
                "required": ["risk_level"],
                "properties": {
                    "risk_level": {"type": "string", "enum": ["Low", "Medium", "High", "Critical"]},
                    "plant_code": {"type": "string", "description": "Optional plant code filter"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sensor_readings",
            "description": "Get recent sensor readings for an equipment (temperature, pressure, vibration, etc.).",
            "parameters": {
                "type": "object",
                "required": ["equipment_id"],
                "properties": {
                    "equipment_id": {"type": "string"},
                    "sensor_type": {"type": "string", "enum": ["temperature", "pressure", "vibration", "humidity", "flow_rate", "power"]},
                    "hours_back": {"type": "integer", "default": 24},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_maintenance_docs",
            "description": "Search equipment health documents using semantic and keyword search.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Natural language search query"},
                    "equipment_id": {"type": "string"},
                    "top_k": {"type": "integer", "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_equipment_anomalies",
            "description": "Find anomalous sensor readings for an equipment (BAD or UNCERTAIN quality flags).",
            "parameters": {
                "type": "object",
                "required": ["equipment_id"],
                "properties": {
                    "equipment_id": {"type": "string"},
                    "days_back": {"type": "integer", "default": 30},
                    "sensor_type": {"type": "string", "enum": ["temperature", "pressure", "vibration", "humidity", "flow_rate", "power"]},
                },
            },
        },
    },
]


def _get_agent_config(agent_id: str) -> dict:
    """Get the deployment configuration for an agent."""
    config = AGENT_DEPLOYMENTS.get(agent_id)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Agent '{agent_id}' not found. Available agents: {list(AGENT_DEPLOYMENTS.keys())}",
        )
    return config


def _load_system_prompt(agent_config: dict) -> str:
    """Load the system prompt, either inline or from a file."""
    if "system_prompt_file" in agent_config:
        prompt_path = Path(__file__).resolve().parent.parent.parent.parent.parent / agent_config["system_prompt_file"]
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        logger.warning(f"System prompt file not found: {prompt_path}, using fallback")
    return agent_config.get("system_prompt", "You are a helpful assistant.")


def _build_messages(agent_config: dict, user_messages: list[dict]) -> list[dict]:
    """Build the full message list including system prompt."""
    system_prompt = _load_system_prompt(agent_config)
    messages = [
        {"role": "system", "content": system_prompt},
    ]
    for msg in user_messages:
        messages.append({"role": msg["role"], "content": msg["content"]})
    return messages


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, raw_request: Request):
    """
    Send a chat message to an AI agent and get a response.

    If `stream` is True, returns a Server-Sent Events stream.
    Otherwise, returns a complete JSON response.
    Tool-calling agents (like equipment-health-agent) use the AgentExecutor loop.
    """
    agent_config = _get_agent_config(request.agent_id)
    messages = _build_messages(agent_config, [m.model_dump() for m in request.messages])

    # Tool-calling agent path (equipment-health-agent)
    if agent_config.get("tools"):
        return await _handle_tool_agent(raw_request, agent_config, messages, request.agent_id)

    if request.stream:
        return StreamingResponse(
            _stream_response(agent_config, messages),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming response
    try:
        result = await ai_service.chat_completion(
            deployment_name=agent_config["deployment_name"],
            messages=messages,
            temperature=agent_config["temperature"],
            max_tokens=agent_config["max_tokens"],
            stream=False,
        )

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = result.get("usage", {})

        # Extract citations from knowledge base (if applicable)
        citations = _extract_citations(content)

        return ChatResponse(
            id=result.get("id", ""),
            content=content,
            agent_id=request.agent_id,
            model=agent_config["deployment_name"],
            citations=citations,
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=result.get("choices", [{}])[0].get("finish_reason", "stop"),
        )
    except Exception as e:
        logger.error(f"Chat completion failed for agent '{request.agent_id}': {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI agent communication failed: {str(e)}")


async def _handle_tool_agent(
    raw_request: Request, agent_config: dict, messages: list[dict], agent_id: str
) -> ChatResponse:
    """
    Handle agents that use function-calling tools via AgentExecutor.

    Prefers MCP server (dynamic tool discovery) when available,
    falls back to direct EquipmentTools handlers.
    """
    tools: list[dict] | None = None
    tool_handlers: dict | None = None

    # --- Path 1: MCP server (preferred) ---
    mcp_key = agent_config.get("mcp_server")
    if mcp_key:
        from services.mcp_client import MCPClient

        mcp_client: MCPClient | None = getattr(
            raw_request.app.state, f"mcp_{mcp_key}", None
        )
        if mcp_client and mcp_client.connected:
            tools = mcp_client.get_openai_tools()
            tool_handlers = mcp_client.get_tool_handlers()
            logger.info(f"Agent '{agent_id}' using MCP server (tools: {mcp_client.tool_names})")

    # --- Path 2: Direct tool handlers (fallback) ---
    if tool_handlers is None:
        from services.equipment_tools import EquipmentTools

        equipment_tools: EquipmentTools | None = getattr(
            raw_request.app.state, "equipment_tools", None
        )

        if equipment_tools is None:
            raise HTTPException(
                status_code=503,
                detail="No tool backend available. Neither MCP server nor direct tools are initialized.",
            )

        tools = EQUIPMENT_HEALTH_TOOLS
        tool_handlers = {
            "get_equipment_status": equipment_tools.get_equipment_status,
            "list_equipment_by_risk": equipment_tools.list_equipment_by_risk,
            "get_sensor_readings": equipment_tools.get_sensor_readings,
            "search_maintenance_docs": equipment_tools.search_maintenance_docs,
            "get_equipment_anomalies": equipment_tools.get_equipment_anomalies,
        }
        logger.info(f"Agent '{agent_id}' using direct tool handlers (fallback)")

    executor = AgentExecutor(ai_service=ai_service, tool_handlers=tool_handlers)

    try:
        result = await executor.run(
            deployment_name=agent_config["deployment_name"],
            messages=messages,
            tools=tools,
            temperature=agent_config["temperature"],
            max_tokens=agent_config["max_tokens"],
        )

        citations = _extract_citations(result["content"])

        return ChatResponse(
            id="",
            content=result["content"],
            agent_id=agent_id,
            model=agent_config["deployment_name"],
            citations=citations,
            usage=result["usage"],
            finish_reason="stop",
        )
    except Exception as e:
        logger.error(f"Tool agent failed for '{agent_id}': {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"AI agent communication failed: {str(e)}")


async def _stream_response(
    agent_config: dict, messages: list[dict]
) -> AsyncGenerator[str, None]:
    """Generate SSE stream from AI Foundry streaming response."""
    try:
        async for chunk in ai_service.chat_completion_stream(
            deployment_name=agent_config["deployment_name"],
            messages=messages,
            temperature=agent_config["temperature"],
            max_tokens=agent_config["max_tokens"],
        ):
            if chunk.get("type") == "content":
                event = ChatStreamEvent(type="content", content=chunk["content"])
                yield f"data: {event.model_dump_json()}\n\n"
            elif chunk.get("type") == "done":
                # Send citations before done signal
                citations = _extract_citations(chunk.get("full_content", ""))
                if citations:
                    cite_event = json.dumps({"type": "citations", "citations": [c.model_dump() for c in citations]})
                    yield f"data: {cite_event}\n\n"
                yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        error_event = json.dumps({"type": "error", "message": str(e)})
        yield f"data: {error_event}\n\n"
        yield "data: [DONE]\n\n"


def _extract_citations(content: str) -> list:
    """
    Extract citations from response content.
    In production, this would query the knowledge base index used during RAG.
    """
    from models.schemas import CitationSchema

    # Placeholder citations based on content analysis
    citations = []
    if any(keyword in content.lower() for keyword in ["sales", "revenue", "forecast", "order"]):
        citations.append(
            CitationSchema(
                title="Sales Database - Q1 2026",
                source="Fabric Lakehouse",
                url="/data/sales-lakehouse",
            )
        )
    if any(keyword in content.lower() for keyword in ["manufacturing", "defect", "sensor", "quality"]):
        citations.append(
            CitationSchema(
                title="Manufacturing Telemetry Data",
                source="IoT Hub / Fabric Lakehouse",
                url="/data/manufacturing-lakehouse",
            )
        )
    if any(keyword in content.lower() for keyword in ["inventory", "stock", "reorder", "warehouse"]):
        citations.append(
            CitationSchema(
                title="Inventory Management System",
                source="WMS API / Fabric Lakehouse",
                url="/data/inventory-lakehouse",
            )
        )
    return citations
