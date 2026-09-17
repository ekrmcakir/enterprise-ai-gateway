"""FinOps Model Pricing Catalog (Prices per 1,000 Tokens in USD)."""

from typing import Dict, Any


# Prices per 1,000 tokens (e.g. GPT-4o: $0.005 / 1k input, $0.015 / 1k output)
PRICING_CATALOG: Dict[str, Dict[str, float]] = {
    # OpenAI Models
    "gpt-4o": {
        "prompt_price_per_1k": 0.005,
        "completion_price_per_1k": 0.015,
        "provider": "openai",
    },
    "gpt-4o-mini": {
        "prompt_price_per_1k": 0.00015,
        "completion_price_per_1k": 0.0006,
        "provider": "openai",
    },
    "gpt-4-turbo": {
        "prompt_price_per_1k": 0.01,
        "completion_price_per_1k": 0.03,
        "provider": "openai",
    },
    "gpt-3.5-turbo": {
        "prompt_price_per_1k": 0.0005,
        "completion_price_per_1k": 0.0015,
        "provider": "openai",
    },
    
    # Anthropic Models
    "claude-3-5-sonnet-20240620": {
        "prompt_price_per_1k": 0.003,
        "completion_price_per_1k": 0.015,
        "provider": "anthropic",
    },
    "claude-3-haiku-20240307": {
        "prompt_price_per_1k": 0.00025,
        "completion_price_per_1k": 0.00125,
        "provider": "anthropic",
    },

    # DeepSeek Models
    "deepseek-chat": {
        "prompt_price_per_1k": 0.00014,
        "completion_price_per_1k": 0.00028,
        "provider": "deepseek",
    },

    # Local / Open Weights (Free / Compute cost only)
    "llama3": {
        "prompt_price_per_1k": 0.0001,
        "completion_price_per_1k": 0.0002,
        "provider": "ollama",
    },
    "mistral": {
        "prompt_price_per_1k": 0.0001,
        "completion_price_per_1k": 0.0002,
        "provider": "ollama",
    },
}

# Fallback default price for custom models
DEFAULT_PRICING = {
    "prompt_price_per_1k": 0.002,
    "completion_price_per_1k": 0.006,
    "provider": "custom",
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculates the exact monetary cost in USD for a given completion."""
    pricing = PRICING_CATALOG.get(model.lower(), DEFAULT_PRICING)
    
    input_cost = (prompt_tokens / 1000.0) * pricing["prompt_price_per_1k"]
    output_cost = (completion_tokens / 1000.0) * pricing["completion_price_per_1k"]
    
    return round(input_cost + output_cost, 7)
