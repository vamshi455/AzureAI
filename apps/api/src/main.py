"""
Azure Data Platform - FastAPI Backend
Main application entry point with route registration, middleware, and health checks.
"""

import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import asyncpg

from routes.chat import router as chat_router
from routes.analytics import router as analytics_router
from routes.tickets import router as tickets_router
from services.equipment_tools import EquipmentTools
from services.mcp_client import MCPClient, create_pg_mcp_client

# --- Logging Configuration ---
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Application Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifecycle."""
    logger.info("Starting Azure Data Platform API...")
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")

    # Startup: initialize connections, warm up caches
    app.state.startup_time = datetime.utcnow()

    # Initialize PostgreSQL connection pool for equipment tools
    pg_conn_str = os.getenv("PGVECTOR_CONNECTION_STRING", "")
    pg_pool = None
    if pg_conn_str:
        try:
            pg_pool = await asyncpg.create_pool(pg_conn_str, min_size=2, max_size=10)
            app.state.pg_pool = pg_pool
            app.state.equipment_tools = EquipmentTools(pg_pool)
            logger.info("PostgreSQL pool initialized for equipment tools.")
        except Exception as e:
            logger.warning(f"Could not initialize PostgreSQL pool: {e}")
            app.state.equipment_tools = None
    else:
        logger.info("PGVECTOR_CONNECTION_STRING not set; equipment tools disabled.")
        app.state.equipment_tools = None

    # Initialize MCP client for PostgreSQL server
    mcp_pg: MCPClient | None = None
    if os.getenv("MCP_PG_ENABLED", "true").lower() == "true":
        try:
            mcp_pg = create_pg_mcp_client()
            await mcp_pg.connect()
            app.state.mcp_pg = mcp_pg
            logger.info(f"PostgreSQL MCP client ready — tools: {mcp_pg.tool_names}")
        except Exception as e:
            logger.warning(f"Could not start PostgreSQL MCP server: {e}")
            app.state.mcp_pg = None
    else:
        app.state.mcp_pg = None

    logger.info("Application startup complete.")

    yield

    # Shutdown: close connections, flush buffers
    logger.info("Shutting down Azure Data Platform API...")
    if mcp_pg:
        await mcp_pg.disconnect()
        logger.info("MCP PostgreSQL client disconnected.")
    if pg_pool:
        await pg_pool.close()
        logger.info("PostgreSQL pool closed.")
    logger.info("Application shutdown complete.")


# --- FastAPI Application ---
app = FastAPI(
    title="Azure Data Platform API",
    description=(
        "Backend API for the Azure Data Platform. Provides endpoints for "
        "AI chat interactions, analytics data, pipeline management, and ticket tracking."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# --- CORS Middleware ---
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://localhost:8501",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API Key Middleware ---
API_KEY = os.getenv("API_KEY", "")
PUBLIC_PATHS = {"/", "/docs", "/redoc", "/openapi.json", "/health", "/health/ready"}


@app.middleware("http")
async def api_key_middleware(request: Request, call_next):
    """Require API key for /api/* routes. Accepts X-API-Key header or ?api_key= query param."""
    path = request.url.path.rstrip("/") or "/"
    if API_KEY and path not in PUBLIC_PATHS and path.startswith("/api/"):
        key = request.headers.get("X-API-Key") or request.query_params.get("api_key", "")
        if key != API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


# --- Request Logging Middleware ---
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and response times."""
    import time

    start_time = time.time()
    response: Response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {duration_ms:.1f}ms"
    )
    response.headers["X-Response-Time"] = f"{duration_ms:.1f}ms"
    return response


# --- Global Exception Handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler for unhandled errors."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred.",
            "type": type(exc).__name__,
        },
    )


# --- Health Check Endpoint ---
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for load balancers and container orchestration.
    Returns service status and uptime information.
    """
    startup_time = getattr(app.state, "startup_time", None)
    uptime_seconds = (
        (datetime.utcnow() - startup_time).total_seconds() if startup_time else 0
    )

    return {
        "status": "healthy",
        "service": "azure-data-platform-api",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "uptime_seconds": round(uptime_seconds, 1),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check():
    """
    Readiness probe - checks if the service and its dependencies are ready.
    """
    checks = {
        "api": "ok",
        "database": "ok",
        "ai_foundry": "ok",
    }

    # In production, actually check connectivity to dependencies
    # For now, return a basic readiness response
    all_healthy = all(v == "ok" for v in checks.values())

    return {
        "ready": all_healthy,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


# --- Register Route Modules ---
app.include_router(
    chat_router,
    prefix="/api/v1/chat",
    tags=["Chat"],
)

app.include_router(
    analytics_router,
    prefix="/api/v1/analytics",
    tags=["Analytics"],
)

app.include_router(
    tickets_router,
    prefix="/api/v1/tickets",
    tags=["Tickets"],
)


# --- Root Endpoint ---
@app.get("/", tags=["Root"])
async def root():
    """API root - returns basic service information."""
    return {
        "service": "Azure Data Platform API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
    )
