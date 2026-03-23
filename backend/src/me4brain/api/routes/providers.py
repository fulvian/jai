"""Providers API Routes - CRUD per provider LLM."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from me4brain.llm.provider_registry import (
    get_provider_registry,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/providers", tags=["Providers"])


class ProviderModelInput(BaseModel):
    id: str
    display_name: str = ""
    context_window: int = 32768
    max_output_tokens: int = 4096
    supports_tools: bool = True
    supports_vision: bool = False
    supports_streaming: bool = True
    access_mode: str = "api_paid"
    pricing: dict | None = None


class SubscriptionInput(BaseModel):
    enabled: bool = False
    weekly_token_limit: int | None = None
    reset_day: int = 1
    tokens_used_this_week: int = 0


class ProviderCreateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(
        default="openai_compatible", description="openai_compatible, anthropic, google_gemini, etc."
    )
    base_url: str = Field(..., pattern=r"^https?://.+")
    api_key: str | None = None
    api_key_header: str = "Authorization"
    models: list[ProviderModelInput] = []
    is_local: bool = False
    is_enabled: bool = True
    subscription: SubscriptionInput | None = None


class ProviderUpdateInput(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_header: str | None = None
    models: list[ProviderModelInput] | None = None
    is_local: bool | None = None
    is_enabled: bool | None = None
    subscription: SubscriptionInput | None = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    type: str
    base_url: str
    api_key: str | None
    api_key_header: str
    models: list[dict]
    is_local: bool
    is_enabled: bool
    created_at: str
    updated_at: str
    last_test: dict | None
    subscription: dict | None


class ProviderTestResponse(BaseModel):
    success: bool
    latency_ms: float
    error: str | None = None
    models_count: int | None = None


class DiscoverResponse(BaseModel):
    provider_id: str
    models: list[dict]
    count: int


@router.get("", response_model=list[ProviderResponse])
async def list_providers() -> list[ProviderResponse]:
    """Lista tutti i provider configurati."""
    registry = get_provider_registry()
    return [ProviderResponse(**p.to_dict()) for p in registry.list_all()]


@router.post("", response_model=ProviderResponse)
async def create_provider(data: ProviderCreateInput) -> ProviderResponse:
    """Crea un nuovo provider."""
    registry = get_provider_registry()

    provider_data = data.model_dump()
    if provider_data.get("subscription"):
        provider_data["subscription"] = data.subscription.model_dump()

    provider = registry.create(provider_data)
    logger.info("provider_created", id=provider.id, name=provider.name)
    return ProviderResponse(**provider.to_dict())


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: str) -> ProviderResponse:
    """Ottieni dettagli di un provider."""
    registry = get_provider_registry()
    provider = registry.get(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return ProviderResponse(**provider.to_dict())


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(provider_id: str, data: ProviderUpdateInput) -> ProviderResponse:
    """Aggiorna un provider esistente."""
    registry = get_provider_registry()
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    provider = registry.update(provider_id, update_data)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    logger.info("provider_updated", id=provider_id)
    return ProviderResponse(**provider.to_dict())


@router.delete("/{provider_id}")
async def delete_provider(provider_id: str) -> dict[str, Any]:
    """Elimina un provider."""
    registry = get_provider_registry()
    if not registry.delete(provider_id):
        raise HTTPException(status_code=404, detail="Provider not found")
    logger.info("provider_deleted", id=provider_id)
    return {"status": "deleted", "id": provider_id}


@router.post("/{provider_id}/test", response_model=ProviderTestResponse)
async def test_provider_connection(provider_id: str) -> ProviderTestResponse:
    """Testa la connessione al provider."""
    registry = get_provider_registry()
    result = await registry.test_connection(provider_id)
    return ProviderTestResponse(
        success=result.success,
        latency_ms=result.latency_ms,
        error=result.error,
        models_count=result.models_count,
    )


@router.get("/{provider_id}/discover", response_model=DiscoverResponse)
async def discover_provider_models(provider_id: str) -> DiscoverResponse:
    """Auto-discover modelli dal provider."""
    registry = get_provider_registry()
    models = await registry.discover_models(provider_id)
    return DiscoverResponse(
        provider_id=provider_id,
        models=[m.to_dict() for m in models],
        count=len(models),
    )


@router.get("/{provider_id}/subscription")
async def get_subscription_status(provider_id: str) -> dict[str, Any]:
    """Ottieni lo stato della subscription per un provider."""
    registry = get_provider_registry()
    provider = registry.get(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if not provider.subscription:
        return {"enabled": False, "message": "No subscription configured"}

    return {
        "enabled": provider.subscription.get("enabled", False),
        "weekly_token_limit": provider.subscription.get("weekly_token_limit"),
        "tokens_used_this_week": provider.subscription.get("tokens_used_this_week", 0),
        "reset_day": provider.subscription.get("reset_day", 1),
        "remaining": (
            provider.subscription.get("weekly_token_limit", 0)
            - provider.subscription.get("tokens_used_this_week", 0)
        )
        if provider.subscription.get("weekly_token_limit")
        else None,
    }


@router.post("/{provider_id}/subscription/reset")
async def reset_subscription_tokens(provider_id: str) -> dict[str, Any]:
    """Resetta i token usati questa settimana."""
    registry = get_provider_registry()
    provider = registry.get(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider.subscription:
        provider.subscription["tokens_used_this_week"] = 0
        registry._save()

    return {"status": "reset", "provider_id": provider_id}


@router.get("/subscription/models")
async def list_subscription_models() -> list[dict]:
    """Lista tutti i modelli disponibili via subscription."""
    registry = get_provider_registry()
    models = []
    for provider, model in registry.get_subscription_models():
        models.append(
            {
                "provider_id": provider.id,
                "provider_name": provider.name,
                "model_id": model.id,
                "display_name": model.display_name,
                "context_window": model.context_window,
                "supports_tools": model.supports_tools,
                "supports_vision": model.supports_vision,
            }
        )
    return models
