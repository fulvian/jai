"""LLM Health Check System - Robust Provider Detection.

Fornisce health checks e fallback intelligence per:
- Ollama (http://localhost:11434)
- LM Studio (http://localhost:1234)
- NanoGPT Cloud (https://nano-gpt.com)

Supporta fallback automatico quando provider primario è offline.
"""

import asyncio
from dataclasses import dataclass

import httpx
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class HealthCheckResult:
    """Risultato di un health check."""

    provider: str
    healthy: bool
    latency_ms: float
    error: str | None = None
    model_loaded: str | None = None


class LLMHealthChecker:
    """Monitora salute dei provider LLM e determina fallback intelligente."""

    def __init__(self):
        self._cache: dict[str, HealthCheckResult] = {}
        self._cache_ttl = 30  # 30 secondi

    async def check_ollama(
        self, base_url: str = "http://localhost:11434", required_model: str | None = None
    ) -> HealthCheckResult:
        """Controlla se Ollama è disponibile e ha il modello richiesto caricato.

        Args:
            base_url: URL base di Ollama (default: localhost:11434)
            required_model: Modello specifico da verificare (es. 'qwen3:14b')

        Returns:
            HealthCheckResult con status e latenza
        """
        start = asyncio.get_event_loop().time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/api/tags", follow_redirects=True)
                latency_ms = (asyncio.get_event_loop().time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    model_names = [m.get("name") for m in models]

                    # Verifica il modello richiesto se specificato
                    if required_model:
                        # Check exact match or match with tag variations
                        base_model = (
                            required_model.split(":")[0]
                            if ":" in required_model
                            else required_model
                        )
                        has_required_model = required_model in model_names or any(
                            base_model in m for m in model_names
                        )

                        if not has_required_model:
                            logger.warning(
                                "ollama_required_model_not_loaded",
                                required_model=required_model,
                                available_models=model_names[:5],
                                latency_ms=latency_ms,
                            )
                            return HealthCheckResult(
                                provider="ollama",
                                healthy=False,
                                latency_ms=latency_ms,
                                error=f"Required model '{required_model}' not loaded. Available: {', '.join(model_names[:3])}",
                            )

                    logger.info(
                        "ollama_health_ok",
                        latency_ms=latency_ms,
                        models_count=len(models),
                        models=model_names[:3],  # First 3
                        required_model=required_model,
                    )

                    return HealthCheckResult(
                        provider="ollama",
                        healthy=True,
                        latency_ms=latency_ms,
                        model_loaded=model_names[0] if model_names else None,
                    )
                else:
                    return HealthCheckResult(
                        provider="ollama",
                        healthy=False,
                        latency_ms=latency_ms,
                        error=f"HTTP {response.status_code}",
                    )

        except TimeoutError:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning("ollama_health_timeout", latency_ms=latency_ms)
            return HealthCheckResult(
                provider="ollama",
                healthy=False,
                latency_ms=latency_ms,
                error="Timeout (5s)",
            )

        except httpx.ConnectError as e:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning(
                "ollama_health_connect_error",
                latency_ms=latency_ms,
                error=str(e),
            )
            return HealthCheckResult(
                provider="ollama",
                healthy=False,
                latency_ms=latency_ms,
                error="Connection refused (is Ollama running?)",
            )

        except Exception as e:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.error("ollama_health_error", latency_ms=latency_ms, error=str(e))
            return HealthCheckResult(
                provider="ollama",
                healthy=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def check_lmstudio(self, base_url: str = "http://localhost:1234") -> HealthCheckResult:
        """Controlla se LM Studio è disponibile.

        Args:
            base_url: URL base di LM Studio (default: localhost:1234)

        Returns:
            HealthCheckResult con status e latenza
        """
        start = asyncio.get_event_loop().time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/v1/models", follow_redirects=True)
                latency_ms = (asyncio.get_event_loop().time() - start) * 1000

                if response.status_code == 200:
                    data = response.json()
                    models = data.get("data", [])
                    model_names = [m.get("id") for m in models]

                    logger.info(
                        "lmstudio_health_ok",
                        latency_ms=latency_ms,
                        models_count=len(models),
                    )

                    return HealthCheckResult(
                        provider="lmstudio",
                        healthy=True,
                        latency_ms=latency_ms,
                        model_loaded=model_names[0] if model_names else None,
                    )
                else:
                    return HealthCheckResult(
                        provider="lmstudio",
                        healthy=False,
                        latency_ms=latency_ms,
                        error=f"HTTP {response.status_code}",
                    )

        except TimeoutError:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning("lmstudio_health_timeout", latency_ms=latency_ms)
            return HealthCheckResult(
                provider="lmstudio",
                healthy=False,
                latency_ms=latency_ms,
                error="Timeout (5s) - is LM Studio desktop app running?",
            )

        except httpx.ConnectError:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning("lmstudio_health_connect_error", latency_ms=latency_ms)
            return HealthCheckResult(
                provider="lmstudio",
                healthy=False,
                latency_ms=latency_ms,
                error="Connection refused (LM Studio desktop not running)",
            )

        except Exception as e:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.error("lmstudio_health_error", latency_ms=latency_ms, error=str(e))
            return HealthCheckResult(
                provider="lmstudio",
                healthy=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def check_nanogpt(self, base_url: str = "https://nano-gpt.com/api") -> HealthCheckResult:
        """Controlla se NanoGPT cloud è disponibile.

        Args:
            base_url: URL base di NanoGPT (default: https://nano-gpt.com/api)

        Returns:
            HealthCheckResult con status e latenza
        """
        start = asyncio.get_event_loop().time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{base_url}/health")
                latency_ms = (asyncio.get_event_loop().time() - start) * 1000

                if response.status_code in (
                    200,
                    404,
                ):  # 404 = health endpoint non exist, ma server up
                    logger.info("nanogpt_health_ok", latency_ms=latency_ms)
                    return HealthCheckResult(
                        provider="nanogpt",
                        healthy=True,
                        latency_ms=latency_ms,
                    )
                else:
                    return HealthCheckResult(
                        provider="nanogpt",
                        healthy=False,
                        latency_ms=latency_ms,
                        error=f"HTTP {response.status_code}",
                    )

        except TimeoutError:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.warning("nanogpt_health_timeout", latency_ms=latency_ms)
            return HealthCheckResult(
                provider="nanogpt",
                healthy=False,
                latency_ms=latency_ms,
                error="Timeout (10s) - network issue or service down",
            )

        except Exception as e:
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000
            logger.error("nanogpt_health_error", latency_ms=latency_ms, error=str(e))
            return HealthCheckResult(
                provider="nanogpt",
                healthy=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def get_best_provider(self, required_model: str | None = None) -> str:
        """Determina il miglior provider disponibile nel seguente ordine:
        1. Ollama (local, fast, no API keys required)
        2. LM Studio (local, reliable, UI-based)
        3. NanoGPT (cloud, slow, requires API key but always available)

        Args:
            required_model: Modello specifico da verificare (es. 'qwen3:14b')

        Returns:
            Nome del provider migliore disponibile
        """
        from me4brain.llm.config import get_llm_config

        config = get_llm_config()

        # Use routing model if no specific model required
        if required_model is None:
            required_model = config.model_routing

        # Health check in parallelo
        results = await asyncio.gather(
            self.check_ollama(config.ollama_base_url, required_model=required_model),
            self.check_lmstudio(config.lmstudio_base_url),
            self.check_nanogpt(config.nanogpt_base_url),
        )

        logger.info(
            "llm_health_check_complete",
            ollama=results[0].healthy,
            lmstudio=results[1].healthy,
            nanogpt=results[2].healthy,
            required_model=required_model,
        )

        # Priorità: Ollama > LM Studio > NanoGPT
        if results[0].healthy:
            logger.info("best_provider_selected", provider="ollama", model=required_model)
            return "ollama"
        elif results[1].healthy:
            logger.warning(
                "best_provider_selected_degraded",
                provider="lmstudio",
                reason="Ollama offline or model not loaded",
            )
            return "lmstudio"
        else:
            logger.warning(
                "best_provider_selected_degraded",
                provider="nanogpt",
                reason="Both local providers offline - falling back to cloud",
            )
            return "nanogpt"


# Singleton instance
_health_checker: LLMHealthChecker | None = None


def get_llm_health_checker() -> LLMHealthChecker:
    """Get or create the health checker singleton."""
    global _health_checker
    if _health_checker is None:
        _health_checker = LLMHealthChecker()
    return _health_checker
