"""Semantic Caching Engine with Vector Similarity & Exact Fast Path."""

import hashlib
import json
import math
from typing import Optional, Tuple, Dict, Any, List
import numpy as np

from app.config import settings
from app.cache.redis_store import InMemoryVectorStore, RedisVectorStore
from app.core.telemetry import CACHE_HITS_TOTAL, CACHE_MISSES_TOTAL, COST_SAVINGS_USD_TOTAL
from app.core.logging import logger


class EmbeddingGenerator:
    """
    Lightweight, ultra-fast embedding generator producing 128-dimensional normalized vectors.
    Uses sub-word n-gram hashing and character distribution to capture semantic overlap 
    without needing heavy external model calls or GPU dependencies.
    """

    DIMENSION = 128

    @classmethod
    def generate_vector(cls, text: str) -> List[float]:
        if not text:
            return [0.0] * cls.DIMENSION

        clean_text = text.lower().strip()
        words = clean_text.split()
        
        vec = np.zeros(cls.DIMENSION, dtype=np.float32)

        # Word-level features
        for word in words:
            # Word hash index
            h_word = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
            idx = h_word % cls.DIMENSION
            sign = 1.0 if (h_word // cls.DIMENSION) % 2 == 0 else -1.0
            vec[idx] += sign * (1.0 + math.log(1 + len(word)))

            # Character 3-gram features
            for i in range(len(word) - 2):
                ngram = word[i:i+3]
                h_ngram = int(hashlib.sha1(ngram.encode("utf-8")).hexdigest(), 16)
                n_idx = h_ngram % cls.DIMENSION
                n_sign = 1.0 if (h_ngram // cls.DIMENSION) % 2 == 0 else -1.0
                vec[n_idx] += n_sign * 0.8

        # L2 Normalization
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        return vec.tolist()


class SemanticCache:
    """Orchestrates Exact SHA-256 caching and Vector Cosine Similarity Semantic Caching."""

    def __init__(self):
        if settings.use_redis:
            self.backend = RedisVectorStore(settings.redis_url)
        else:
            self.backend = InMemoryVectorStore()
        
        self.threshold = settings.cache_similarity_threshold
        self.ttl = settings.cache_ttl_seconds

    def _generate_exact_key(self, model: str, messages: List[Dict[str, Any]], temperature: Optional[float] = 0.7) -> str:
        serialized = json.dumps({
            "model": model,
            "messages": messages,
            "temperature": round(temperature or 0.7, 2)
        }, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _extract_query_text(self, messages: List[Dict[str, Any]]) -> str:
        """Extracts the latest user prompt text for semantic representation."""
        user_msgs = [m.get("content", "") for m in messages if m.get("role") == "user"]
        if user_msgs:
            return " ".join(user_msgs)
        return " ".join(m.get("content", "") for m in messages)

    async def lookup(
        self, model: str, messages: List[Dict[str, Any]], temperature: Optional[float] = 0.7
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str], float]:
        """
        Lookup response in cache.
        Returns: (is_hit, cached_response_data, hit_type ("exact" | "semantic" | None), similarity_score)
        """
        if not settings.cache_enabled:
            return False, None, None, 0.0

        exact_key = self._generate_exact_key(model, messages, temperature)
        
        # 1. Exact Match Fast Path (<1ms)
        exact_result = await self.backend.get_exact(exact_key)
        if exact_result:
            logger.info(f"[CACHE] Exact cache HIT for model={model}")
            CACHE_HITS_TOTAL.labels(model=model).inc()
            return True, exact_result, "exact", 1.0

        # 2. Semantic Cosine Vector Similarity Path
        query_text = self._extract_query_text(messages)
        query_vector = EmbeddingGenerator.generate_vector(query_text)
        
        semantic_match = await self.backend.search_semantic(model, query_vector, self.threshold)
        if semantic_match:
            cached_resp, score = semantic_match
            logger.info(f"[CACHE] Semantic cache HIT for model={model} with score={score:.4f}")
            CACHE_HITS_TOTAL.labels(model=model).inc()
            return True, cached_resp, "semantic", round(score, 4)

        # 3. Cache Miss
        CACHE_MISSES_TOTAL.labels(model=model).inc()
        return False, None, None, 0.0

    async def store(
        self, model: str, messages: List[Dict[str, Any]], response_data: Dict[str, Any], temperature: Optional[float] = 0.7
    ):
        """Stores result in both exact index and semantic vector index."""
        if not settings.cache_enabled:
            return

        exact_key = self._generate_exact_key(model, messages, temperature)
        query_text = self._extract_query_text(messages)
        query_vector = EmbeddingGenerator.generate_vector(query_text)

        await self.backend.set_exact(exact_key, response_data, self.ttl)
        await self.backend.store_semantic(model, query_text, query_vector, response_data, self.ttl)
        logger.debug(f"[CACHE] Stored response in cache for model={model}")


semantic_cache = SemanticCache()
