"""Rate Limiting Middleware.

Implementa rate limiting server-side usando slowapi con Redis backend.
"""

import structlog
from fastapi import Request
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)


def get_user_identifier(request: Request) -> str:
    """Estrae identificatore utente per rate limiting.

    Priorità:
    1. tenant_id dall'header Authorization (se autenticato)
    2. X-Tenant-ID header
    3. IP address (fallback)
    """
    # Prova a ottenere tenant_id dall'header
    tenant_id = request.headers.get("X-Tenant-ID")
    if tenant_id:
        return f"tenant:{tenant_id}"

    # Fallback a IP
    return f"ip:{get_remote_address(request)}"


def create_limiter() -> Limiter:
    """Crea il limiter con configurazione appropriata."""
    settings = get_settings()

    # Usa Redis se disponibile, altrimenti in-memory
    redis_url = getattr(settings, "redis_url", None)

    if redis_url:
        storage_uri = redis_url
        logger.info("rate_limiter_using_redis", redis_url=redis_url[:30] + "...")
    else:
        storage_uri = "memory://"
        logger.info("rate_limiter_using_memory")

    return Limiter(
        key_func=get_user_identifier,
        default_limits=["100/minute"],
        storage_uri=storage_uri,
        strategy="fixed-window",
    )


# Singleton limiter
limiter = create_limiter()


# Rate limits per endpoint category
RATE_LIMITS = {
    # Cognitive queries (costose)
    "cognitive": "10/minute",
    # Domain queries
    "domain": "30/minute",
    # Tool execution
    "tool": "60/minute",
    # Working memory (veloci)
    "working": "100/minute",
    # Search/retrieval
    "search": "50/minute",
    # Admin endpoints
    "admin": "20/minute",
}


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Handler per rate limit exceeded."""
    from fastapi.responses import JSONResponse

    logger.warning(
        "rate_limit_exceeded",
        path=request.url.path,
        limit=str(exc.detail),
        identifier=get_user_identifier(request),
    )

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Rate limit exceeded: {exc.detail}",
            "retry_after": getattr(exc, "retry_after", 60),
        },
    )
