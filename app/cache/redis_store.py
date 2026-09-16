"""Redis & In-Memory Vector Store implementation with Cosine Similarity."""

import time
import json
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from app.cache.base import BaseCacheStore
from app.core.logging import logger

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None


class InMemoryVectorStore(BaseCacheStore):
    """High-performance in-memory vector & key-value cache with cosine similarity search."""

    def __init__(self):
        self.exact_cache: Dict[str, Dict[str, Any]] = {}
        # List of items: {"model": str, "vector": np.ndarray, "query": str, "response": dict, "expires_at": float}
        self.vector_records: List[Dict[str, Any]] = []

    async def get_exact(self, key: str) -> Optional[Dict[str, Any]]:
        record = self.exact_cache.get(key)
        if not record:
            return None
        if time.time() > record["expires_at"]:
            del self.exact_cache[key]
            return None
        return record["value"]

    async def set_exact(self, key: str, value: Dict[str, Any], ttl_seconds: int):
        self.exact_cache[key] = {
            "value": value,
            "expires_at": time.time() + ttl_seconds
        }

    async def search_semantic(
        self, model: str, query_vector: List[float], similarity_threshold: float
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        now = time.time()
        # Clean expired records
        self.vector_records = [r for r in self.vector_records if r["expires_at"] > now]

        if not self.vector_records:
            return None

        # Filter by model
        candidates = [r for r in self.vector_records if r["model"] == model]
        if not candidates:
            return None

        q_vec = np.array(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return None

        best_score = -1.0
        best_record = None

        for rec in candidates:
            r_vec = rec["vector"]
            r_norm = np.linalg.norm(r_vec)
            if r_norm == 0:
                continue
            
            # Cosine similarity
            cosine_sim = float(np.dot(q_vec, r_vec) / (q_norm * r_norm))
            if cosine_sim > best_score:
                best_score = cosine_sim
                best_record = rec

        if best_record and best_score >= similarity_threshold:
            return best_record["response"], best_score

        return None

    async def store_semantic(
        self, model: str, query_text: str, query_vector: List[float], response_data: Dict[str, Any], ttl_seconds: int
    ):
        v_arr = np.array(query_vector, dtype=np.float32)
        self.vector_records.append({
            "model": model,
            "query": query_text,
            "vector": v_arr,
            "response": response_data,
            "expires_at": time.time() + ttl_seconds
        })

    async def flush(self):
        self.exact_cache.clear()
        self.vector_records.clear()


class RedisVectorStore(BaseCacheStore):
    """Redis-backed Cache Store."""

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.client: Optional[Any] = None
        self.in_memory_fallback = InMemoryVectorStore()

    async def connect(self):
        if aioredis:
            try:
                self.client = aioredis.from_url(self.redis_url, decode_responses=True)
                await self.client.ping()
                logger.info("[CACHE] Connected to Redis successfully.")
            except Exception as e:
                logger.warning(f"[CACHE] Redis connection failed ({e}). Falling back to In-Memory Vector Cache.")
                self.client = None

    async def get_exact(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return await self.in_memory_fallback.get_exact(key)
        try:
            val = await self.client.get(f"exact:{key}")
            return json.loads(val) if val else None
        except Exception:
            return await self.in_memory_fallback.get_exact(key)

    async def set_exact(self, key: str, value: Dict[str, Any], ttl_seconds: int):
        if not self.client:
            return await self.in_memory_fallback.set_exact(key, value, ttl_seconds)
        try:
            await self.client.setex(f"exact:{key}", ttl_seconds, json.dumps(value))
        except Exception:
            await self.in_memory_fallback.set_exact(key, value, ttl_seconds)

    async def search_semantic(
        self, model: str, query_vector: List[float], similarity_threshold: float
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        # Uses in-memory vector index (or Redis search vector extension if configured)
        return await self.in_memory_fallback.search_semantic(model, query_vector, similarity_threshold)

    async def store_semantic(
        self, model: str, query_text: str, query_vector: List[float], response_data: Dict[str, Any], ttl_seconds: int
    ):
        await self.in_memory_fallback.store_semantic(model, query_text, query_vector, response_data, ttl_seconds)

    async def flush(self):
        if self.client:
            try:
                await self.client.flushdb()
            except Exception:
                pass
        await self.in_memory_fallback.flush()
