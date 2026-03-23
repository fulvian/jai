"""Multi-tenant Isolation - Package init."""

from me4brain.core.tenant.context import (
    TenantNotSetError,
    get_tenant_config,
    get_tenant_id,
    set_tenant,
    tenant_context,
)
from me4brain.core.tenant.quota import QuotaManager
from me4brain.core.tenant.store import TenantStore
from me4brain.core.tenant.types import (
    TenantConfig,
    TenantInfo,
    TenantLimits,
    TenantQuota,
    TenantTier,
    TenantUsage,
)

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
