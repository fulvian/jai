"""Tenant Middleware - FastAPI middleware per tenant extraction e validation."""

from __future__ import annotations

import re
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from me4brain.core.tenant.context import reset_tenant, set_tenant
from me4brain.core.tenant.store import TenantStore
from me4brain.core.tenant.types import TenantStatus

logger = structlog.get_logger(__name__)


# Public endpoints che non richiedono tenant
DEFAULT_PUBLIC_PATHS: set[str] = {
    "/health",
    "/health/ready",
    "/health/components",
    "/metrics",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/v1/auth/login",
    "/v1/auth/register",
}


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware per estrazione e validazione tenant.

    Ordine di estrazione (priorità):
    1. Header X-Tenant-ID
    2. Subdomain (tenant.example.com)
    3. Path prefix (/tenants/{id}/...)
    4. Query param ?tenant_id=...

    Dopo estrazione:
    - Valida che tenant esista
    - Verifica status (non suspended/deleted)
    - Imposta context per request
    """

    def __init__(
        self,
        app,
        public_paths: set[str] | None = None,
        tenant_store: TenantStore | None = None,
    ):
        """
        Args:
            app: FastAPI app
            public_paths: Paths che non richiedono tenant
            tenant_store: Store per validazione tenant (opzionale)
        """
        super().__init__(app)
        self.public_paths = public_paths or DEFAULT_PUBLIC_PATHS
        self.tenant_store = tenant_store
        self._path_pattern = re.compile(r"^/tenants/([^/]+)/")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with tenant context."""
        path = request.url.path

        # Skip public endpoints
        if self._is_public(path):
            return await call_next(request)

        # Extract tenant ID
        tenant_id = self._extract_tenant_id(request)

        if not tenant_id:
            logger.warning("tenant_id_missing", path=path)
            return JSONResponse(
                status_code=400,
                content={"error": "Tenant ID required", "code": "TENANT_REQUIRED"},
            )

        # Validate tenant
        config = await self._validate_tenant(tenant_id)

        if config is None:
            logger.warning("tenant_not_found", tenant_id=tenant_id)
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid tenant", "code": "INVALID_TENANT"},
            )

        if config.status == TenantStatus.SUSPENDED:
            return JSONResponse(
                status_code=403,
                content={"error": "Tenant suspended", "code": "TENANT_SUSPENDED"},
            )

        if config.status == TenantStatus.DELETED:
            return JSONResponse(
                status_code=410,
                content={"error": "Tenant deleted", "code": "TENANT_DELETED"},
            )

        # Extract user ID (opzionale)
        user_id = request.headers.get("X-User-ID")

        # Set context
        token = set_tenant(tenant_id, config, user_id)

        try:
            # Log con tenant per tracing
            logger.bind(tenant_id=tenant_id, user_id=user_id)

            response = await call_next(request)

            # Add tenant header alla response
            response.headers["X-Tenant-ID"] = tenant_id

            return response

        finally:
            reset_tenant(token)

    def _is_public(self, path: str) -> bool:
        """Check se path è pubblico."""
        # Exact match
        if path in self.public_paths:
            return True

        # Prefix match per admin tenant creation
        if path.startswith("/v1/admin/tenants") and not path.endswith("/usage"):
            return True

        return False

    def _extract_tenant_id(self, request: Request) -> str | None:
        """
        Estrae tenant ID dalla request.

        Ordine priorità:
        1. Header X-Tenant-ID
        2. Subdomain
        3. Path prefix
        4. Query param
        """
        # 1. Header (preferito)
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            return tenant_id.strip()

        # 2. Subdomain (tenant.api.example.com)
        host = request.url.hostname
        if host and "." in host:
            subdomain = host.split(".")[0]
            # Skip common subdomains
            if subdomain not in {"api", "www", "app", "localhost"}:
                return subdomain

        # 3. Path prefix (/tenants/{id}/...)
        match = self._path_pattern.match(request.url.path)
        if match:
            return match.group(1)

        # 4. Query param
        tenant_id = request.query_params.get("tenant_id")
        if tenant_id:
            return tenant_id.strip()

        return None

    async def _validate_tenant(self, tenant_id: str):
        """Valida che tenant esista."""
        if self.tenant_store:
            return await self.tenant_store.get(tenant_id)

        # Fallback: usa store globale
        store = TenantStore()
        return await store.get(tenant_id)


# --- Dependency per FastAPI ---


async def get_current_tenant(request: Request):
    """
    FastAPI dependency per ottenere tenant corrente.

    Uso:
        @app.get("/items")
        async def list_items(tenant: TenantConfig = Depends(get_current_tenant)):
            ...
    """
    from me4brain.core.tenant.context import get_tenant_config

    config = get_tenant_config()
    if not config:
        from fastapi import HTTPException

        raise HTTPException(401, "Tenant not set")

    return config


async def require_feature(feature: str):
    """
    Factory per dependency che richiede feature.

    Uso:
        @app.post("/browser/sessions")
        async def create_session(
            _: None = Depends(require_feature("browser_automation"))
        ):
            ...
    """

    async def _check(request: Request):
        from fastapi import HTTPException

        from me4brain.core.tenant.context import get_tenant_config

        config = get_tenant_config()
        if not config:
            raise HTTPException(401, "Tenant not set")

        if not getattr(config.features, feature, False):
            raise HTTPException(
                403,
                f"Feature '{feature}' not enabled for tenant",
            )

    return _check
