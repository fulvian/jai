"""Health Check Routes.

Endpoints per verificare lo stato di salute del sistema e dei suoi componenti.
Include checks per Redis, Qdrant, Neo4j, database, queue, e LLM providers.
"""

import asyncio
import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Health"])


class ServiceHealth(BaseModel):
    """Stato di un singolo servizio."""

    name: str
    status: str  # "ok", "degraded", "error"
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class HealthStatus(BaseModel):
    """Modello risposta health check."""

    status: str  # "healthy", "degraded", "unhealthy"
    version: str
    uptime_seconds: float
    services: list[ServiceHealth]


class ReadinessResponse(BaseModel):
    """Risposta readiness check."""

    ready: bool
    checks: list[ServiceHealth]
    critical_failures: list[str] = Field(default_factory=list)


# Track startup time
_startup_time: float | None = None


def set_startup_time() -> None:
    """Chiamato al startup dell'app."""
    global _startup_time
    _startup_time = time.time()


def get_uptime() -> float:
    """Ritorna uptime in secondi."""
    if _startup_time is None:
        return 0.0
    return time.time() - _startup_time


# =============================================================================
# Service Checks
# =============================================================================


async def check_redis() -> ServiceHealth:
    """Check Redis connectivity."""
    start = time.time()
    try:
        from me4brain.config import get_settings

        settings = get_settings()
        redis_url = getattr(settings, "redis_url", "redis://localhost:6379")

        import redis.asyncio as redis

        client = redis.from_url(redis_url, decode_responses=True)
        await client.ping()
        await client.close()

        latency = (time.time() - start) * 1000
        return ServiceHealth(
            name="redis",
            status="ok",
            latency_ms=latency,
        )
    except Exception as e:
        return ServiceHealth(
            name="redis",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_qdrant() -> ServiceHealth:
    """Check Qdrant connectivity."""
    start = time.time()
    try:
        from qdrant_client import AsyncQdrantClient

        from me4brain.config import get_settings

        settings = get_settings()
        # Usa HTTP port per REST API
        qdrant_host = getattr(settings, "qdrant_host", "localhost")
        qdrant_port = getattr(settings, "qdrant_http_port", 6333)
        qdrant_url = f"http://{qdrant_host}:{qdrant_port}"

        client = AsyncQdrantClient(url=qdrant_url, timeout=5)
        collections = await client.get_collections()
        await client.close()

        latency = (time.time() - start) * 1000
        return ServiceHealth(
            name="qdrant",
            status="ok",
            latency_ms=latency,
            details={"collections_count": len(collections.collections)},
        )
    except Exception as e:
        return ServiceHealth(
            name="qdrant",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_neo4j() -> ServiceHealth:
    """Check Neo4j connectivity."""
    start = time.time()
    try:
        from me4brain.memory import get_semantic_memory

        semantic = get_semantic_memory()
        driver = await semantic.get_driver()

        if driver is None:
            raise RuntimeError("Neo4j driver not initialized")

        # Simple query to verify connectivity
        async with driver.session() as session:
            result = await session.run("MATCH (n) RETURN count(n) as cnt LIMIT 1")
            record = await result.single()
            count = record["cnt"] if record else 0

        latency = (time.time() - start) * 1000
        return ServiceHealth(
            name="neo4j",
            status="ok",
            latency_ms=latency,
            details={"node_count": count},
        )
    except Exception as e:
        return ServiceHealth(
            name="neo4j",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_tool_index() -> ServiceHealth:
    """Check if the Tool Index exists in Qdrant."""
    start = time.time()
    try:
        import os

        from qdrant_client import AsyncQdrantClient

        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        client = AsyncQdrantClient(url=qdrant_url, timeout=5)

        # Check if collection exists (check both unified and legacy for health)
        collections_to_check = ["me4brain_capabilities", "tools", "memories"]
        for collection_name in collections_to_check:
            try:
                if await client.collection_exists(collection_name):
                    break
            except Exception:
                continue
        else:
            # None of the expected collections found
            await client.close()
            return ServiceHealth(
                name="tool_index",
                status="error",
                latency_ms=(time.time() - start) * 1000,
                error="Nessuna collection di tool trovata in Qdrant",
            )

        await client.close()

        latency = (time.time() - start) * 1000
        return ServiceHealth(
            name="tool_index",
            status="ok",
            latency_ms=latency,
            details={"collection": collection_name},
        )
    except Exception as e:
        return ServiceHealth(
            name="tool_index",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_bge_m3() -> ServiceHealth:
    """Check BGE-M3 embedding model status.

    Critical for Issue #1: BGE-M3 cold start richiede ~30-60 secondi.
    Se il modello non è caricato, segnaliamo "loading" invece di errore.
    """
    start = time.time()
    try:
        from me4brain.embeddings import get_embedding_service

        emb = get_embedding_service()

        # Check if model is loaded (attribute check)
        # NOTE: BGEM3Service stores model as self.model (NOT self._model)
        if hasattr(emb, "model") and emb.model is not None:
            # Quick test embedding
            test_vec = emb.embed_query("test")
            dim = len(test_vec)

            latency = (time.time() - start) * 1000
            return ServiceHealth(
                name="bge_m3",
                status="ok",
                latency_ms=latency,
                details={"dimension": dim, "model_loaded": True},
            )
        else:
            # Model not yet loaded
            return ServiceHealth(
                name="bge_m3",
                status="loading",
                latency_ms=(time.time() - start) * 1000,
                details={"model_loaded": False},
            )
    except Exception as e:
        error_msg = str(e)[:200]
        # Distinguish loading from actual errors
        if "loading" in error_msg.lower() or "initializing" in error_msg.lower():
            return ServiceHealth(
                name="bge_m3",
                status="loading",
                latency_ms=(time.time() - start) * 1000,
                details={"model_loaded": False},
            )
        return ServiceHealth(
            name="bge_m3",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=error_msg,
        )


async def check_database() -> ServiceHealth:
    """Check PostgreSQL/SQLite database connectivity."""
    start = time.time()
    try:
        from me4brain.database.connection import get_session_context

        async with get_session_context() as session:
            # Simple query to verify connectivity
            from sqlalchemy import text

            result = await session.execute(text("SELECT 1"))
            result.scalar()

        latency = (time.time() - start) * 1000
        return ServiceHealth(
            name="database",
            status="ok",
            latency_ms=latency,
        )
    except Exception as e:
        return ServiceHealth(
            name="database",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_queue() -> ServiceHealth:
    """Check Redis queue service status."""
    start = time.time()
    try:
        from me4brain.queue import get_queue_manager

        queue = get_queue_manager()
        stats = await queue.get_queue_stats()

        latency = (time.time() - start) * 1000
        return ServiceHealth(
            name="queue",
            status="ok",
            latency_ms=latency,
            details={
                "pending_tasks": stats.get("total_pending", 0),
                "running": stats.get("running", False),
            },
        )
    except Exception as e:
        return ServiceHealth(
            name="queue",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_tracing() -> ServiceHealth:
    """Check Jaeger tracing connectivity."""
    start = time.time()
    try:
        from me4brain.observability.tracing import is_trace_initialized

        initialized = is_trace_initialized()
        latency = (time.time() - start) * 1000

        if initialized:
            return ServiceHealth(
                name="tracing",
                status="ok",
                latency_ms=latency,
                details={"jaeger_configured": True},
            )
        else:
            return ServiceHealth(
                name="tracing",
                status="degraded",
                latency_ms=latency,
                details={"jaeger_configured": False},
            )
    except Exception as e:
        return ServiceHealth(
            name="tracing",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


async def check_llm_providers() -> ServiceHealth:
    """Check LLM providers (Ollama, LM Studio) availability."""
    start = time.time()
    try:
        from me4brain.llm.health import get_llm_health_checker

        checker = get_llm_health_checker()

        # Check providers in parallel
        ollama_result, lmstudio_result = await asyncio.gather(
            checker.check_ollama(),
            checker.check_lmstudio(),
            return_exceptions=True,
        )

        # Handle exceptions
        if isinstance(ollama_result, Exception):
            ollama_healthy = False
            str(ollama_result)[:100]
        else:
            ollama_healthy = ollama_result.healthy

        if isinstance(lmstudio_result, Exception):
            lmstudio_healthy = False
            str(lmstudio_result)[:100]
        else:
            lmstudio_healthy = lmstudio_result.healthy

        # Overall status
        any_healthy = ollama_healthy or lmstudio_healthy
        overall_status = "ok" if any_healthy else "error"

        latency = (time.time() - start) * 1000
        details = {}
        if isinstance(ollama_result, Exception):
            details["ollama_error"] = str(ollama_result)[:100]
        else:
            details["ollama_healthy"] = ollama_result.healthy
            if ollama_result.model_loaded:
                details["ollama_model"] = ollama_result.model_loaded

        if isinstance(lmstudio_result, Exception):
            details["lmstudio_error"] = str(lmstudio_result)[:100]
        else:
            details["lmstudio_healthy"] = lmstudio_result.healthy
            if lmstudio_result.model_loaded:
                details["lmstudio_model"] = lmstudio_result.model_loaded

        return ServiceHealth(
            name="llm_providers",
            status=overall_status,
            latency_ms=latency,
            details=details,
        )
    except Exception as e:
        return ServiceHealth(
            name="llm_providers",
            status="error",
            latency_ms=(time.time() - start) * 1000,
            error=str(e)[:200],
        )


# =============================================================================
# Endpoints
# =============================================================================


@router.get(
    "/health",
    response_model=HealthStatus,
    status_code=status.HTTP_200_OK,
    summary="Health Check",
    description="Verifica lo stato di salute del sistema.",
)
async def health_check() -> HealthStatus:
    """Endpoint principale per health check.

    Ritorna lo stato generale del sistema. Per i load balancer e orchestratori.
    """
    # Run all checks in parallel
    import asyncio

    from me4brain import __version__

    checks = await asyncio.gather(
        check_redis(),
        check_qdrant(),
        check_neo4j(),
        check_tool_index(),
        check_bge_m3(),
        check_database(),
        check_queue(),
        check_tracing(),
        check_llm_providers(),
        return_exceptions=True,
    )

    services = []
    for check in checks:
        if isinstance(check, Exception):
            services.append(ServiceHealth(name="unknown", status="error", error=str(check)))
        else:
            services.append(check)

    # Determina status globale
    error_count = sum(1 for s in services if s.status == "error")
    if error_count == 0:
        overall_status = "healthy"
    elif error_count < len(services):
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthStatus(
        status=overall_status,
        version=__version__,
        uptime_seconds=get_uptime(),
        services=services,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness Check",
    description="Verifica se il sistema è pronto a ricevere richieste.",
)
async def readiness_check() -> ReadinessResponse:
    """Readiness probe per Kubernetes.

    Verifica che tutti i servizi critici siano raggiungibili.
    Ritorna 503 se non pronto.
    """
    import asyncio

    # Critical services that must be up for the system to operate
    critical_services = {"redis", "qdrant", "database", "llm_providers"}

    checks = await asyncio.gather(
        check_redis(),
        check_qdrant(),
        check_database(),
        check_llm_providers(),
    )

    critical_failures = []
    for check in checks:
        if check.name in critical_services and check.status == "error":
            critical_failures.append(check.name)

    ready = len(critical_failures) == 0

    response = ReadinessResponse(
        ready=ready,
        checks=list(checks),
        critical_failures=critical_failures,
    )

    if not ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=response.model_dump(),
        )

    return response


@router.get(
    "/health/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness Check",
    description="Verifica se il processo è vivo.",
)
async def liveness_check() -> dict[str, Any]:
    """Liveness probe per Kubernetes.

    Ritorna sempre OK se il processo risponde.
    """
    return {
        "status": "alive",
        "uptime_seconds": get_uptime(),
    }


class ModelsStatusResponse(BaseModel):
    """Stato dei modelli AI."""

    ready: bool
    models: list[ServiceHealth]
    message: str


@router.get(
    "/health/models",
    response_model=ModelsStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="AI Models Status",
    description="Verifica lo stato dei modelli AI (BGE-M3). Usa per sapere se il sistema è pronto per query semantiche.",
)
async def models_status() -> ModelsStatusResponse:
    """Endpoint per verificare stato modelli AI.

    Critico per Issue #1: Gateway può verificare se BGE-M3 è caricato
    prima di inviare query, evitando timeout durante cold start.

    Returns:
        ModelsStatusResponse con stato di tutti i modelli
    """
    bge_status = await check_bge_m3()

    models = [bge_status]
    ready = bge_status.status == "ok"

    if ready:
        message = "All AI models loaded and ready"
    elif bge_status.status == "loading":
        message = "BGE-M3 model is still loading (~30-60s). Query may timeout."
    else:
        message = f"BGE-M3 error: {bge_status.error}"

    return ModelsStatusResponse(
        ready=ready,
        models=models,
        message=message,
    )
