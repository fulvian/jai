"""Multi-tenant Isolation - Package init."""

from me4brain.core.tenant.types import (
    TenantConfig,
    TenantInfo,
    TenantLimits,
    TenantQuota,
    TenantTier,
    TenantUsage,
)
from me4brain.core.tenant.context import (
    get_tenant_id,
    get_tenant_config,
    set_tenant,
    tenant_context,
    TenantNotSetError,
)
from me4brain.core.tenant.store import TenantStore
from me4brain.core.tenant.quota import QuotaManager

__all__ = [
    # Types
    "TenantConfig",
    "TenantInfo",
    "TenantLimits",
    "TenantQuota",
    "TenantTier",
    "TenantUsage",
    # Context
    "get_tenant_id",
    "get_tenant_config",
    "set_tenant",
    "tenant_context",
    "TenantNotSetError",
    # Store & Quota
    "TenantStore",
    "QuotaManager",
]
