"""Configuration module for Enterprise AI Gateway."""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Gateway Metadata
    app_name: str = "Enterprise AI Gateway & Semantic Firewall"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False
    api_prefix: str = "/v1"
    host: str = "0.0.0.0"
    port: int = 8000

    # API Security & Master Keys
    master_api_key: str = "sk-gw-admin-secret"
    allowed_api_keys: List[str] = [
        "sk-gw-admin-secret",
        "sk-gw-test-client",
        "sk-gw-finops-demo"
    ]

    # Upstream Provider Keys & Endpoints
    openai_api_key: Optional[str] = None
    openai_base_url: str = "https://api.openai.com/v1"

    anthropic_api_key: Optional[str] = None
    anthropic_base_url: str = "https://api.anthropic.com"

    ollama_base_url: str = "http://localhost:11434"
    
    # Enable simulated mock provider when real keys are absent
    enable_mock_fallback: bool = True

    # Semantic Firewall Settings
    firewall_enabled: bool = True
    block_prompt_injections: bool = True
    injection_sensitivity_threshold: float = 0.70  # 0.0 (permissive) to 1.0 (strict)
    pii_masking_enabled: bool = True
    output_guard_enabled: bool = True

    # Semantic Caching Settings
    cache_enabled: bool = True
    cache_similarity_threshold: float = 0.92  # Cosine similarity threshold for hit
    cache_ttl_seconds: int = 3600             # 1 hour default TTL
    redis_url: str = "redis://localhost:6379/0"
    use_redis: bool = False                   # Auto-fallbacks to in-memory vector cache if Redis down

    # FinOps & Rate Limiting
    rate_limit_enabled: bool = True
    default_rpm: int = 60                     # Requests per minute
    default_tpm: int = 100_000                # Tokens per minute
    default_monthly_budget_usd: float = 50.0  # Default budget cap per tenant

    # OpenTelemetry & Observability
    otel_service_name: str = "enterprise-ai-gateway"
    otel_exporter_otlp_endpoint: Optional[str] = None
    enable_prometheus: bool = True


settings = Settings()
