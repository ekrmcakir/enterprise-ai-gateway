"""High-Fidelity Simulated Mock Provider for Local Demos, Testing & Fallback Validation."""

import asyncio
from typing import AsyncGenerator
from app.routing.providers.base import BaseLLMProvider
from app.models.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChoiceMessage,
    Usage,
    ChatCompletionChunk,
    StreamChoice,
    DeltaMessage,
)
from app.finops.pricing_catalog import calculate_cost


class MockProvider(BaseLLMProvider):
    """
    Mock LLM provider that simulates realistic LLM outputs, token usages, and latency.
    Used for local testing and reliable fallback when upstream cloud keys are omitted.
    """

    def __init__(self, simulate_failure: bool = False, simulated_latency_s: float = 0.05):
        super().__init__("mock_provider")
        self.simulate_failure = simulate_failure
        self.simulated_latency_s = simulated_latency_s

    async def is_available(self) -> bool:
        return not self.simulate_failure

    def _generate_mock_reply(self, request: ChatCompletionRequest) -> str:
        last_user_msg = ""
        for m in reversed(request.messages):
            if m.role == "user":
                last_user_msg = m.content
                break

        return (
            f"[Gateway Proxy ({request.model})] "
            f"Processed your request securely: '{last_user_msg[:80]}...'. "
            f"Enterprise guardrails and semantic checks were successfully executed."
        )

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        if self.simulate_failure:
            raise RuntimeError("Mock provider simulated upstream 503 service unavailable.")

        if self.simulated_latency_s > 0:
            await asyncio.sleep(self.simulated_latency_s)

        content = self._generate_mock_reply(request)
        all_text = " ".join(m.content for m in request.messages)
        prompt_tokens = max(1, len(all_text.split()) * 2)
        completion_tokens = max(1, len(content.split()) * 2)
        cost = calculate_cost(request.model, prompt_tokens, completion_tokens)

        return ChatCompletionResponse(
            model=request.model,
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChoiceMessage(role="assistant", content=content),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
                estimated_cost_usd=cost,
            ),
        )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        if self.simulate_failure:
            raise RuntimeError("Mock provider simulated upstream stream error.")

        full_reply = self._generate_mock_reply(request)
        words = full_reply.split(" ")

        for i, word in enumerate(words):
            await asyncio.sleep(0.02)
            is_last = i == len(words) - 1
            chunk_word = word if is_last else f"{word} "
            yield ChatCompletionChunk(
                model=request.model,
                choices=[
                    StreamChoice(
                        index=0,
                        delta=DeltaMessage(role="assistant" if i == 0 else None, content=chunk_word),
                        finish_reason="stop" if is_last else None,
                    )
                ]
            )
