"""
MCP Client — connects to MCP servers via stdio and provides tool handlers
compatible with the AgentExecutor.

This lets any agent use tools from MCP servers (like pg-mcp-server) without
hardcoded tool implementations. Tools are discovered dynamically at startup.
"""

import logging
import os
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPClient:
    """
    Long-lived connection to an MCP server via stdio transport.

    Usage:
        client = MCPClient("pg-mcp-server")
        await client.connect()
        tools = client.get_openai_tools()      # OpenAI function-calling format
        handlers = client.get_tool_handlers()   # for AgentExecutor
        ...
        await client.disconnect()
    """

    def __init__(
        self,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
    ):
        self._server_params = StdioServerParameters(
            command=command,
            args=args or [],
            env=env,
        )
        self._session: ClientSession | None = None
        self._stdio_cm = None
        self._session_cm = None
        self._tools = []

    async def connect(self):
        """Start the MCP server subprocess and initialize the session."""
        self._stdio_cm = stdio_client(self._server_params)
        read, write = await self._stdio_cm.__aenter__()

        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()

        # Discover available tools
        result = await self._session.list_tools()
        self._tools = result.tools
        logger.info(
            f"MCP connected ({self._server_params.command}): "
            f"{len(self._tools)} tools — {[t.name for t in self._tools]}"
        )

    async def disconnect(self):
        """Shut down session and server process."""
        try:
            if self._session_cm:
                await self._session_cm.__aexit__(None, None, None)
            if self._stdio_cm:
                await self._stdio_cm.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"MCP disconnect error: {e}")
        finally:
            self._session = None
            self._tools = []
            logger.info(f"MCP disconnected ({self._server_params.command})")

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def tool_names(self) -> list[str]:
        return [t.name for t in self._tools]

    def get_openai_tools(self) -> list[dict]:
        """Convert MCP tool schemas to OpenAI function-calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.inputSchema,
                },
            }
            for tool in self._tools
        ]

    def get_tool_handlers(self) -> dict[str, Any]:
        """Return tool_name → async handler dict for AgentExecutor."""
        return {tool.name: self._make_handler(tool.name) for tool in self._tools}

    def _make_handler(self, tool_name: str):
        """Create an async handler that proxies tool calls through MCP."""

        async def handler(**kwargs) -> dict:
            if not self._session:
                return {"error": "MCP session not connected"}
            try:
                result = await self._session.call_tool(tool_name, kwargs)
                texts = [c.text for c in result.content if hasattr(c, "text")]
                combined = "\n".join(texts)
                return {"result": combined} if combined else {"result": "No content returned."}
            except Exception as e:
                logger.error(f"MCP tool '{tool_name}' failed: {e}")
                return {"error": str(e)}

        return handler


def create_pg_mcp_client() -> MCPClient:
    """Create an MCPClient configured for the PostgreSQL MCP server."""
    # Merge parent env so subprocess has PATH, PYTHONPATH, etc.
    env = {**os.environ}
    env.update({
        "PGHOST": os.getenv("PGHOST", "dp-psql-dev.postgres.database.azure.com"),
        "PGPORT": os.getenv("PGPORT", "5432"),
        "PGUSER": os.getenv("PGUSER", "dpadmin"),
        "PGPASSWORD": os.getenv("PGPASSWORD", ""),
        "PGSSLMODE": os.getenv("PGSSLMODE", "require"),
        "PG_DATABASES": os.getenv("PG_DATABASES", "manufacturing_db,vector_db,sales_db"),
    })

    return MCPClient(
        command="pg-mcp-server",  # installed via pip install -e mcp-servers/postgresql
        env=env,
    )
