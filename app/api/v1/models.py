"""OpenAI-compatible /v1/models endpoint."""

from fastapi import APIRouter
from app.models.schemas import ModelListResponse, ModelCard
from app.finops.pricing_catalog import PRICING_CATALOG

models_router = APIRouter(tags=["Models"])


@models_router.get("/models", response_model=ModelListResponse)
async def list_models():
    """Returns list of all supported LLM models and aliases in the Gateway."""
    model_cards = [
        ModelCard(
            id=model_id,
            owned_by=meta.get("provider", "gateway")
        )
        for model_id, meta in PRICING_CATALOG.items()
    ]
    return ModelListResponse(data=model_cards)
