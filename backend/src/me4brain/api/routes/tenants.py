"""Tenant API Routes - Endpoints per gestione tenant."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from me4brain.core.tenant.context import get_tenant_config, get_tenant_id
from me4brain.core.tenant.quota import QuotaManager, get_quota_manager
from me4brain.core.tenant.store import TenantStore, get_tenant_store
from me4brain.core.tenant.types import (
    TenantConfig,
    TenantCreateRequest,
    TenantInfo,
    TenantListResponse,
    TenantStatus,
    TenantTier,
    TenantUpdateRequest,
    TenantUsageResponse,
)

router = APIRouter(tags=["tenants"])


# --- Admin Routes (require admin auth) ---


@router.post("/v1/admin/tenants", response_model=TenantInfo)
async def create_tenant(
    request: TenantCreateRequest,
    store: TenantStore = Depends(get_tenant_store),
):
    """
    Crea nuovo tenant (admin only).

    Returns:
        Info del tenant creato
    """
    try:
        config = await store.create(
            name=request.name,
            tier=request.tier,
            owner_email=request.owner_email,
        )
        return TenantInfo.from_config(config)

    except ValueError as e:
        raise HTTPException(409, str(e))


@router.get("/v1/admin/tenants", response_model=TenantListResponse)
async def list_tenants(
    status: TenantStatus | None = None,
    tier: TenantTier | None = None,
    store: TenantStore = Depends(get_tenant_store),
):
    """
    Lista tutti i tenant (admin only).

    Args:
        status: Filtra per status
        tier: Filtra per tier
    """
    tenants = await store.list_all(status=status, tier=tier)

    return TenantListResponse(
        total=len(tenants),
        tenants=[TenantInfo.from_config(t) for t in tenants],
    )


@router.get("/v1/admin/tenants/{tenant_id}", response_model=TenantConfig)
async def get_tenant(
    tenant_id: str,
    store: TenantStore = Depends(get_tenant_store),
):
    """
    Dettaglio tenant (admin only).

    Returns:
        Config completa del tenant
    """
    config = await store.get(tenant_id)
    if not config:
        raise HTTPException(404, "Tenant not found")

    return config


@router.put("/v1/admin/tenants/{tenant_id}", response_model=TenantConfig)
async def update_tenant(
    tenant_id: str,
    request: TenantUpdateRequest,
    store: TenantStore = Depends(get_tenant_store),
):
    """
    Aggiorna tenant (admin only).
    """
    config = await store.update(
        tenant_id,
        name=request.name,
        tier=request.tier,
        status=request.status,
        limits=request.limits,
        features=request.features,
    )

    if not config:
        raise HTTPException(404, "Tenant not found")

    return config


@router.delete("/v1/admin/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    hard: bool = False,
    store: TenantStore = Depends(get_tenant_store),
):
    """
    Elimina tenant (admin only).

    Args:
        hard: Se True, elimina definitivamente
    """
    success = await store.delete(tenant_id, soft=not hard)

    if not success:
        raise HTTPException(404, "Tenant not found")

    return {"deleted": True, "tenant_id": tenant_id, "hard": hard}


# --- Self Routes (per tenant corrente) ---


@router.get("/v1/tenant/info", response_model=TenantInfo)
async def get_current_tenant_info():
    """
    Info del tenant corrente.

    Richiede X-Tenant-ID header.
    """
    config = get_tenant_config()
    if not config:
        raise HTTPException(401, "Tenant not set")

    return TenantInfo.from_config(config)


@router.get("/v1/tenant/usage", response_model=TenantUsageResponse)
async def get_current_tenant_usage(
    quota_manager: QuotaManager = Depends(get_quota_manager),
):
    """
    Usage corrente del tenant.

    Returns:
        Usage e quotas
    """
    tenant_id = get_tenant_id()

    usage = await quota_manager.get_usage(tenant_id)
    quotas = await quota_manager.get_all_quotas(tenant_id)

    return TenantUsageResponse(usage=usage, quotas=quotas)


@router.post("/v1/tenant/usage/reset")
async def reset_tenant_usage(
    resource: str | None = None,
    quota_manager: QuotaManager = Depends(get_quota_manager),
):
    """
    Reset usage counters (solo per testing/admin).

    Args:
        resource: Risorsa specifica da resettare (opzionale)
    """
    tenant_id = get_tenant_id()

    if resource:
        await quota_manager.reset(tenant_id, resource)
        return {"reset": resource}
    else:
        await quota_manager.reset_all(tenant_id)
        return {"reset": "all"}
