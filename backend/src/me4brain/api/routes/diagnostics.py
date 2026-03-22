"""Diagnostic endpoint for LLM provider chain configuration.

Provides health checks and configuration status for:
- Ollama provider (primary)
- LM Studio provider (fallback)
- Model resolution chain
- Fallback cascade status
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["diagnostics"])


@router.get("/v1/diagnostics/llm-chain")
async def diagnose_llm_chain() -> dict[str, Any]:
    """Diagnose the LLM provider chain configuration.

    Returns:
        dict with config, health checks, resolution status, and recommendation

    Example response:
        {
            "config": {
                "model_routing": "llama2",
                "model_primary": "ollama",
                "llm_local_only": True,
                "ollama_base_url": "http://localhost:11434"
            },
            "health": {
                "ollama": {
                    "healthy": True,
                    "error": None,
                    "latency_ms": 45,
                    "models": ["llama2:latest", "neural-chat:latest"]
                },
                "lmstudio": {
                    "healthy": False,
                    "error": "Connection refused",
                    "latency_ms": None
                }
            },
            "resolution": {
                "ok": True,
                "client": "NanoGPTClient",
                "model": "llama2:latest"
            },
            "recommendation": "OK: Ollama is healthy and ready"
        }
    """
    try:
        from me4brain.llm.config import get_llm_config
        from me4brain.llm.health import get_llm_health_checker
        from me4brain.llm.provider_factory import resolve_model_client

        config = get_llm_config()
        checker = get_llm_health_checker()

        # Test each provider asynchronously
        ollama_health = await checker.check_ollama(
            config.ollama_base_url,
            config.model_routing,
        )
        lmstudio_health = await checker.check_lmstudio(config.lmstudio_base_url)

        # Test model resolution
        resolution_ok = False
        resolution_client = None
        resolution_model = None
        resolution_error = None

        try:
            client, model = resolve_model_client(config.model_routing)
            resolution_ok = True
            resolution_client = type(client).__name__
            resolution_model = model
        except Exception as e:
            resolution_ok = False
            resolution_error = str(e)
            logger.error("model_resolution_failed", error=str(e))

        # Generate recommendation based on health status
        recommendation = _generate_recommendation(
            ollama_health,
            lmstudio_health,
            config,
        )

        response: dict[str, Any] = {
            "config": {
                "model_routing": config.model_routing,
                "model_primary": config.model_primary,
                "llm_local_only": config.llm_local_only,
                "ollama_base_url": config.ollama_base_url,
                "lmstudio_base_url": config.lmstudio_base_url,
            },
            "health": {
                "ollama": {
                    "healthy": ollama_health.healthy,
                    "error": ollama_health.error,
                    "latency_ms": ollama_health.latency_ms,
                    "models": ollama_health.available_models or [],
                },
                "lmstudio": {
                    "healthy": lmstudio_health.healthy,
                    "error": lmstudio_health.error,
                    "latency_ms": lmstudio_health.latency_ms,
                },
            },
            "resolution": {
                "ok": resolution_ok,
                "client": resolution_client,
                "model": resolution_model,
                "error": resolution_error,
            },
            "recommendation": recommendation,
        }

        logger.info(
            "llm_chain_diagnostics_completed",
            ollama_healthy=ollama_health.healthy,
            lmstudio_healthy=lmstudio_health.healthy,
            resolution_ok=resolution_ok,
        )

        return response

    except Exception as e:
        logger.error("llm_chain_diagnostics_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to diagnose LLM chain: {str(e)}",
        )


def _generate_recommendation(ollama_health: Any, lmstudio_health: Any, config: Any) -> str:
    """Generate a recommendation based on health status.

    Args:
        ollama_health: Ollama health check result
        lmstudio_health: LM Studio health check result
        config: LLM configuration

    Returns:
        Recommendation string with action items
    """
    if ollama_health.healthy:
        return f"✅ OK: Ollama is healthy and ready with model '{config.model_routing}'"

    if lmstudio_health.healthy:
        return (
            "⚠️ DEGRADED: Ollama is unavailable. Using LM Studio fallback. "
            f"Start Ollama for best performance: ollama pull {config.model_routing}"
        )

    return (
        f"🔴 CRITICAL: No local LLM available. "
        f"Start Ollama with: ollama pull {config.model_routing} && ollama serve"
    )
