"""Intelligent Router and Fallback Cascade Engine."""

import time
from typing import List, Dict, Tuple, Optional, AsyncGenerator
from app.routing.providers.base import BaseLLMProvider
from app.routing.providers.openai_provider import OpenAIProvider
from app.routing.providers.anthropic_provider import AnthropicProvider
from app.routing.providers.ollama_provider import OllamaProvider
from app.routing.providers.mock_provider import MockProvider
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChunk
from app.core.exceptions import UpstreamProviderException
from app.core.logging import logger
from app.config import settings


class CircuitBreaker:
    """Simple circuit breaker tracking consecutive upstream failures."""

    def __init__(self, failure_threshold: int = 3, recovery_timeout_s: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED (healthy), OPEN (broken), HALF-OPEN (testing)

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(f"[CIRCUIT_BREAKER] State changed to OPEN (failures={self.failure_count})")

    def allow_request(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout_s:
                self.state = "HALF-OPEN"
                return True
            return False
        return True  # HALF-OPEN allows a single probe


class IntelligentRouter:
    """Routes requests to primary model and transparently cascades down fallback providers on failure."""

    def __init__(self):
        self.providers: Dict[str, BaseLLMProvider] = {
            "openai": OpenAIProvider(),
            "anthropic": AnthropicProvider(),
            "ollama": OllamaProvider(),
            "mock": MockProvider(),
        }
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            name: CircuitBreaker() for name in self.providers
        }

    def _resolve_provider_for_model(self, model: str) -> str:
        m = model.lower()
        if "gpt" in m or "text-davinci" in m:
            return "openai"
        if "claude" in m:
            return "anthropic"
        if "llama" in m or "mistral" in m or "qwen" in m:
            return "ollama"
        return "mock" if settings.enable_mock_fallback else "openai"

    def get_fallback_chain(self, request: ChatCompletionRequest) -> List[Tuple[str, str]]:
        """
        Builds an ordered cascade list of (provider_name, model_name).
        Example: [("openai", "gpt-4o"), ("anthropic", "claude-3-5-sonnet-20240620"), ("mock", "gpt-4o")]
        """
        chain = []
        primary_provider = self._resolve_provider_for_model(request.model)
        chain.append((primary_provider, request.model))

        if request.fallback_models:
            for fb_model in request.fallback_models:
                p_name = self._resolve_provider_for_model(fb_model)
                if (p_name, fb_model) not in chain:
                    chain.append((p_name, fb_model))

        # Ensure Mock provider fallback is at the end if enabled
        if settings.enable_mock_fallback and not any(p == "mock" for p, _ in chain):
            chain.append(("mock", request.model))

        return chain

    async def route_completion(self, request: ChatCompletionRequest) -> Tuple[ChatCompletionResponse, str, str]:
        """
        Tries providers in fallback order until success.
        Returns: (ChatCompletionResponse, provider_used, model_used)
        """
        chain = self.get_fallback_chain(request)
        last_error = None

        for provider_name, target_model in chain:
            cb = self.circuit_breakers.get(provider_name)
            if cb and not cb.allow_request():
                logger.info(f"[ROUTER] Skipping provider '{provider_name}' due to open circuit breaker.")
                continue

            provider = self.providers.get(provider_name)
            if not provider:
                continue

            # Check provider readiness
            if not await provider.is_available() and provider_name != "mock":
                logger.debug(f"[ROUTER] Provider '{provider_name}' not available (no credentials / offline).")
                continue

            try:
                # Modify request for this provider model
                req_copy = request.model_copy(update={"model": target_model})
                logger.info(f"[ROUTER] Attempting provider '{provider_name}' with model '{target_model}'")
                
                resp = await provider.complete(req_copy)
                
                if cb:
                    cb.record_success()
                return resp, provider_name, target_model

            except Exception as e:
                logger.warning(f"[ROUTER] Provider '{provider_name}' failed with error: {e}")
                if cb:
                    cb.record_failure()
                last_error = e

        raise UpstreamProviderException(
            f"All providers in fallback cascade failed. Last error: {last_error}"
        )

    async def route_stream(
        self, request: ChatCompletionRequest
    ) -> AsyncGenerator[Tuple[ChatCompletionChunk, str, str], None]:
        """Routes streaming request to first available provider."""
        chain = self.get_fallback_chain(request)

        for provider_name, target_model in chain:
            provider = self.providers.get(provider_name)
            if not provider:
                continue

            if not await provider.is_available() and provider_name != "mock":
                continue

            try:
                req_copy = request.model_copy(update={"model": target_model})
                async for chunk in provider.stream_complete(req_copy):
                    yield chunk, provider_name, target_model
                return
            except Exception as e:
                logger.warning(f"[ROUTER] Stream provider '{provider_name}' failed: {e}")
                continue

        raise UpstreamProviderException("All streaming providers in fallback cascade failed.")


router = IntelligentRouter()
