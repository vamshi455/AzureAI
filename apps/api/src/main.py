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

from routes.chat import router as chat_router
from routes.analytics import router as analytics_router
from routes.tickets import router as tickets_router

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
    logger.info("Application startup complete.")

    yield

    # Shutdown: close connections, flush buffers
    logger.info("Shutting down Azure Data Platform API...")
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
