"""OpenTelemetry and Prometheus Telemetry integration for GenAI metrics and tracing."""

from typing import Optional
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from prometheus_client import Counter, Histogram, Gauge

from app.config import settings

# Initialize Tracer
resource = Resource.create({"service.name": settings.otel_service_name, "environment": settings.environment})
provider = TracerProvider(resource=resource)
# In production, BatchSpanProcessor(OTLPSpanExporter(...)) is added here
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("enterprise-ai-gateway")

# --- Prometheus Metrics Instruments (Conforming to GenAI Semantic Conventions) ---
REQUESTS_TOTAL = Counter(
    "gen_ai_gateway_requests_total",
    "Total incoming LLM requests processed by the gateway",
    ["model", "client_id", "status"]
)

LATENCY_HISTOGRAM = Histogram(
    "gen_ai_gateway_request_duration_seconds",
    "Latency duration for requests processed by the gateway",
    ["model", "source"],  # source: cache_hit, upstream_call, blocked
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

PROMPT_TOKENS_TOTAL = Counter(
    "gen_ai_gateway_prompt_tokens_total",
    "Total input prompt tokens processed",
    ["model", "client_id"]
)

COMPLETION_TOKENS_TOTAL = Counter(
    "gen_ai_gateway_completion_tokens_total",
    "Total output completion tokens generated",
    ["model", "client_id"]
)

ESTIMATED_COST_USD = Counter(
    "gen_ai_gateway_estimated_cost_usd_total",
    "Cumulative estimated dollar cost of LLM generation",
    ["model", "client_id"]
)

CACHE_HITS_TOTAL = Counter(
    "gen_ai_gateway_cache_hits_total",
    "Total number of semantic and exact cache hits",
    ["model"]
)

CACHE_MISSES_TOTAL = Counter(
    "gen_ai_gateway_cache_misses_total",
    "Total number of cache misses",
    ["model"]
)

COST_SAVINGS_USD_TOTAL = Counter(
    "gen_ai_gateway_cost_savings_usd_total",
    "Total estimated dollars saved via semantic caching",
    ["model"]
)

FIREWALL_BLOCKED_TOTAL = Counter(
    "gen_ai_gateway_firewall_blocked_total",
    "Total prompt injections and malicious attacks blocked by firewall",
    ["threat_type", "client_id"]
)

PII_ENTITIES_MASKED_TOTAL = Counter(
    "gen_ai_gateway_pii_entities_masked_total",
    "Total sensitive PII entities redacted before upstream dispatch",
    ["entity_type"]
)
