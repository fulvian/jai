"""Provider Factory - Dispatcher per provider LLM con Health Check.

Architettura robusta:
1. **Ollama-First**: Priorità massima (local, no API keys, fast)
2. **LM Studio Fallback**: Se Ollama offline (local, reliable UI)
3. **NanoGPT Cloud**: Se entrambi offline (cloud, always available)

Health checks automatici determinano il miglior provider disponibile.
Supporta fallback intelligente e caching decisioni.
"""

from __future__ import annotations

import structlog
import re
from me4brain.llm.base import LLMProvider
from me4brain.llm.config import get_llm_config
from me4brain.llm.health import get_llm_health_checker
from me4brain.llm.nanogpt import get_llm_client
from me4brain.llm.ollama import get_ollama_client
from me4brain.llm.fallback import FallbackProvider

logger = structlog.get_logger(__name__)


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
                # Non è un UUID (es. "qwen3.5:4b" o "mlx/qwen3.5:9b")
                # Treat as Ollama model (Ollama uses colons in tags)
                logger.debug("resolve_model_client_ollama", model=model_id)
                return get_ollama_client(), model_id

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

    # Modello semplice - priorizza Ollama rispetto a NanoGPT
    # Per MLX models, usa ancora LM Studio via NanoGPT
    if model_id.endswith("-mlx") or model_id.startswith("mlx-"):
        logger.debug("resolve_model_client_lmstudio", model=model_id)
        return get_llm_client(), model_id

    # Default per modelli semplici: prova Ollama first
    if config.llm_local_only:
        logger.debug("resolve_model_client_ollama_local_only", model=model_id)
        return get_ollama_client(), model_id

    # Modelli con famiglia locale comune: usa Ollama
    if model_id.startswith(("qwen", "llama", "mistral")) and "/" not in model_id:
        logger.debug("resolve_model_client_ollama_family", model=model_id)
        return get_ollama_client(), model_id

    # Default: usa NanoGPT cloud
    logger.debug("resolve_model_client_cloud", model=model_id)
    return get_llm_client(), model_id


async def get_reasoning_client() -> LLMProvider:
    """Restituisce il client per ragionamento, sintesi e task complessi.

    Implementa Ollama-First con fallback intelligente:
    1. Ollama (local, fast, no API keys) - FIRST TRY
    2. LM Studio (local, reliable) - IF OLLAMA DOWN
    3. NanoGPT Cloud (cloud, always available) - LAST RESORT

    Health checks automatici determinano il provider migliore disponibile.
    """
    config = get_llm_config()
    health_checker = get_llm_health_checker()

    if config.llm_local_only or config.use_local_tool_calling:
        # Determina miglior provider locale disponibile
        best_provider = await health_checker.get_best_provider()

        if best_provider == "ollama":
            logger.debug(
                "provider_factory_reasoning_ollama_selected",
                provider="ollama",
                model=config.ollama_model,
                strategy="ollama_first",
            )
            return get_ollama_client()

        elif best_provider == "lmstudio":
            logger.warning(
                "provider_factory_reasoning_lmstudio_selected",
                provider="lmstudio",
                reason="Ollama offline",
            )
            return get_llm_client()  # NanoGPT routes MLX to LM Studio

        else:  # nanogpt
            logger.warning(
                "provider_factory_reasoning_nanogpt_fallback",
                provider="nanogpt",
                reason="Both local providers offline",
            )
            return get_llm_client()

    # Non-local mode: use cloud
    logger.debug("provider_factory_reasoning_cloud", provider="nanogpt", model=config.model_primary)
    return get_llm_client()


async def get_tool_calling_client() -> LLMProvider:
    """Restituisce il client per tool selection e argument extraction.

    Implementa Ollama-First strategy:
    1. Ollama (local, fast) - PRIMARY
    2. LM Studio (local, reliable) - FALLBACK
    3. NanoGPT (cloud, always available) - LAST RESORT
    """
    config = get_llm_config()
    health_checker = get_llm_health_checker()

    if config.llm_local_only:
        best_provider = await health_checker.get_best_provider()

        if best_provider == "ollama":
            logger.debug(
                "provider_factory_tool_calling_ollama",
                provider="ollama",
                model=config.ollama_model,
            )
            return get_ollama_client()

        elif best_provider == "lmstudio":
            logger.warning(
                "provider_factory_tool_calling_lmstudio",
                provider="lmstudio",
                reason="Ollama offline",
            )
            return get_llm_client()

        else:  # nanogpt
            logger.warning(
                "provider_factory_tool_calling_nanogpt",
                provider="nanogpt",
                reason="Both local providers offline",
            )
            return get_llm_client()

    # Non-local mode with local tool calling enabled
    if config.use_local_tool_calling:
        best_provider = await health_checker.get_best_provider()

        if best_provider in ("ollama", "lmstudio"):
            logger.debug(
                "provider_factory_tool_calling_local",
                provider=best_provider,
            )
            return get_ollama_client() if best_provider == "ollama" else get_llm_client()

        if not config.llm_allow_cloud_fallback:
            logger.warning(
                "provider_factory_tool_calling_no_cloud_fallback",
                provider="ollama_only",
            )
            return get_ollama_client()

        local_client = get_ollama_client()
        cloud_client = get_llm_client()
        logger.debug("provider_factory_tool_calling", strategy="fallback_ollama_first")
        return FallbackProvider(
            primary=local_client,
            fallback=cloud_client,
            name="tool_calling",
            fallback_model=config.model_fallback,
        )

    logger.debug(
        "provider_factory_tool_calling_cloud", provider="nanogpt", model=config.model_agentic
    )
    return get_llm_client()
