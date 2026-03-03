"""
PostgreSQL MCP Server for Azure Data Platform.

Exposes PostgreSQL databases (manufacturing_db, vector_db, sales_db)
as MCP resources and tools so any AI agent can query them without
custom tool code.

Run:
    pg-mcp-server                    (via pyproject entry point)
    python -m pg_mcp_server.server   (direct)
    mcp dev src/pg_mcp_server/server.py  (MCP inspector)
"""

import asyncio
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal

import asyncpg
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    GetPromptResult,
    Prompt,
    PromptArgument,
    PromptMessage,
    Resource,
    TextContent,
    Tool,
)

from pg_mcp_server.config import ServerConfig

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pg-mcp-server")

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
config = ServerConfig()
pools: dict[str, asyncpg.Pool] = {}
server = Server("pg-mcp-server")

# SQL keywords that are NOT allowed (read-only enforcement)
BLOCKED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "COPY", "EXECUTE", "CALL",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_default(obj):
    """JSON serializer for types not handled by default."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, bytes):
        return obj.hex()
    return str(obj)


def _format_rows(rows: list[asyncpg.Record], max_rows: int = 500) -> str:
    """Format query results as a readable markdown table."""
    if not rows:
        return "_No rows returned._"

    columns = list(rows[0].keys())
    truncated = rows[:max_rows]

    # Build markdown table
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]

    for row in truncated:
        values = []
        for col in columns:
            val = row[col]
            if val is None:
                values.append("")
            elif isinstance(val, (dict, list)):
                values.append(json.dumps(val, default=_json_default)[:100])
            else:
                s = str(val)
                values.append(s[:100] if len(s) > 100 else s)
        lines.append("| " + " | ".join(values) + " |")

    result = "\n".join(lines)
    if len(rows) > max_rows:
        result += f"\n\n_Showing {max_rows} of {len(rows)} rows._"
    return result


def _validate_sql(sql: str) -> str | None:
    """Validate SQL is read-only. Returns error message or None if valid."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return "Empty query."

    first_word = stripped.split()[0].upper()
    if first_word not in ("SELECT", "WITH", "EXPLAIN"):
        return f"Only SELECT/WITH/EXPLAIN queries are allowed. Got: {first_word}"

    tokens = set(stripped.upper().split())
    blocked = tokens & BLOCKED_KEYWORDS
    if blocked:
        return f"Blocked keywords detected: {', '.join(blocked)}"

    return None


async def _get_pool(database: str) -> asyncpg.Pool:
    """Get or create a connection pool for a database."""
    if database not in pools:
        pools[database] = await asyncpg.create_pool(
            host=config.pg_host,
            port=config.pg_port,
            user=config.pg_user,
            password=config.pg_password,
            database=database,
            ssl="require" if config.pg_sslmode == "require" else None,
            min_size=config.pool_min_size,
            max_size=config.pool_max_size,
        )
        logger.info(f"Pool created for database: {database}")
    return pools[database]


# ---------------------------------------------------------------------------
# Resources — table schemas that agents can read for context
# ---------------------------------------------------------------------------

@server.list_resources()
async def list_resources() -> list[Resource]:
    """List all tables across all databases as resources."""
    resources = []
    for db_name in config.databases:
        try:
            pool = await _get_pool(db_name)
            async with pool.acquire() as conn:
                tables = await conn.fetch(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                )
                for row in tables:
                    table = row["table_name"]
                    resources.append(Resource(
                        uri=f"postgres://{config.pg_host}/{db_name}/{table}",
                        name=f"{db_name}.{table}",
                        description=f"Table '{table}' in database '{db_name}'",
                        mimeType="application/json",
                    ))
        except Exception as e:
            logger.warning(f"Could not list tables for {db_name}: {e}")
    return resources


@server.read_resource()
async def read_resource(uri: str) -> str:
    """Read a table's schema: columns, types, row count, sample data."""
    parts = uri.replace("postgres://", "").split("/")
    if len(parts) < 3:
        return f"Invalid resource URI: {uri}"

    db_name, table = parts[1], parts[2]
    pool = await _get_pool(db_name)

    async with pool.acquire() as conn:
        # Column info
        columns = await conn.fetch(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position",
            table,
        )

        # Row count
        count = await conn.fetchval(f"SELECT count(*) FROM \"{table}\"")

        # Sample rows
        sample = await conn.fetch(f"SELECT * FROM \"{table}\" LIMIT 3")

    schema_info = {
        "database": db_name,
        "table": table,
        "row_count": count,
        "columns": [
            {
                "name": c["column_name"],
                "type": c["data_type"],
                "nullable": c["is_nullable"] == "YES",
                "default": c["column_default"],
            }
            for c in columns
        ],
        "sample_rows": [dict(r) for r in sample] if sample else [],
    }

    return json.dumps(schema_info, indent=2, default=_json_default)


