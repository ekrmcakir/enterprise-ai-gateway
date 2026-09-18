"""Main FastAPI application entry point for Enterprise AI Gateway."""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from app.config import settings
from app.core.logging import logger
from app.core.exceptions import GatewayException
from app.api.v1 import v1_router, health_router
from app.api.dashboard import dashboard_router
from app.cache.redis_store import RedisVectorStore
from app.cache.semantic_cache import semantic_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"[BOOT] Starting {settings.app_name} v{settings.app_version} on {settings.environment}...")
    if isinstance(semantic_cache.backend, RedisVectorStore):
        await semantic_cache.backend.connect()
    yield
    logger.info("[SHUTDOWN] Shutting down AI Gateway...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production-grade AI Gateway, Semantic Firewall, Model Routing, and FinOps Controller.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus Metrics
if settings.enable_prometheus:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

# Mount Static Assets for Dashboard
static_dir = Path(__file__).resolve().parent.parent / "dashboard"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Register Routers
app.include_router(health_router)
app.include_router(v1_router)
app.include_router(dashboard_router)


from fastapi.responses import JSONResponse

@app.exception_handler(GatewayException)
async def gateway_exception_handler(request: Request, exc: GatewayException):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )
