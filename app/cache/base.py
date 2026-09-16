"""Abstract Base Cache Provider."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple


class BaseCacheStore(ABC):
    """Abstract interface for cache backends (Redis, In-Memory, VectorDB)."""

    @abstractmethod
    async def get_exact(self, key: str) -> Optional[Dict[str, Any]]:
        """Fetch exact cached entry by key."""
        pass

    @abstractmethod
    async def set_exact(self, key: str, value: Dict[str, Any], ttl_seconds: int):
        """Set exact cached entry with TTL."""
        pass

    @abstractmethod
    async def search_semantic(
        self, model: str, query_vector: List[float], similarity_threshold: float
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """
        Search for semantically similar query.
        Returns: (cached_value_dict, similarity_score) or None
        """
        pass

    @abstractmethod
    async def store_semantic(
        self, model: str, query_text: str, query_vector: List[float], response_data: Dict[str, Any], ttl_seconds: int
    ):
        """Store embedding vector and response data."""
        pass

    @abstractmethod
    async def flush(self):
        """Flush all cache items."""
        pass
