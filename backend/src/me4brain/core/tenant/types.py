"""Multi-tenant Types - Modelli Pydantic per tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TenantTier(str, Enum):
    """Tier del tenant (pricing/features)."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TenantStatus(str, Enum):
    """Stato del tenant."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"
    PENDING = "pending"


class TenantLimits(BaseModel):
    """Limiti risorse per tenant."""

    # API
    api_calls_per_day: int = 1000
    api_calls_per_minute: int = 60

    # LLM
    llm_tokens_per_month: int = 100_000
    llm_max_context_tokens: int = 8192

    # Storage
    storage_mb: int = 100
    max_episodes: int = 10_000
    max_entities: int = 5_000

    # Sessions
    max_concurrent_sessions: int = 10
    max_users: int = 5

    # Browser
    max_browser_sessions: int = 2

    @classmethod
    def for_tier(cls, tier: TenantTier) -> TenantLimits:
        """Limiti predefiniti per tier."""
        defaults = {
            TenantTier.FREE: cls(
                api_calls_per_day=500,
                llm_tokens_per_month=50_000,
                storage_mb=50,
                max_users=1,
            ),
            TenantTier.PRO: cls(
                api_calls_per_day=10_000,
                llm_tokens_per_month=1_000_000,
                storage_mb=1024,
                max_users=10,
                max_browser_sessions=5,
            ),
            TenantTier.ENTERPRISE: cls(
                api_calls_per_day=1_000_000,
                llm_tokens_per_month=100_000_000,
                storage_mb=10240,
                max_users=1000,
                max_concurrent_sessions=100,
                max_browser_sessions=50,
            ),
        }
        return defaults.get(tier, cls())


class TenantFeatures(BaseModel):
    """Feature flags per tenant."""

    # Core
    episodic_memory: bool = True
    semantic_memory: bool = True
    procedural_memory: bool = True

    # Advanced
    browser_automation: bool = False
    custom_tools: bool = False
    webhooks: bool = False
    multi_agent: bool = False

    # Enterprise
    sso: bool = False
    audit_logs: bool = False
    dedicated_resources: bool = False

    @classmethod
    def for_tier(cls, tier: TenantTier) -> TenantFeatures:
        """Features predefinite per tier."""
        defaults = {
            TenantTier.FREE: cls(),
            TenantTier.PRO: cls(
                browser_automation=True,
                custom_tools=True,
                webhooks=True,
            ),
            TenantTier.ENTERPRISE: cls(
                browser_automation=True,
                custom_tools=True,
                webhooks=True,
                multi_agent=True,
                sso=True,
                audit_logs=True,
                dedicated_resources=True,
            ),
        }
        return defaults.get(tier, cls())


class TenantConfig(BaseModel):
    """Configurazione completa di un tenant."""

    id: str
    name: str
    tier: TenantTier = TenantTier.FREE
    status: TenantStatus = TenantStatus.ACTIVE
    limits: TenantLimits = Field(default_factory=TenantLimits)
    features: TenantFeatures = Field(default_factory=TenantFeatures)

    # Metadata
    owner_email: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        tenant_id: str,
        name: str,
        tier: TenantTier = TenantTier.FREE,
        owner_email: str | None = None,
    ) -> TenantConfig:
        """Factory per creare tenant con defaults per tier."""
        return cls(
            id=tenant_id,
            name=name,
            tier=tier,
            limits=TenantLimits.for_tier(tier),
            features=TenantFeatures.for_tier(tier),
            owner_email=owner_email,
        )


class TenantInfo(BaseModel):
    """Info pubbliche tenant (API response)."""

    id: str
    name: str
    tier: TenantTier
    status: TenantStatus
    created_at: datetime

    @classmethod
    def from_config(cls, config: TenantConfig) -> TenantInfo:
        """Crea da config completa."""
        return cls(
            id=config.id,
            name=config.name,
            tier=config.tier,
            status=config.status,
            created_at=config.created_at,
        )


class TenantUsage(BaseModel):
    """Usage corrente del tenant."""

    tenant_id: str

    # API
    api_calls_today: int = 0
    api_calls_this_minute: int = 0

    # LLM
    llm_tokens_this_month: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0

    # Storage
    storage_used_mb: float = 0.0
    episodes_count: int = 0
    entities_count: int = 0

    # Sessions
    active_sessions: int = 0
    active_browser_sessions: int = 0

    # Cost tracking
    estimated_cost_usd: float = 0.0

    # Timestamps
    last_activity: datetime | None = None
    period_start: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TenantQuota(BaseModel):
    """Stato quota tenant (per enforcement)."""

    tenant_id: str
    resource: str  # "api_calls", "llm_tokens", "storage"
    current: int
    limit: int
    remaining: int
    reset_at: datetime | None = None

    @property
    def is_exceeded(self) -> bool:
        """True se quota superata."""
        return self.current >= self.limit

    @property
    def usage_percent(self) -> float:
        """Percentuale utilizzo."""
        if self.limit == 0:
            return 100.0
        return (self.current / self.limit) * 100


# --- API Response Models ---


class TenantCreateRequest(BaseModel):
    """Request per creare tenant."""

    name: str
    tier: TenantTier = TenantTier.FREE
    owner_email: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TenantUpdateRequest(BaseModel):
    """Request per aggiornare tenant."""

    name: str | None = None
    tier: TenantTier | None = None
    status: TenantStatus | None = None
    limits: TenantLimits | None = None
    features: TenantFeatures | None = None
    metadata: dict[str, Any] | None = None


class TenantListResponse(BaseModel):
    """Response lista tenants."""

    total: int
    tenants: list[TenantInfo]


class TenantUsageResponse(BaseModel):
    """Response usage tenant."""

    usage: TenantUsage
    quotas: list[TenantQuota]