# ---------------------------------------------------------------------------
# Tools — query, search_embeddings, list_tables
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return available tools."""
    return [
        Tool(
            name="query",
            description=(
                "Execute a read-only SQL query against a PostgreSQL database. "
                "Supports SELECT and WITH (CTE) queries. "
                "Available databases: manufacturing_db (equipment, IoT, lifecycle), "
                "vector_db (document embeddings), sales_db (future)."
            ),
            inputSchema={
                "type": "object",
                "required": ["sql", "database"],
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "SQL SELECT query to execute",
                    },
                    "database": {
                        "type": "string",
                        "description": "Target database name",
                        "enum": config.databases,
                    },
                },
            },
        ),
        Tool(
            name="search_documents",
            description=(
                "Search document embeddings using full-text keyword search. "
                "Searches the document_embeddings table in vector_db. "
                "Filter by document_type: equipment_health, customer_360, product_catalog."
            ),
            inputSchema={
                "type": "object",
                "required": ["query", "document_type"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query",
                    },
                    "document_type": {
                        "type": "string",
                        "description": "Type of document to search",
                        "enum": ["equipment_health", "customer_360", "product_catalog"],
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5,
                    },
                },
            },
        ),
        Tool(
            name="list_tables",
            description="List all tables and their row counts in a database.",
            inputSchema={
                "type": "object",
                "required": ["database"],
                "properties": {
                    "database": {
                        "type": "string",
                        "enum": config.databases,
                    },
                },
            },
        ),
        Tool(
            name="describe_table",
            description="Get column names, types, and sample data for a table.",
            inputSchema={
                "type": "object",
                "required": ["database", "table"],
                "properties": {
                    "database": {
                        "type": "string",
                        "enum": config.databases,
                    },
                    "table": {
                        "type": "string",
                        "description": "Table name",
                    },
                },
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a tool call."""

    if name == "query":
        return await _tool_query(arguments)
    elif name == "search_documents":
        return await _tool_search_documents(arguments)
    elif name == "list_tables":
        return await _tool_list_tables(arguments)
    elif name == "describe_table":
        return await _tool_describe_table(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _tool_query(args: dict) -> list[TextContent]:
    """Execute a read-only SQL query."""
    sql = args.get("sql", "")
    database = args.get("database", "")

    # Validate
    error = _validate_sql(sql)
    if error:
        return [TextContent(type="text", text=f"Query rejected: {error}")]

    if database not in config.databases:
        return [TextContent(type="text", text=f"Unknown database: {database}. Available: {config.databases}")]

    try:
        pool = await _get_pool(database)
        async with pool.acquire() as conn:
            # Set statement timeout (10 seconds) to prevent long-running queries
            await conn.execute("SET statement_timeout = '10s'")
            rows = await conn.fetch(sql)

        result = _format_rows(rows, max_rows=config.max_rows)
        return [TextContent(type="text", text=f"Query returned {len(rows)} rows:\n\n{result}")]

    except asyncpg.PostgresError as e:
        return [TextContent(type="text", text=f"SQL error: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _tool_search_documents(args: dict) -> list[TextContent]:
    """Search document embeddings using full-text search."""
    query = args.get("query", "")
    doc_type = args.get("document_type", "")
    top_k = min(args.get("top_k", 5), 20)

    try:
        pool = await _get_pool("vector_db")
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT document_id, content, metadata, source_file,
                       ts_rank_cd(content_tsv, plainto_tsquery('english', $1)) AS score
                FROM document_embeddings
                WHERE document_type = $2
                  AND content_tsv @@ plainto_tsquery('english', $1)
                ORDER BY score DESC
                LIMIT $3
                """,
                query, doc_type, top_k,
            )

        if not rows:
            return [TextContent(type="text", text=f"No results found for '{query}' in {doc_type} documents.")]

        results = []
        for i, row in enumerate(rows, 1):
            meta = json.loads(row["metadata"]) if row["metadata"] else {}
            results.append(
                f"### Result {i} (score: {row['score']:.4f})\n"
                f"**Document:** {row['document_id']} | **Source:** {row['source_file']}\n"
                f"**Metadata:** {json.dumps(meta, default=str)}\n\n"
                f"{row['content'][:500]}\n"
            )

        return [TextContent(type="text", text="\n---\n".join(results))]

    except Exception as e:
        return [TextContent(type="text", text=f"Search error: {e}")]


async def _tool_list_tables(args: dict) -> list[TextContent]:
    """List tables with row counts."""
    database = args.get("database", "")

    try:
        pool = await _get_pool(database)
        async with pool.acquire() as conn:
            tables = await conn.fetch(
                """
                SELECT t.table_name,
                       pg_stat_user_tables.n_live_tup AS row_count
                FROM information_schema.tables t
                LEFT JOIN pg_stat_user_tables ON t.table_name = pg_stat_user_tables.relname
                WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
                ORDER BY t.table_name
                """
            )

        lines = [f"Tables in **{database}**:\n"]
        lines.append("| Table | Rows |")
        lines.append("|---|---:|")
        for t in tables:
            lines.append(f"| {t['table_name']} | {t['row_count'] or 0:,} |")

        return [TextContent(type="text", text="\n".join(lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


async def _tool_describe_table(args: dict) -> list[TextContent]:
    """Describe a table's schema and show sample data."""
    database = args.get("database", "")
    table = args.get("table", "")

    try:
        pool = await _get_pool(database)
        async with pool.acquire() as conn:
            columns = await conn.fetch(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=$1 "
                "ORDER BY ordinal_position",
                table,
            )
            count = await conn.fetchval(f'SELECT count(*) FROM "{table}"')
            sample = await conn.fetch(f'SELECT * FROM "{table}" LIMIT 3')

        lines = [f"## {database}.{table} ({count:,} rows)\n"]
        lines.append("| Column | Type | Nullable |")
        lines.append("|---|---|---|")
        for c in columns:
            lines.append(f"| {c['column_name']} | {c['data_type']} | {c['is_nullable']} |")

        if sample:
            lines.append(f"\n### Sample Data ({min(3, count)} rows)\n")
            lines.append(_format_rows(sample))

        return [TextContent(type="text", text="\n".join(lines))]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {e}")]


# ---------------------------------------------------------------------------
# Prompts — reusable prompt templates for common queries
# ---------------------------------------------------------------------------

@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    """Return available prompt templates."""
    return [
        Prompt(
            name="analyze_equipment",
            description="Analyze equipment health status with sensor data and anomalies",
            arguments=[
                PromptArgument(name="equipment_id", description="Equipment ID (e.g., EQ-1100-A-006)", required=True),
            ],
        ),
        Prompt(
            name="fleet_overview",
            description="Get an overview of equipment fleet health by plant or risk level",
            arguments=[
                PromptArgument(name="plant_code", description="Plant code to filter (optional)", required=False),
            ],
        ),
        Prompt(
            name="investigate_anomalies",
            description="Investigate recent sensor anomalies for an equipment",
            arguments=[
                PromptArgument(name="equipment_id", description="Equipment ID", required=True),
                PromptArgument(name="days_back", description="Number of days to look back (default: 30)", required=False),
            ],
        ),
    ]


@server.get_prompt()
async def get_prompt(name: str, arguments: dict | None = None) -> GetPromptResult:
    """Return a prompt template with context."""
    args = arguments or {}

    if name == "analyze_equipment":
        eq_id = args.get("equipment_id", "EQ-1100-A-006")
        return GetPromptResult(
            description=f"Analyze equipment {eq_id}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Analyze the health of equipment **{eq_id}**.\n\n"
                            "Steps:\n"
                            f"1. Query the equipment_health table for {eq_id}\n"
                            f"2. Get recent sensor readings from iot_telemetry for {eq_id}\n"
                            f"3. Check for anomalies (quality_flag != 'GOOD')\n"
                            f"4. Search maintenance docs for {eq_id}\n"
                            "5. Provide a summary with health score, risk factors, and recommended actions"
                        ),
                    ),
                ),
            ],
        )

    elif name == "fleet_overview":
        plant = args.get("plant_code", "")
        filter_clause = f" for plant {plant}" if plant else " across all plants"
        return GetPromptResult(
            description=f"Fleet overview{filter_clause}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Provide a fleet health overview{filter_clause}.\n\n"
                            "Steps:\n"
                            "1. Query equipment_health grouped by failure_risk to get counts\n"
                            "2. List top 5 highest-risk equipment\n"
                            "3. Show average health score by plant\n"
                            "4. Summarize with actionable recommendations"
                        ),
                    ),
                ),
            ],
        )

    elif name == "investigate_anomalies":
        eq_id = args.get("equipment_id", "EQ-1100-A-006")
        days = args.get("days_back", "30")
        return GetPromptResult(
            description=f"Investigate anomalies for {eq_id}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=(
                            f"Investigate sensor anomalies for equipment **{eq_id}** "
                            f"over the last {days} days.\n\n"
                            "Steps:\n"
                            f"1. Query iot_telemetry for {eq_id} where quality_flag != 'GOOD'\n"
                            "2. Group anomalies by sensor_type and count them\n"
                            "3. Show the timeline of anomalies\n"
                            "4. Search maintenance docs for relevant troubleshooting guides\n"
                            "5. Recommend actions based on the anomaly patterns"
                        ),
                    ),
                ),
            ],
        )

    return GetPromptResult(
        description="Unknown prompt",
        messages=[
            PromptMessage(
                role="user",
                content=TextContent(type="text", text=f"Unknown prompt: {name}"),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

async def run():
    """Start the MCP server on stdio."""
    logger.info(f"Starting pg-mcp-server (host={config.pg_host}, databases={config.databases})")

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )

    # Cleanup pools
    for db_name, pool in pools.items():
        await pool.close()
        logger.info(f"Pool closed for {db_name}")


def main():
    """Entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
