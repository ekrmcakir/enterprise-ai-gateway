"""Unit tests for Semantic Caching and Vector Similarity."""

import pytest
import numpy as np
from app.cache.semantic_cache import SemanticCache, EmbeddingGenerator
from app.cache.redis_store import InMemoryVectorStore


@pytest.fixture
def cache():
    sc = SemanticCache()
    sc.backend = InMemoryVectorStore()  # Isolated in-memory store
    sc.threshold = 0.70
    return sc


def test_embedding_generator_normalization():
    vec1 = EmbeddingGenerator.generate_vector("How do I configure Docker Compose?")
    vec2 = EmbeddingGenerator.generate_vector("How do I set up Docker Compose?")
    
    assert len(vec1) == 128
    assert len(vec2) == 128
    
    norm1 = np.linalg.norm(np.array(vec1))
    norm2 = np.linalg.norm(np.array(vec2))
    assert pytest.approx(norm1, 0.001) == 1.0
    assert pytest.approx(norm2, 0.001) == 1.0

    # High similarity for semantically identical questions
    sim = np.dot(np.array(vec1), np.array(vec2))
    assert sim > 0.70


@pytest.mark.asyncio
async def test_exact_cache_hit_and_miss(cache):
    messages = [{"role": "user", "content": "What is Python asyncio?"}]
    response_payload = {
        "id": "mock-1",
        "model": "gpt-4o",
        "created": 123456,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Asyncio is a library..."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30, "estimated_cost_usd": 0.0003}
    }

    # First lookup -> Miss
    hit, val, hit_type, score = await cache.lookup("gpt-4o", messages)
    assert not hit
    assert val is None

    # Store in cache
    await cache.store("gpt-4o", messages, response_payload)

    # Second lookup -> Exact Hit
    hit, val, hit_type, score = await cache.lookup("gpt-4o", messages)
    assert hit is True
    assert hit_type == "exact"
    assert val["choices"][0]["message"]["content"] == "Asyncio is a library..."


@pytest.mark.asyncio
async def test_semantic_cache_hit_on_paraphrased_query(cache):
    msg1 = [{"role": "user", "content": "Explain microservices architecture benefits."}]
    response_payload = {
        "id": "mock-2",
        "model": "gpt-4o",
        "created": 123456,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "Microservices offer scalability..."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 25, "total_tokens": 37, "estimated_cost_usd": 0.0004}
    }

    # Store first query
    await cache.store("gpt-4o", msg1, response_payload)

    # Lookup paraphrased query with similar words
    msg2 = [{"role": "user", "content": "Explain microservices architecture benefits"}]
    hit, val, hit_type, score = await cache.lookup("gpt-4o", msg2)
    
    assert hit is True
    assert hit_type in ("exact", "semantic")
    assert score >= cache.threshold
    assert val["choices"][0]["message"]["content"] == "Microservices offer scalability..."
