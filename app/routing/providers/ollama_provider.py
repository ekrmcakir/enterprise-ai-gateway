"""Ollama Local Model Provider Adapter."""

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


class OllamaProvider(BaseLLMProvider):
    """Adapter for local Ollama server running Llama 3, Mistral, Qwen, DeepSeek."""

    def __init__(self, base_url: str = None):
        super().__init__("ollama")
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception:
            return False

    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        url = f"{self.base_url}/api/chat"
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature or 0.7,
            }
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

            content = data.get("message", {}).get("content", "")
            prompt_toks = data.get("prompt_eval_count", len(str(messages)) // 4)
            comp_toks = data.get("eval_count", len(content) // 4)
            cost = calculate_cost(request.model, prompt_toks, comp_toks)

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
                    prompt_tokens=prompt_toks,
                    completion_tokens=comp_toks,
                    total_tokens=prompt_toks + comp_toks,
                    estimated_cost_usd=cost,
                ),
            )

    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        url = f"{self.base_url}/api/chat"
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        payload = {
            "model": request.model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": request.temperature or 0.7}
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk_json = json.loads(line)
                    delta_text = chunk_json.get("message", {}).get("content", "")
                    done = chunk_json.get("done", False)

                    yield ChatCompletionChunk(
                        model=request.model,
                        choices=[
                            StreamChoice(
                                index=0,
                                delta=DeltaMessage(role="assistant", content=delta_text),
                                finish_reason="stop" if done else None,
                            )
                        ]
                    )
