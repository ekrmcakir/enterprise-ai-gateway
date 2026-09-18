"""Health and readiness check endpoints."""

from fastapi import APIRouter
from typing import Dict, Any
from app.config import settings
from app.routing.router import router

health_router = APIRouter(tags=["Health"])


@health_router.get("/health")
async def health_check() -> Dict[str, Any]:
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
    }


@health_router.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    provider_status = {}
    for name, prov in router.providers.items():
        provider_status[name] = await prov.is_available()

    return {
        "status": "ready",
        "providers": provider_status,
        "firewall_active": settings.firewall_enabled,
        "cache_active": settings.cache_enabled,
    }
