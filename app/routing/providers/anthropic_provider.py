"""Anthropic Claude Provider Adapter (converts OpenAI ChatCompletion format <-> Anthropic Messages API)."""

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
from app.finops.pricing_catalog import calculate_cost


class AnthropicProvider(BaseLLMProvider):
    """Adapter for Anthropic Claude /v1/messages API."""

    def __init__(self, api_key: str = None, base_url: str = None):
        super().__init__("anthropic")
        self.api_key = api_key or settings.anthropic_api_key
        self.base_url = (base_url or settings.anthropic_base_url).rstrip("/")

    async def is_available(self) -> bool:
        return bool(self.api_key)

    def _convert_messages(self, messages):
        system_prompt = ""
        claude_msgs = []
        for msg in messages:
            if msg.role == "system":
                system_prompt += f"{msg.content}\n"
            else:
                claude_msgs.append({
                    "role": "user" if msg.role == "user" else "assistant",
                    "content": msg.content
                })
        return system_prompt.strip(), claude_msgs

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        system_prompt, claude_msgs = self._convert_messages(request.messages)
        
        payload = {
            "model": request.model if "claude" in request.model else "claude-3-5-sonnet-20240620",
            "messages": claude_msgs,
            "max_tokens": request.max_tokens or 1024,
            "temperature": request.temperature or 0.7,
        }
        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

            prompt_toks = data.get("usage", {}).get("input_tokens", 0)
            comp_toks = data.get("usage", {}).get("output_tokens", 0)
            cost = calculate_cost(request.model, prompt_toks, comp_toks)
            
            content_text = ""
            if "content" in data and isinstance(data["content"], list):
                content_text = "".join(b.get("text", "") for b in data["content"] if b.get("type") == "text")

            return ChatCompletionResponse(
                id=data.get("id"),
                model=data.get("model", request.model),
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChoiceMessage(role="assistant", content=content_text),
                        finish_reason=data.get("stop_reason", "stop"),
                    )
                ],
                usage=Usage(
                    prompt_tokens=prompt_toks,
                    completion_tokens=comp_toks,
                    total_tokens=prompt_toks + comp_toks,
                    estimated_cost_usd=cost,
                ),
            )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        # Fallback to single chunk for streaming when direct SSE message stream is requested
        comp = await self.complete(request)
        yield ChatCompletionChunk(
            id=comp.id,
            model=comp.model,
            choices=[
                StreamChoice(
                    index=0,
                    delta=DeltaMessage(role="assistant", content=comp.choices[0].message.content),
                    finish_reason="stop",
                )
            ]
        )
