"""Analytics and FinOps monitoring API."""

from fastapi import APIRouter, Query, Header, Depends
from typing import Dict, Any, List
from app.models.db_models import audit_store, AuditLogRecord
from app.finops.budget_manager import budget_manager
from app.cache.semantic_cache import semantic_cache

analytics_router = APIRouter(prefix="/analytics", tags=["Analytics & FinOps"])


@analytics_router.get("/summary")
async def get_summary_metrics() -> Dict[str, Any]:
    """Get high-level Gateway KPI metrics (Total Requests, Cache Hit Ratio, Threat Blocks, FinOps Savings)."""
    return audit_store.get_summary_stats()


@analytics_router.get("/audit-logs", response_model=List[AuditLogRecord])
async def get_audit_logs(limit: int = Query(default=50, ge=1, le=200)):
    """Get recent detailed audit logs with firewall threat details and token usage."""
    return audit_store.get_records(limit=limit)


@analytics_router.get("/finops/wallet/{client_id}")
async def get_client_wallet(client_id: str) -> Dict[str, Any]:
    """Inspect current spending, limits, and tokens for a client/tenant."""
    return budget_manager.get_wallet(client_id)


@analytics_router.post("/cache/flush")
async def flush_cache() -> Dict[str, str]:
    """Admin endpoint to flush semantic and exact caches."""
    await semantic_cache.backend.flush()
    return {"message": "Semantic cache and exact cache flushed successfully."}
