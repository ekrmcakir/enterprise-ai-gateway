"""In-memory telemetry and audit log store for Gateway Dashboard and Analytics."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone
import uuid


class AuditLogRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    client_id: str
    model_requested: str
    model_used: str
    status: str  # "success", "blocked_firewall", "cached", "rate_limited", "error"
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    cache_hit: bool = False
    cache_type: Optional[str] = None  # "exact", "semantic", None
    firewall_triggered: bool = False
    threat_details: Optional[Dict[str, Any]] = None
    pii_entities_masked: List[str] = Field(default_factory=list)
    prompt_preview: str = ""
    completion_preview: str = ""


class AuditStore:
    """Thread-safe ring buffer for real-time audit logging and analytics."""

    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self.records: List[AuditLogRecord] = []
        self._total_requests: int = 0
        self._total_cache_hits: int = 0
        self._total_blocked: int = 0
        self._total_cost_spent_usd: float = 0.0
        self._total_cost_saved_usd: float = 0.0

    def add_record(self, record: AuditLogRecord):
        self.records.insert(0, record)
        if len(self.records) > self.max_records:
            self.records.pop()

        self._total_requests += 1
        if record.cache_hit:
            self._total_cache_hits += 1
            self._total_cost_saved_usd += record.cost_usd
        elif record.firewall_triggered:
            self._total_blocked += 1
        else:
            self._total_cost_spent_usd += record.cost_usd

    def get_records(self, limit: int = 50) -> List[AuditLogRecord]:
        return self.records[:limit]

    def get_summary_stats(self) -> Dict[str, Any]:
        hit_ratio = (self._total_cache_hits / self._total_requests * 100.0) if self._total_requests > 0 else 0.0
        avg_latency = (
            sum(r.latency_ms for r in self.records) / len(self.records)
            if self.records else 0.0
        )
        return {
            "total_requests": self._total_requests,
            "total_cache_hits": self._total_cache_hits,
            "cache_hit_ratio_percent": round(hit_ratio, 2),
            "total_blocked_threats": self._total_blocked,
            "total_cost_spent_usd": round(self._total_cost_spent_usd, 6),
            "total_cost_saved_usd": round(self._total_cost_saved_usd, 6),
            "average_latency_ms": round(avg_latency, 2),
            "active_rules": ["Prompt Injection Detection", "Jailbreak Classifier", "Reversible PII Sanitizer", "Output Leak Guard"]
        }


audit_store = AuditStore()
