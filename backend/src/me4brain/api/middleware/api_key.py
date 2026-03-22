"""API Key Authentication Middleware.

Middleware semplice per autenticazione via header X-API-Key.
Se ME4BRAIN_API_KEY non è configurata, il middleware è in bypass mode.
"""

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)

# Schema per OpenAPI docs
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),
) -> str:
    """Dependency per richiedere API Key.

    Se ME4BRAIN_API_KEY è configurata, richiede header matching.
    Altrimenti, bypass (development mode).

    Usage:
        @app.get("/protected")
        async def protected(api_key: str = Depends(get_api_key)):
            return {"status": "authenticated"}
    """
    settings = get_settings()

    # Bypass se API key non configurata (development)
    if settings.api_key is None:
        logger.debug("api_key_bypass", reason="not_configured")
        return "bypass"

    expected_key = settings.api_key.get_secret_value()

    # Verifica header
    if api_key is None:
        logger.warning("api_key_missing")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != expected_key:
        logger.warning("api_key_invalid")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Log accesso autenticato
    logger.debug("api_key_authenticated")
    return api_key


async def get_optional_api_key(
    request: Request,
    api_key: str | None = Depends(api_key_header),
) -> str | None:
    """Dependency opzionale per API Key.

    Non solleva errore se non autenticato.
    Utile per endpoint che supportano sia auth che accesso pubblico.
    """
    settings = get_settings()

    # Bypass se non configurata
    if settings.api_key is None:
        return None

    expected_key = settings.api_key.get_secret_value()

    # Verifica se presente e valida
    if api_key and api_key == expected_key:
        logger.debug("api_key_authenticated")
        return api_key

    return None


def require_api_key():
    """Factory per richiedere API Key obbligatoria.

    Usage:
        @app.get("/admin")
        async def admin(api_key: str = Depends(require_api_key())):
            return {"status": "admin access"}
    """
    return get_api_key
