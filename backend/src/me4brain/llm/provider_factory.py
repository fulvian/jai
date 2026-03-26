"""Provider Factory - Dispatcher per provider LLM con Health Check.

Architettura robusta:
1. **LM Studio ONLY**: Unico provider locale (local, reliable UI)
2. **NanoGPT Cloud**: Fallback cloud (always available)

NOTA: Ollama è stato rimosso. Tutti i provider locali usano LM Studio.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import structlog

from me4brain.llm.base import LLMProvider
from me4brain.llm.config import get_llm_config
from me4brain.llm.health import get_llm_health_checker
from me4brain.llm.nanogpt import get_llm_client, get_lmstudio_client

logger = structlog.get_logger(__name__)


@dataclass
class CachedProviderStatus:
    """Cache entry for provider health status with TTL validation."""

    provider: str
    healthy: bool
    checked_at: float
    ttl: float = 30.0  # 30 second cache TTL

    @property
    def is_valid(self) -> bool:
        """Check if cached status is still valid (within TTL)."""
        return (time.time() - self.checked_at) < self.ttl


_provider_cache: CachedProviderStatus | None = None


async def get_cached_best_provider() -> str:
    """Get best provider with caching to avoid repeated health checks.

    Uses cached result if available and fresh (< 30s old), otherwise performs
    new health check and caches the result.

    Returns:
        Provider name: "ollama", "lmstudio", or "nanogpt"
    """
    global _provider_cache

    # Use cache if valid
    if _provider_cache and _provider_cache.is_valid:
        logger.debug(
            "get_cached_best_provider_cache_hit",
            provider=_provider_cache.provider,
            age_seconds=time.time() - _provider_cache.checked_at,
        )
        return _provider_cache.provider

    # Cache miss or expired - perform health check
    health_checker = get_llm_health_checker()
    best = await health_checker.get_best_provider()

    # Update cache
    _provider_cache = CachedProviderStatus(
        provider=best,
        healthy=True,
        checked_at=time.time(),
    )

    logger.debug(
        "get_cached_best_provider_cache_updated",
        provider=best,
    )

    return best


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def resolve_model_client(model_id: str) -> tuple[LLMProvider, str]:
    """Risolve un model_id al client appropriato.

    Supporta due formati:
    1. provider_id:model_id - Usa il provider dinamico dal registry
       Esempio: fa548723-e5d1-4dc9-847b-c729681c852c:mistralai/mistral-large-3
    2. model_id semplice - Usa il client hardcoded (NanoGPT/Ollama)
       Esempio: qwen3.5-4b-mlx, mistralai/mistral-large-3-675b-instruct-2512

    Returns:
        Tuple di (client, actual_model_id)
    """
    config = get_llm_config()

    if ":" in model_id:
        # Formato provider_id:model_id - solo se provider_id è un UUID
        parts = model_id.split(":", 1)
        if len(parts) == 2:
            provider_id, actual_model = parts
            # Verifica che provider_id sia un UUID valido
            if not UUID_PATTERN.match(provider_id):
                # Non è un UUID - verifica se è un provider noto (lm-studio-)
                if provider_id.startswith("lm-studio-"):
                    # LM Studio provider - usa get_lmstudio_client()
                    # Estrae solo il nome del modello senza il prefisso provider
                    logger.debug("resolve_model_client_lmstudio_provider", model=actual_model)
                    return get_lmstudio_client(), actual_model
                # Non è un UUID e non è un provider noto (es. "qwen3.5:4b")
                # Treat as LM Studio model (LM Studio uses colons in model names)
                logger.debug("resolve_model_client_lmstudio_fallback", model=model_id)
                return get_lmstudio_client(), model_id

            if config.llm_local_only:
                raise ValueError("Dynamic provider resolution is disabled in local-only mode")

            logger.debug(
                "resolve_model_client_dynamic",
                provider_id=provider_id,
                model=actual_model,
            )
            from me4brain.llm.dynamic_client import get_client_for_provider

            client = get_client_for_provider(provider_id, actual_model)
            return client, actual_model

    # In local-only, blocca modelli cloud espliciti
    if config.llm_local_only and "/" in model_id:
        raise ValueError(f"Cloud model '{model_id}' blocked because llm_local_only=true")

    # Modello semplice - priorizza Ollama rispetto a NanoGPT
    # Per MLX models, usa ancora LM Studio via NanoGPT
    if model_id.endswith("-mlx") or model_id.startswith("mlx-") or model_id.startswith("mlx/"):
        logger.debug("resolve_model_client_lmstudio", model=model_id)
        return get_llm_client(), model_id

    # Default per modelli semplici: usa LM Studio
    if config.llm_local_only:
        logger.debug("resolve_model_client_lmstudio_local_only", model=model_id)
        return get_lmstudio_client(), model_id

    # Modelli con famiglia locale comune: usa LM Studio (senza /)
    if model_id.startswith(("qwen", "llama", "mistral")) and "/" not in model_id:
        logger.debug("resolve_model_client_lmstudio_family", model=model_id)
        return get_lmstudio_client(), model_id

    # LM Studio models have / in them (e.g., "qwen/qwen3.5-9b") and use - not :
    # Ollama models use : separator (e.g., "qwen3.5:9b")
    # Route models with / to LM Studio
    if "/" in model_id and not model_id.startswith(
        ("mistralai/", "openai/", "anthropic/", "google/")
    ):
        logger.debug("resolve_model_client_lmstudio", model=model_id)
        return get_lmstudio_client(), model_id

    # Default: usa NanoGPT cloud
    logger.debug("resolve_model_client_cloud", model=model_id)
    return get_llm_client(), model_id


def get_reasoning_client() -> LLMProvider:
    """Restituisce il client per ragionamento, sintesi e task complessi.

    Usa LM Studio come provider locale.
    NanoGPT Cloud come fallback.
    """
    config = get_llm_config()
    if config.llm_local_only or config.use_local_tool_calling:
        logger.debug(
            "provider_factory_reasoning_local",
            provider="lmstudio",
            model=config.model_routing,
        )
        return get_lmstudio_client()

    # Non-local mode: use cloud
    logger.debug("provider_factory_reasoning_cloud", provider="nanogpt", model=config.model_primary)
    return get_llm_client()


def get_tool_calling_client() -> LLMProvider:
    """Restituisce il client per tool selection e argument extraction.

    Usa LM Studio come provider locale.
    NanoGPT Cloud come fallback.
    """
    config = get_llm_config()
    if config.llm_local_only:
        logger.debug(
            "provider_factory_tool_calling_local_only",
            provider="lmstudio",
            model=config.model_routing,
        )
        return get_lmstudio_client()

    # Non-local mode with local tool calling enabled
    if config.use_local_tool_calling:
        logger.debug(
            "provider_factory_tool_calling_local",
            provider="lmstudio",
            model=config.model_routing,
        )
        return get_lmstudio_client()

    logger.debug(
        "provider_factory_tool_calling_cloud", provider="nanogpt", model=config.model_agentic
    )
    return get_llm_client()
