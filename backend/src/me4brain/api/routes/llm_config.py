"""LLM Configuration API Routes - SOTA 2026.

API per configurazione runtime dei modelli LLM senza restart del server.
Supporta model discovery per hot-swapping a monitoring risorse.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from me4brain.core.monitoring.resource_monitor import (
    get_resource_monitor,
)
from me4brain.engine.context_compressor import (
    get_context_tracker,
)
from me4brain.llm.config import get_llm_config
from me4brain.llm.model_discovery import (
    DiscoveredModel,
    ModelSource,
    get_model_discovery,
)
from me4brain.llm.model_profiles import (
    ModelProfile,
    get_all_profiles,
    get_cloud_models,
    get_local_models,
    get_model_profile,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/config/llm", tags=["LLM Configuration"])


from dotenv import find_dotenv, set_key

# Mapping from config keys to environment variable names
ENV_VAR_MAPPING = {
    "model_primary": "LLM_PRIMARY_MODEL",
    "model_routing": "LLM_ROUTING_MODEL",
    "model_synthesis": "LLM_SYNTHESIS_MODEL",
    "model_fallback": "LLM_FALLBACK_MODEL",
    "use_local_tool_calling": "USE_LOCAL_TOOL_CALLING",
    "context_overflow_strategy": "CONTEXT_OVERFLOW_STRATEGY",
    "default_temperature": "LLM_DEFAULT_TEMPERATURE",
    "default_max_tokens": "LLM_DEFAULT_MAX_TOKENS",
    "context_window_size": "LLM_CONTEXT_WINDOW_SIZE",
    "enable_streaming": "LLM_ENABLE_STREAMING",
    "enable_caching": "LLM_ENABLE_CACHING",
    "enable_metrics": "LLM_ENABLE_METRICS",
}


def _persist_to_env_file(updates: dict[str, Any]) -> tuple[bool, str]:
    """Persist configuration updates to .env file using dynamic discovery."""
    env_file = find_dotenv()
    if not env_file:
        logger.warning("env_file_not_found_dynamically")
        return False, ".env file not found dynamically"

    try:
        for config_key, env_var in ENV_VAR_MAPPING.items():
            if config_key in updates:
                value = updates[config_key]
                # Convert value to string and normalize
                value_str = str(value).lower() if isinstance(value, bool) else str(value)

                # Use set_key for clean, comment-preserving updates
                set_key(env_file, env_var, value_str)
                logger.debug("persisted_env_var", key=env_var, value=value_str)

        logger.info("persisted_config_to_env", file=str(env_file), updates=list(updates.keys()))
        return True, f"Persisted to {env_file}"

    except Exception as e:
        logger.error("failed_to_persist_env", error=str(e))
        return False, f"Failed to persist: {str(e)}"


class LLMConfigUpdate(BaseModel):
    """Parametri LLM modificabili a runtime."""

    model_primary: str | None = None
    model_routing: str | None = None
    model_synthesis: str | None = None
    model_fallback: str | None = None
    use_local_tool_calling: bool | None = None
    context_overflow_strategy: Literal["map_reduce", "truncate", "cloud_fallback"] | None = None
    default_temperature: float | None = Field(None, ge=0.0, le=2.0)
    default_max_tokens: int | None = Field(None, ge=64, le=32768)
    context_window_size: int | None = Field(None, ge=2048, le=131072)
    enable_streaming: bool | None = None
    enable_caching: bool | None = None
    enable_metrics: bool | None = None


class LLMModelInfo(BaseModel):
    """Informazioni su un modello disponibile."""

    id: str
    name: str
    provider: str
    context_window: int
    supports_tools: bool
    supports_vision: bool
    quantization: str | None = None
    vram_required_gb: float | None = None
    speed_tps: float | None = None
    recommended_for: list[str] = []
    not_recommended_for: list[str] = []
    max_context_length: int | None = None  # Max supported by the model (from LM Studio)
    is_loaded: bool = False  # Whether the model is currently loaded in LM Studio


class LLMConfigResponse(BaseModel):
    """Configurazione LLM corrente."""

    model_primary: str
    model_routing: str
    model_synthesis: str
    model_fallback: str
    use_local: bool
    context_overflow_strategy: str
    default_temperature: float
    default_max_tokens: int
    context_window: int
    available_models: list[LLMModelInfo] = []
    enable_streaming: bool = True
    enable_caching: bool = True
    enable_metrics: bool = False


class LLMStatusResponse(BaseModel):
    """Stato runtime dei provider LLM."""

    local: dict[str, Any]
    cloud: dict[str, Any]
    resources: dict[str, Any]


def _profile_to_info(profile: ModelProfile) -> LLMModelInfo:
    """Converte ModelProfile in LLMModelInfo."""
    return LLMModelInfo(
        id=profile.id,
        name=profile.name,
        provider=profile.provider.value,
        context_window=profile.context_window,
        supports_tools=profile.supports_tools,
        supports_vision=profile.supports_vision,
        quantization=profile.quantization,
        vram_required_gb=profile.vram_required_gb,
        speed_tps=profile.speed_tps,
        recommended_for=profile.recommended_for,
        not_recommended_for=profile.not_recommended_for,
    )


def _discovered_to_info(m: DiscoveredModel) -> LLMModelInfo:
    """Converte DiscoveredModel in LLMModelInfo."""
    is_local = m.source != ModelSource.CLOUD_NANOGPT
    return LLMModelInfo(
        id=m.id,
        name=f"{m.name} {'(Locale)' if is_local else '(Cloud - NanoGPT)'}",
        provider=m.source.value,
        context_window=m.context_window,
        supports_tools=m.supports_tools,
        supports_vision=m.supports_vision,
        quantization=m.quantization,
        vram_required_gb=m.size_gb,
        max_context_length=m.metadata.get("max_context_length"),
        is_loaded=m.metadata.get("is_loaded", False),
    )


@router.get("/models")
async def list_available_models() -> list[LLMModelInfo]:
    """Lista modelli disponibili (locali scoperti + cloud + provider custom)."""
    models = []

    discovery = get_model_discovery()
    discovered = await discovery.get_all_local_models()
    for m in discovered:
        models.append(_discovered_to_info(m))

    for profile in get_cloud_models():
        models.append(_profile_to_info(profile))

    try:
        from me4brain.llm.provider_registry import get_provider_registry

        registry = get_provider_registry()
        for provider in registry.list_all():
            if provider.is_enabled:
                for model in provider.models:
                    is_sub = provider.subscription and provider.subscription.get("enabled")
                    access = model.access_mode
                    sub_label = "PRO" if (access in ("subscription", "both") and is_sub) else None
                    api_label = "API" if access in ("api_paid", "both") else None
                    labels = [l for l in [sub_label, api_label] if l]
                    label_str = f" ({' + '.join(labels)})" if labels else ""

                    models.append(
                        LLMModelInfo(
                            id=f"{provider.id}:{model.id}",
                            name=f"{model.display_name}{label_str} ({provider.name})",
                            provider=f"custom:{provider.name}",
                            context_window=model.context_window,
                            supports_tools=model.supports_tools,
                            supports_vision=model.supports_vision,
                        )
                    )
    except Exception as e:
        logger.warning("failed_to_load_custom_providers", error=str(e))

    return models


@router.get("/models/local")
async def list_local_models() -> list[LLMModelInfo]:
    """Lista modelli locali scoperti."""
    models = []

    discovery = get_model_discovery()
    discovered = await discovery.get_all_local_models()
    for m in discovered:
        models.append(_discovered_to_info(m))

    for profile in get_local_models():
        models.append(_profile_to_info(profile))

    return models


@router.get("/models/cloud")
async def list_cloud_models() -> list[LLMModelInfo]:
    """Lista modelli cloud (solo Mistral Large 3)."""
    models = []
    for profile in get_cloud_models():
        models.append(_profile_to_info(profile))
    return models


@router.get("/current")
async def get_current_config() -> LLMConfigResponse:
    """Configurazione LLM corrente."""
    config = get_llm_config()

    # Get available models from discovery + providers (same as /models endpoint)
    available_models = await list_available_models()

    primary_profile = get_model_profile(config.model_primary)
    context_window = (
        primary_profile.context_window if primary_profile else config.context_window_size
    )

    return LLMConfigResponse(
        model_primary=config.model_primary,
        model_routing=config.model_routing,
        model_synthesis=config.model_synthesis,
        model_fallback=config.model_fallback,
        use_local=config.use_local_tool_calling,
        context_overflow_strategy=config.context_overflow_strategy,
        default_temperature=config.default_temperature,
        default_max_tokens=config.default_max_tokens,
        context_window=context_window,
        available_models=available_models,
        enable_streaming=config.enable_streaming,
        enable_caching=config.enable_caching,
        enable_metrics=config.enable_metrics,
    )


@router.put("/update")
async def update_llm_config(update: LLMConfigUpdate) -> dict[str, Any]:
    """Aggiorna configurazione LLM a runtime e persiste nel file .env."""
    updates_applied = []
    updates_to_persist: dict[str, Any] = {}
    should_clear_cache = False

    if update.model_primary is not None:
        updates_applied.append(f"model_primary={update.model_primary}")
        updates_to_persist["model_primary"] = update.model_primary
        should_clear_cache = True

    if update.model_routing is not None:
        updates_applied.append(f"model_routing={update.model_routing}")
        updates_to_persist["model_routing"] = update.model_routing
        should_clear_cache = True

    if update.model_synthesis is not None:
        updates_applied.append(f"model_synthesis={update.model_synthesis}")
        updates_to_persist["model_synthesis"] = update.model_synthesis
        should_clear_cache = True

    if update.model_fallback is not None:
        updates_applied.append(f"model_fallback={update.model_fallback}")
        updates_to_persist["model_fallback"] = update.model_fallback
        should_clear_cache = True

    if update.use_local_tool_calling is not None:
        updates_applied.append(f"use_local_tool_calling={update.use_local_tool_calling}")
        updates_to_persist["use_local_tool_calling"] = update.use_local_tool_calling
        should_clear_cache = True

    if update.context_overflow_strategy is not None:
        updates_applied.append(f"context_overflow_strategy={update.context_overflow_strategy}")
        updates_to_persist["context_overflow_strategy"] = update.context_overflow_strategy
        should_clear_cache = True

    if update.default_temperature is not None:
        updates_applied.append(f"default_temperature={update.default_temperature}")
        updates_to_persist["default_temperature"] = update.default_temperature

    if update.default_max_tokens is not None:
        updates_applied.append(f"default_max_tokens={update.default_max_tokens}")
        updates_to_persist["default_max_tokens"] = update.default_max_tokens

    if update.context_window_size is not None:
        updates_applied.append(f"context_window_size={update.context_window_size}")
        updates_to_persist["context_window_size"] = update.context_window_size

    if update.enable_streaming is not None:
        updates_applied.append(f"enable_streaming={update.enable_streaming}")
        updates_to_persist["enable_streaming"] = update.enable_streaming

    if update.enable_caching is not None:
        updates_applied.append(f"enable_caching={update.enable_caching}")
        updates_to_persist["enable_caching"] = update.enable_caching

    if update.enable_metrics is not None:
        updates_applied.append(f"enable_metrics={update.enable_metrics}")
        updates_to_persist["enable_metrics"] = update.enable_metrics

    # First persist to .env file (source of truth), then update os.environ
    persistence_result = {"success": False, "message": "No updates to persist"}
    if updates_to_persist:
        success, message = _persist_to_env_file(updates_to_persist)
        persistence_result = {"success": success, "message": message}
        if not success:
            logger.error("failed_to_persist_env_before_os_update", message=message)
            # Continue anyway - os.environ update will still work for this process

    # Now update os.environ with the persisted values
    for config_key, env_var in ENV_VAR_MAPPING.items():
        if config_key in updates_to_persist:
            value = updates_to_persist[config_key]
            value_str = str(value).lower() if isinstance(value, bool) else str(value)
            os.environ[env_var] = value_str

    # Reset hybrid router singleton to pick up new config
    # Note: get_llm_config() is not cached - it creates a fresh LLMConfig()
    # instance each time that reads from os.environ and .env file
    verified_config = {}
    if should_clear_cache:
        try:
            from me4brain.engine.hybrid_router.router import _reset_router_singleton

            _reset_router_singleton()
        except Exception as e:
            logger.warning("hybrid_router_reset_failed", error=str(e))

        new_config = get_llm_config()
        verified_config = {
            "context_overflow_strategy": new_config.context_overflow_strategy,
            "model_primary": new_config.model_primary,
            "model_routing": new_config.model_routing,
            "model_synthesis": new_config.model_synthesis,
            "model_fallback": new_config.model_fallback,
            "use_local_tool_calling": new_config.use_local_tool_calling,
        }

    logger.info(
        "llm_config_updated",
        updates=updates_applied,
        verified_strategy=verified_config.get("context_overflow_strategy"),
        persisted=persistence_result["success"],
    )

    return {
        "status": "updated",
        "updates_applied": updates_applied,
        "verified_config": verified_config,
        "persistence": persistence_result,
    }


@router.post("/reset")
async def reset_llm_config() -> dict[str, Any]:
    """Ripristina la configurazione LLM ai valori predefiniti.

    Reimposta tutte le variabili ambientali LLM ai valori di default
    definiti in LLMConfig e persiste nel file .env.
    """
    from me4brain.llm.config import LLMConfig

    # Get default config values
    default_config = LLMConfig()

    # Build updates dict with default values
    updates = {
        "model_primary": default_config.model_primary,
        "model_routing": default_config.model_routing,
        "model_synthesis": default_config.model_synthesis,
        "model_fallback": default_config.model_fallback,
        "use_local_tool_calling": default_config.use_local_tool_calling,
        "context_overflow_strategy": default_config.context_overflow_strategy,
        "default_temperature": default_config.default_temperature,
        "default_max_tokens": default_config.default_max_tokens,
        "context_window_size": default_config.context_window_size,
        "enable_streaming": default_config.enable_streaming,
        "enable_caching": default_config.enable_caching,
        "enable_metrics": default_config.enable_metrics,
    }

    # Update os.environ
    env_mapping = {
        "model_primary": "LLM_PRIMARY_MODEL",
        "model_routing": "LLM_ROUTING_MODEL",
        "model_synthesis": "LLM_SYNTHESIS_MODEL",
        "model_fallback": "LLM_FALLBACK_MODEL",
        "use_local_tool_calling": "USE_LOCAL_TOOL_CALLING",
        "context_overflow_strategy": "CONTEXT_OVERFLOW_STRATEGY",
        "default_temperature": "LLM_DEFAULT_TEMPERATURE",
        "default_max_tokens": "LLM_DEFAULT_MAX_TOKENS",
        "context_window_size": "LLM_CONTEXT_WINDOW_SIZE",
        "enable_streaming": "LLM_ENABLE_STREAMING",
        "enable_caching": "LLM_ENABLE_CACHING",
        "enable_metrics": "LLM_ENABLE_METRICS",
    }

    for config_key, env_var in env_mapping.items():
        value = updates[config_key]
        value_str = str(value).lower() if isinstance(value, bool) else str(value)
        os.environ[env_var] = value_str

    # Persist to .env file
    persistence_success, persistence_message = _persist_to_env_file(updates)

    # Reset router singleton
    try:
        from me4brain.engine.hybrid_router.router import _reset_router_singleton

        _reset_router_singleton()
    except Exception as e:
        logger.warning("hybrid_router_reset_failed", error=str(e))

    logger.info("llm_config_reset_to_defaults", persistence=persistence_success)

    return {
        "status": "reset",
        "message": "Configurazione ripristinata ai valori predefiniti",
        "defaults_applied": list(updates.keys()),
        "persistence": {"success": persistence_success, "message": persistence_message},
    }


@router.get("/status")
async def get_llm_status() -> LLMStatusResponse:
    """Stato runtime dei provider LLM."""
    monitor = get_resource_monitor()
    stats = await monitor.get_system_stats()

    config = get_llm_config()

    local_available = False
    local_model = config.ollama_model
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.ollama_base_url}/models")
            if response.status_code == 200:
                local_available = True
    except Exception:
        pass

    cloud_available = bool(config.nanogpt_api_key)

    return LLMStatusResponse(
        local={
            "available": local_available,
            "model_loaded": local_model,
            "inference_speed_tps": None,
            "process_memory_gb": round(stats.mlx_process_rss_gb, 2),
        },
        cloud={
            "available": cloud_available,
            "provider": "nanogpt",
            "base_url": config.nanogpt_base_url,
        },
        resources={
            "ram_usage_pct": round(stats.ram_usage_pct, 1),
            "swap_gb": round(stats.swap_used_gb, 2),
            "level": stats.resource_level.value,
            "under_pressure": stats.is_under_pressure,
        },
    )


@router.get("/discover")
async def discover_local_models() -> dict[str, Any]:
    """Scansiona modelli locali disponibili (mlx_lm.server / LM Studio)."""
    config = get_llm_config()
    discovered = {
        "ollama": [],
        "lmstudio": [],
        "errors": [],
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config.ollama_base_url}/models")
            if response.status_code == 200:
                data = response.json()
                for model in data.get("data", []):
                    discovered["ollama"].append(
                        {
                            "id": model.get("id"),
                            "owned_by": model.get("owned_by", "local"),
                        }
                    )
    except Exception as e:
        discovered["errors"].append(f"ollama: {str(e)}")

    try:
        lmstudio_url = config.lmstudio_base_url
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{lmstudio_url}/models")
            if response.status_code == 200:
                data = response.json()
                for model in data.get("data", []):
                    discovered["lmstudio"].append(
                        {
                            "id": model.get("id"),
                            "owned_by": model.get("owned_by", "lmstudio"),
                        }
                    )
    except Exception as e:
        discovered["errors"].append(f"lmstudio: {str(e)}")

    return discovered


@router.get("/recommendations")
async def get_model_recommendations() -> dict[str, Any]:
    """Raccomandazioni per task basate sui profili modello."""
    from me4brain.llm.model_profiles import get_best_model_for_task

    tasks = [
        "routing",
        "tool_selection",
        "tool_calling",
        "synthesis",
        "reasoning",
        "vision",
        "extraction",
    ]

    recommendations = {}
    for task in tasks:
        best = get_best_model_for_task(task, prefer_local=True, max_vram_gb=8.0)
        if best:
            recommendations[task] = {
                "model_id": best.id,
                "name": best.name,
                "is_local": best.is_local,
            }

    return {
        "recommendations": recommendations,
        "note": "Based on model profiles and 8GB VRAM limit",
    }


@router.get("/context-tracker")
async def get_context_tracker_info() -> dict[str, Any]:
    """Info sul context tracker."""
    tracker = get_context_tracker()
    return tracker.get_status()


@router.post("/context-tracker/reset")
async def reset_context_tracker() -> dict[str, Any]:
    """Reset del context tracker per nuova query."""
    tracker = get_context_tracker()
    tracker.reset()
    return {"status": "reset", "message": "Context tracker reset for new query"}


class HardwareRecommendationsResponse(BaseModel):
    """Raccomandazioni parametri basate su risorse hardware."""

    recommended_max_tokens: int
    recommended_context_window: int
    available_ram_gb: float
    ram_usage_pct: float
    is_under_pressure: bool
    resource_level: str
    warnings: list[str] = []
    recommendations: list[str] = []


@router.get("/recommendations/hardware")
async def get_hardware_recommendations() -> HardwareRecommendationsResponse:
    """Raccomandazioni per parametri LLM basate su risorse hardware disponibili.

    Calcola valori ottimali per max_tokens e context_window in base a:
    - RAM disponibile
    - Swap in uso
    - Memoria processi MLX
    - Livello di pressione risorse
    """
    monitor = get_resource_monitor()
    stats = await monitor.get_system_stats()

    available_ram_gb = stats.ram_available_gb
    ram_usage_pct = stats.ram_usage_pct
    is_under_pressure = stats.is_under_pressure
    resource_level = stats.resource_level.value

    warnings: list[str] = []
    recommendations_list: list[str] = []

    if stats.swap_used_gb > monitor.SWAP_WARNING_GB:
        warnings.append(
            f"Swap in uso: {stats.swap_used_gb:.1f}GB - prestazioni potenzialmente ridotte"
        )

    if stats.mlx_process_rss_gb > 4.0:
        warnings.append(f"Processo MLX sta usando {stats.mlx_process_rss_gb:.1f}GB di memoria")

    recommended_max_tokens = 8192
    recommended_context_window = 32768

    if available_ram_gb >= 12.0:
        recommended_max_tokens = 16384
        recommended_context_window = 65536
        recommendations_list.append("RAM abbondante: puoi usare modelli grandi e contesti lunghi")
    elif available_ram_gb >= 8.0:
        recommended_max_tokens = 8192
        recommended_context_window = 32768
        recommendations_list.append("RAM adeguata: configurazione bilanciata consigliata")
    elif available_ram_gb >= 4.0:
        recommended_max_tokens = 4096
        recommended_context_window = 16384
        recommendations_list.append("RAM limitata: usa modelli piccoli e contesti brevi")
    else:
        recommended_max_tokens = 2048
        recommended_context_window = 8192
        warnings.append("RAM molto limitata: considera di chiudere altre applicazioni")
        recommendations_list.append("Considera l'uso del cloud fallback per carichi pesanti")

    if is_under_pressure:
        warnings.append("Sistema sotto pressione: il cloud fallback potrebbe essere necessario")
        recommended_max_tokens = min(recommended_max_tokens, 4096)
        recommended_context_window = min(recommended_context_window, 16384)

    return HardwareRecommendationsResponse(
        recommended_max_tokens=recommended_max_tokens,
        recommended_context_window=recommended_context_window,
        available_ram_gb=round(available_ram_gb, 2),
        ram_usage_pct=round(ram_usage_pct, 1),
        is_under_pressure=is_under_pressure,
        resource_level=resource_level,
        warnings=warnings,
        recommendations=recommendations_list,
    )
