"""Unit tests for Intelligent Routing, Circuit Breaking, and Fallback Cascades."""

import pytest
from app.routing.router import IntelligentRouter, CircuitBreaker
from app.routing.providers.mock_provider import MockProvider
from app.models.schemas import ChatCompletionRequest, ChatMessage


def test_circuit_breaker_state_transitions():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout_s=0.1)
    assert cb.state == "CLOSED"
    assert cb.allow_request() is True

    # 1 failure
    cb.record_failure()
    assert cb.state == "CLOSED"

    # 2nd failure -> Trips to OPEN
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.allow_request() is False


@pytest.mark.asyncio
async def test_mock_provider_complete_and_stream():
    prov = MockProvider()
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Hello Gateway!")]
    )

    # Completion test
    resp = await prov.complete(req)
    assert resp.model == "gpt-4o"
    assert len(resp.choices) > 0
    assert "Gateway Proxy" in resp.choices[0].message.content
    assert resp.usage.total_tokens > 0

    # Stream test
    chunks = []
    async for chunk in prov.stream_complete(req):
        chunks.append(chunk)
    assert len(chunks) > 0


@pytest.mark.asyncio
async def test_router_fallback_to_mock():
    router = IntelligentRouter()
    # Force primary providers offline to test fallback
    req = ChatCompletionRequest(
        model="gpt-4o",
        messages=[ChatMessage(role="user", content="Test fallback resilience")],
        fallback_models=["claude-3-5-sonnet-20240620", "llama3"]
    )

    resp, provider_used, model_used = await router.route_completion(req)
    assert resp is not None
    assert provider_used == "mock"  # Successfully resolved down cascade to Mock
