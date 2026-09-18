"""V1 API Router bundle."""

from fastapi import APIRouter
from app.api.v1.chat import chat_router
from app.api.v1.models import models_router
from app.api.v1.analytics import analytics_router
from app.api.v1.health import health_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(chat_router)
v1_router.include_router(models_router)
v1_router.include_router(analytics_router)

__all__ = ["v1_router", "health_router"]
