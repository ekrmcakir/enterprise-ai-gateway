"""Unit tests for FinOps Pricing, Rate Limiting and Token Budgets."""

import pytest
from app.finops.pricing_catalog import calculate_cost, PRICING_CATALOG
from app.finops.rate_limiter import SlidingWindowRateLimiter
from app.finops.budget_manager import BudgetManager
from app.core.exceptions import RateLimitExceededException, BudgetExceededException


def test_pricing_calculation():
    # GPT-4o: prompt=$0.005/1k, completion=$0.015/1k
    # 1000 prompt + 1000 completion = 0.005 + 0.015 = 0.02 USD
    cost = calculate_cost("gpt-4o", prompt_tokens=1000, completion_tokens=1000)
    assert cost == 0.02

    # Llama 3 (Ollama compute cost): prompt=$0.0001/1k, completion=$0.0002/1k
    llama_cost = calculate_cost("llama3", prompt_tokens=2000, completion_tokens=1000)
    assert llama_cost == 0.0004


def test_rate_limiter_rpm_enforcement():
    limiter = SlidingWindowRateLimiter(default_rpm=3, default_tpm=10000)
    client_id = "test-client-1"

    # 3 allowed requests
    limiter.check_and_record(client_id, estimated_tokens=10)
    limiter.check_and_record(client_id, estimated_tokens=10)
    limiter.check_and_record(client_id, estimated_tokens=10)

    # 4th request must trigger exception
    with pytest.raises(RateLimitExceededException):
        limiter.check_and_record(client_id, estimated_tokens=10)


def test_budget_manager_enforcement():
    bm = BudgetManager(default_monthly_limit_usd=1.0)
    client_id = "test-client-budget"

    # Preflight OK initially
    bm.check_budget_preflight(client_id)

    # Spend $0.60
    bm.record_usage(client_id, cost_usd=0.60, total_tokens=1000)
    bm.check_budget_preflight(client_id)

    # Spend another $0.50 (Total: $1.10 > $1.00)
    bm.record_usage(client_id, cost_usd=0.50, total_tokens=1000)

    # Next preflight must fail with BudgetExceededException
    with pytest.raises(BudgetExceededException) as exc_info:
        bm.check_budget_preflight(client_id)
    
    assert "Monthly FinOps token budget" in str(exc_info.value.detail)
