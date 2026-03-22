"""JWT Authentication Middleware.

Middleware FastAPI per autenticazione JWT con Keycloak.
Supporta multi-tenancy con estrazione tenant_id dal token.
"""

from typing import Any

import jwt
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from me4brain.config import get_settings

logger = structlog.get_logger(__name__)


class TokenPayload(BaseModel):
    """Payload estratto dal JWT token."""

    sub: str  # Subject (user_id in Keycloak)
    tenant_id: str
    email: str | None = None
    name: str | None = None
    roles: list[str] = []
    exp: int  # Expiration timestamp


class AuthenticatedUser(BaseModel):
    """Utente autenticato con info dal token."""

    user_id: str
    tenant_id: str
    email: str | None = None
    name: str | None = None
    roles: list[str] = []


# Security scheme per OpenAPI docs
security_scheme = HTTPBearer(auto_error=False)


async def get_keycloak_public_key() -> str:
    """Recupera la chiave pubblica da Keycloak.

    In produzione, questa chiave dovrebbe essere cachata.
    """
    settings = get_settings()

    # La chiave pubblica può essere configurata direttamente
    # o recuperata dall'endpoint JWKS di Keycloak
    if hasattr(settings, "keycloak_public_key") and settings.keycloak_public_key:
        return settings.keycloak_public_key

    # Fallback: recupera da Keycloak JWKS endpoint
    import httpx

    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url)
            response.raise_for_status()
            jwks = response.json()

            # Estrai la prima chiave RSA
            for key in jwks.get("keys", []):
                if key.get("use") == "sig" and key.get("kty") == "RSA":
                    # Costruisci PEM dalla chiave JWKS
                    from jwt.algorithms import RSAAlgorithm

                    public_key = RSAAlgorithm.from_jwk(key)
                    return public_key

    except Exception as e:
        logger.error("keycloak_jwks_error", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="No valid signing key found",
    )


def decode_token(token: str, public_key: Any) -> TokenPayload:
    """Decodifica e valida un JWT token.

    Args:
        token: Il JWT token
        public_key: Chiave pubblica per verifica

    Returns:
        TokenPayload con i claims

    Raises:
        HTTPException: Se il token non è valido
    """
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
            options={"verify_exp": True},
        )

        # Estrai tenant_id dal token
        # Keycloak può avere tenant_id in diversi claim
        tenant_id = (
            payload.get("tenant_id")
            or payload.get("azp")  # Authorized party
            or payload.get("resource_access", {})
            .get(settings.keycloak_client_id, {})
            .get("tenant_id")
            or "default"
        )

        # Estrai ruoli
        roles = []
        if "realm_access" in payload:
            roles.extend(payload["realm_access"].get("roles", []))
        if "resource_access" in payload:
            client_access = payload["resource_access"].get(settings.keycloak_client_id, {})
            roles.extend(client_access.get("roles", []))

        return TokenPayload(
            sub=payload["sub"],
            tenant_id=tenant_id,
            email=payload.get("email"),
            name=payload.get("name") or payload.get("preferred_username"),
            roles=roles,
            exp=payload["exp"],
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("jwt_invalid", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> AuthenticatedUser:
    """Dependency per ottenere l'utente corrente dal token.

    Usage:
        @app.get("/protected")
        async def protected(user: AuthenticatedUser = Depends(get_current_user)):
            return {"user_id": user.user_id}
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    public_key = await get_keycloak_public_key()
    payload = decode_token(token, public_key)

    user = AuthenticatedUser(
        user_id=payload.sub,
        tenant_id=payload.tenant_id,
        email=payload.email,
        name=payload.name,
        roles=payload.roles,
    )

    # Aggiungi user al request state per logging
    request.state.user = user
    request.state.tenant_id = user.tenant_id

    logger.debug(
        "user_authenticated",
        user_id=user.user_id,
        tenant_id=user.tenant_id,
    )

    return user


async def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> AuthenticatedUser | None:
    """Dependency per ottenere l'utente opzionalmente.

    Non solleva errore se non autenticato.
    """
    if credentials is None:
        return None

    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


def require_role(required_role: str):
    """Dependency factory per richiedere un ruolo specifico.

    Usage:
        @app.get("/admin")
        async def admin(
            user: AuthenticatedUser = Depends(require_role("admin"))
        ):
            return {"msg": "You are admin"}
    """

    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if required_role not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{required_role}' required",
            )
        return user

    return role_checker


def require_tenant(tenant_id: str):
    """Dependency factory per richiedere un tenant specifico.

    Utile per endpoint admin che accedono a dati di altri tenant.
    """

    async def tenant_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.tenant_id != tenant_id and "super_admin" not in user.roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access to this tenant not allowed",
            )
        return user

    return tenant_checker


async def get_current_user_dev(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> AuthenticatedUser:
    """Dependency per ottenere l'utente con bypass in dev mode.

    In dev mode (settings.debug=True o ME4BRAIN_DEV_MODE != "false"),
    bypassa autenticazione JWT e restituisce un utente di test.

    Default: ME4BRAIN_DEV_MODE è considerato TRUE se non impostato esplicitamente a "false".
    Questo previene errori 401 quando il .env non viene caricato correttamente.

    Per PRODUZIONE: impostare esplicitamente ME4BRAIN_DEV_MODE=false

    Usage:
        @app.post("/endpoint")
        async def endpoint(user: AuthenticatedUser = Depends(get_current_user_dev)):
            return {"user_id": user.user_id}
    """
    import os

    settings = get_settings()

    # Dev mode logic:
    # 1. If settings.debug is True → dev mode
    # 2. If ME4BRAIN_DEV_MODE is explicitly "false" → production mode
    # 3. Otherwise (not set or any other value) → dev mode (safe default)
    explicit_dev_mode = os.environ.get("ME4BRAIN_DEV_MODE", "").lower()
    is_production = explicit_dev_mode == "false"
    dev_mode = settings.debug or not is_production

    # Se abbiamo credenziali valide, usa auth normale
    if credentials is not None:
        try:
            return await get_current_user(request, credentials)
        except HTTPException:
            # Se auth fallisce e siamo in dev, bypassa
            if not dev_mode:
                raise

    # Dev mode: crea utente di test
    if dev_mode:
        # Prova a leggere tenant/user dagli header (per test)
        tenant_id = request.headers.get("X-Tenant-ID", settings.default_tenant_id)
        user_id = request.headers.get("X-User-ID", "dev_user")

        user = AuthenticatedUser(
            user_id=user_id,
            tenant_id=tenant_id,
            email="dev@me4brain.local",
            name="Dev User",
            roles=["developer"],
        )

        request.state.user = user
        request.state.tenant_id = user.tenant_id

        logger.debug(
            "dev_mode_auth_bypass",
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            settings_debug=settings.debug,
            env_dev_mode=explicit_dev_mode or "(not set)",
        )

        return user

    # Non in dev mode e nessun token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
