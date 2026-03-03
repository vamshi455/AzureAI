"""Configuration for the PostgreSQL MCP server."""

import os
from dataclasses import dataclass, field


@dataclass
class ServerConfig:
    """PostgreSQL connection and server configuration."""

    pg_host: str = os.getenv("PGHOST", "localhost")
    pg_port: int = int(os.getenv("PGPORT", "5432"))
    pg_user: str = os.getenv("PGUSER", "postgres")
    pg_password: str = os.getenv("PGPASSWORD", "")
    pg_sslmode: str = os.getenv("PGSSLMODE", "require")

    # Databases available to agents
    databases: list[str] = field(
        default_factory=lambda: os.getenv(
            "PG_DATABASES", "manufacturing_db,vector_db,sales_db"
        ).split(",")
    )

    pool_min_size: int = 2
    pool_max_size: int = 5

    # Safety: max rows returned per query
    max_rows: int = 500
