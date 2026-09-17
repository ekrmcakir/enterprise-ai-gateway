"""Base LLM Provider Interface."""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List, Optional
from app.models.schemas import ChatCompletionRequest, ChatCompletionResponse, ChatCompletionChunk


class BaseLLMProvider(ABC):
    """Abstract base class for all upstream LLM provider adapters."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def is_available(self) -> bool:
        """Health check probe to verify if provider is configured and reachable."""
        pass

    @abstractmethod
    async def complete(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute non-streaming completion."""
        pass

    @abstractmethod
    async def stream_complete(self, request: ChatCompletionRequest) -> AsyncGenerator[ChatCompletionChunk, None]:
        """Execute streaming completion (SSE chunks)."""
        pass
