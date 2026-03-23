"""Prometheus Metrics for Me4BrAIn.

Traccia latenze, usage LLM e statistiche di retrieval.
"""

import functools
import time

import structlog
from prometheus_client import Counter, Histogram

logger = structlog.get_logger(__name__)

# Metriche Richieste API
REQUEST_LATENCY = Histogram(
    "me4brain_request_latency_seconds",
    "Latenza delle richieste API",
    ["method", "endpoint", "tenant_id"],
)

# Metriche LLM
LLM_TOKENS_TOTAL = Counter(
    "me4brain_llm_tokens_total",
    "Totale token consumati",
    ["model", "type", "tenant_id"],  # token category values: prompt, completion
)

LLM_REQUEST_LATENCY = Histogram(
    "me4brain_llm_request_latency_seconds",
    "Latenza chiamate LLM",
    ["model", "tenant_id"],
)

# Metriche Retrieval
MEMORY_HITS_TOTAL = Counter(
    "me4brain_memory_hits_total",
    "Totale hit della memoria",
    ["source", "tenant_id"],  # source: episodic, semantic, working
)


class MetricsService:
    """Service per la gestione delle metriche Prometheus."""

    @staticmethod
    def record_request_latency(method: str, endpoint: str, tenant_id: str, duration: float):
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint, tenant_id=tenant_id).observe(
            duration
        )

    @staticmethod
    def record_llm_usage(model: str, tenant_id: str, prompt_tokens: int, completion_tokens: int):
        LLM_TOKENS_TOTAL.labels(model=model, type="prompt", tenant_id=tenant_id).inc(prompt_tokens)
        LLM_TOKENS_TOTAL.labels(model=model, type="completion", tenant_id=tenant_id).inc(
            completion_tokens
        )

    @staticmethod
    def record_llm_latency(model: str, tenant_id: str, duration: float):
        LLM_REQUEST_LATENCY.labels(model=model, tenant_id=tenant_id).observe(duration)

    @staticmethod
    def record_memory_hit(source: str, tenant_id: str):
        MEMORY_HITS_TOTAL.labels(source=source, tenant_id=tenant_id).inc()


def track_latency(method: str, endpoint: str, tenant_id: str = "default"):
    """Decorator per tracciare la latenza di una funzione.

    NOTA: Usa functools.wraps per preservare i metadati della funzione
    originale, necessari affinché FastAPI possa ispezionare correttamente
    i parametri della route.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.perf_counter() - start_time
                MetricsService.record_request_latency(method, endpoint, tenant_id, duration)

        return wrapper

    return decorator
