"""OpenAI Provider Adapter."""

import json
from typing import AsyncGenerator
import httpx
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
from app.config import settings
from app.core.logging import logger
from app.finops.pricing_catalog import calculate_cost


class OpenAIProvider(BaseLLMProvider):
    """Adapter for official OpenAI / Azure OpenAI endpoints."""

    def __init__(self, api_key: str = None, base_url: str = None):
        super().__init__("openai")
        self.api_key = api_key or settings.openai_api_key
        self.base_url = (base_url or settings.openai_base_url).rstrip("/")

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = request.model_dump(exclude={"enable_cache", "enable_firewall", "fallback_models"}, exclude_none=True)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            prompt_toks = data.get("usage", {}).get("prompt_tokens", 0)
            comp_toks = data.get("usage", {}).get("completion_tokens", 0)
            cost = calculate_cost(request.model, prompt_toks, comp_toks)

            return ChatCompletionResponse(
                id=data.get("id"),
                model=data.get("model", request.model),
                created=data.get("created"),
                choices=[
                    ChatCompletionChoice(
                        index=c.get("index", 0),
                        message=ChoiceMessage(
                            role=c.get("message", {}).get("role", "assistant"),
                            content=c.get("message", {}).get("content", ""),
                        ),
                        finish_reason=c.get("finish_reason", "stop"),
                    )
                    for c in data.get("choices", [])
                ],
                usage=Usage(
                    prompt_tokens=prompt_toks,
                    completion_tokens=comp_toks,
                    total_tokens=prompt_toks + comp_toks,
                    estimated_cost_usd=cost,
                ),
            )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = request.model_dump(exclude={"enable_cache", "enable_firewall", "fallback_models"}, exclude_none=True)
        payload["stream"] = True

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:].strip()
                    if data_str == "[DONE]":
                        break
                    chunk_json = json.loads(data_str)
                    choices = [
                        StreamChoice(
                            index=c.get("index", 0),
                            delta=DeltaMessage(
                                role=c.get("delta", {}).get("role"),
                                content=c.get("delta", {}).get("content"),
                            ),
                            finish_reason=c.get("finish_reason"),
                        )
                        for c in chunk_json.get("choices", [])
                    ]
                    yield ChatCompletionChunk(
                        id=chunk_json.get("id"),
                        model=chunk_json.get("model", request.model),
                        created=chunk_json.get("created"),
                        choices=choices,
                    )
