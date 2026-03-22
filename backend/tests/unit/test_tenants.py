"""Unit tests for Tenant module (M9)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import pytest

from me4brain.core.tenant.types import (
    TenantConfig,
    TenantFeatures,
    TenantInfo,
    TenantLimits,
    TenantQuota,
    TenantStatus,
    TenantTier,
    TenantUsage,
)
from me4brain.core.tenant.context import (
    TenantNotSetError,
    TenantAccessDeniedError,
    get_tenant_id,
    get_tenant_id_or_none,
    get_tenant_config,
    set_tenant,
    reset_tenant,
    tenant_context,
    validate_tenant_access,
    resolve_tenant_id,
)
from me4brain.core.tenant.store import TenantStore
from me4brain.core.tenant.quota import QuotaManager, QuotaExceededError


# --- Types Tests ---


class TestTenantTypes:
    """Test per modelli Pydantic tenant."""

    def test_tenant_tier_enum(self):
        """Test enum tier."""
        assert TenantTier.FREE.value == "free"
        assert TenantTier.PRO.value == "pro"
        assert TenantTier.ENTERPRISE.value == "enterprise"

    def test_tenant_status_enum(self):
        """Test enum status."""
        assert TenantStatus.ACTIVE.value == "active"
        assert TenantStatus.SUSPENDED.value == "suspended"

    def test_tenant_limits_defaults(self):
        """Test limiti default."""
        limits = TenantLimits()
        assert limits.api_calls_per_day == 1000
        assert limits.llm_tokens_per_month == 100_000

    def test_tenant_limits_for_tier_free(self):
        """Test limiti per tier FREE."""
        limits = TenantLimits.for_tier(TenantTier.FREE)
        assert limits.api_calls_per_day == 500
        assert limits.max_users == 1

    def test_tenant_limits_for_tier_pro(self):
        """Test limiti per tier PRO."""
        limits = TenantLimits.for_tier(TenantTier.PRO)
        assert limits.api_calls_per_day == 10_000
        assert limits.max_browser_sessions == 5

    def test_tenant_limits_for_tier_enterprise(self):
        """Test limiti per tier ENTERPRISE."""
        limits = TenantLimits.for_tier(TenantTier.ENTERPRISE)
        assert limits.api_calls_per_day == 1_000_000
        assert limits.max_concurrent_sessions == 100

    def test_tenant_features_defaults(self):
        """Test features default."""
        features = TenantFeatures()
        assert features.episodic_memory is True
        assert features.browser_automation is False

    def test_tenant_features_for_tier_pro(self):
        """Test features PRO."""
        features = TenantFeatures.for_tier(TenantTier.PRO)
        assert features.browser_automation is True
        assert features.webhooks is True

    def test_tenant_config_create(self):
        """Test factory create."""
        config = TenantConfig.create(
            tenant_id="test-123",
            name="Test Tenant",
            tier=TenantTier.PRO,
        )
        assert config.id == "test-123"
        assert config.tier == TenantTier.PRO
        assert config.limits.api_calls_per_day == 10_000

    def test_tenant_info_from_config(self):
        """Test conversione a TenantInfo."""
        config = TenantConfig.create("t1", "Test", TenantTier.FREE)
        info = TenantInfo.from_config(config)
        assert info.id == "t1"
        assert info.tier == TenantTier.FREE

    def test_tenant_quota_is_exceeded(self):
        """Test quota exceeded."""
        quota = TenantQuota(
            tenant_id="t1",
            resource="api_calls",
            current=100,
            limit=100,
            remaining=0,
        )
        assert quota.is_exceeded is True

    def test_tenant_quota_usage_percent(self):
        """Test percentuale utilizzo."""
        quota = TenantQuota(
            tenant_id="t1",
            resource="api_calls",
            current=50,
            limit=100,
            remaining=50,
        )
        assert quota.usage_percent == 50.0


# --- Context Tests ---


class TestTenantContext:
    """Test per context management."""

    def test_get_tenant_id_not_set(self):
        """Test eccezione quando tenant non impostato."""
        with pytest.raises(TenantNotSetError):
            get_tenant_id()

    def test_get_tenant_id_or_none_empty(self):
        """Test None quando vuoto."""
        result = get_tenant_id_or_none()
        assert result is None

    def test_set_and_get_tenant(self):
        """Test set e get tenant."""
        token = set_tenant("tenant-abc")
        try:
            assert get_tenant_id() == "tenant-abc"
        finally:
            reset_tenant(token)

    def test_tenant_context_manager(self):
        """Test context manager."""
        with tenant_context("tenant-xyz"):
            assert get_tenant_id() == "tenant-xyz"

        # Dopo il context, deve essere vuoto
        assert get_tenant_id_or_none() is None

    def test_tenant_context_with_config(self):
        """Test context con config."""
        config = TenantConfig.create("t1", "Test", TenantTier.PRO)

        with tenant_context("t1", config=config):
            assert get_tenant_id() == "t1"
            assert get_tenant_config() == config

    def test_validate_tenant_access_success(self):
        """Test validazione accesso ok."""
        with tenant_context("tenant-a"):
            # Non dovrebbe sollevare eccezione
            validate_tenant_access("tenant-a")

    def test_validate_tenant_access_denied(self):
        """Test validazione accesso negato."""
        with tenant_context("tenant-a"):
            with pytest.raises(TenantAccessDeniedError):
                validate_tenant_access("tenant-b")

    def test_resolve_tenant_id_from_context(self):
        """Test risoluzione da context."""
        with tenant_context("ctx-tenant"):
            assert resolve_tenant_id() == "ctx-tenant"

    def test_resolve_tenant_id_explicit(self):
        """Test risoluzione esplicita."""
        with tenant_context("ctx-tenant"):
            # Esplicito ha precedenza
            assert resolve_tenant_id("explicit-tenant") == "explicit-tenant"


# --- Store Tests ---


class TestTenantStore:
    """Test per TenantStore."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        mock = AsyncMock()
        mock.exists.return_value = False
        mock.sadd.return_value = 1
        mock.sismember.return_value = True
        mock.smembers.return_value = {"t1", "t2"}
        mock.scard.return_value = 2
        return mock

    @pytest.fixture
    def store(self, mock_redis):
        """Store con mock Redis."""
        s = TenantStore(redis_client=mock_redis)
        return s

    @pytest.mark.asyncio
    async def test_create_tenant(self, store, mock_redis):
        """Test creazione tenant."""
        config = await store.create("Test Tenant", TenantTier.PRO)

        assert config.name == "Test Tenant"
        assert config.tier == TenantTier.PRO
        mock_redis.set.assert_called_once()
        mock_redis.sadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tenant_already_exists(self, store, mock_redis):
        """Test creazione tenant esistente."""
        mock_redis.exists.return_value = True

        with pytest.raises(ValueError):
            await store.create("Test", tenant_id="existing")

    @pytest.mark.asyncio
    async def test_get_tenant(self, store, mock_redis):
        """Test recupero tenant."""
        config = TenantConfig.create("t1", "Test", TenantTier.FREE)
        mock_redis.get.return_value = config.model_dump_json()

        result = await store.get("t1")

        assert result is not None
        assert result.id == "t1"

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(self, store, mock_redis):
        """Test tenant non trovato."""
        mock_redis.get.return_value = None

        result = await store.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_tenant(self, store, mock_redis):
        """Test aggiornamento tenant."""
        config = TenantConfig.create("t1", "Test", TenantTier.FREE)
        mock_redis.get.return_value = config.model_dump_json()

        result = await store.update("t1", name="Updated Name")

        assert result.name == "Updated Name"
        mock_redis.set.assert_called()

    @pytest.mark.asyncio
    async def test_delete_tenant_soft(self, store, mock_redis):
        """Test soft delete."""
        config = TenantConfig.create("t1", "Test", TenantTier.FREE)
        mock_redis.get.return_value = config.model_dump_json()

        result = await store.delete("t1", soft=True)

        assert result is True
        # Soft delete aggiorna status, non elimina
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_tenant_hard(self, store, mock_redis):
        """Test hard delete."""
        mock_redis.delete.return_value = 1

        result = await store.delete("t1", soft=False)

        assert result is True
        mock_redis.delete.assert_called()
        mock_redis.srem.assert_called()

    @pytest.mark.asyncio
    async def test_exists(self, store, mock_redis):
        """Test exists."""
        mock_redis.sismember.return_value = True

        assert await store.exists("t1") is True

    @pytest.mark.asyncio
    async def test_count(self, store, mock_redis):
        """Test count."""
        mock_redis.scard.return_value = 5

        assert await store.count() == 5


# --- Quota Tests ---


class TestQuotaManager:
    """Test per QuotaManager."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        mock = AsyncMock()
        mock.get.return_value = "50"
        mock.incrby.return_value = 51
        mock.ttl.return_value = -1
        mock.mget.return_value = ["100", "5", "1000", "50", "500", "200", "3", "1"]
        return mock

    @pytest.fixture
    def manager(self, mock_redis):
        """Manager con mock Redis."""
        return QuotaManager(redis_client=mock_redis)

    @pytest.mark.asyncio
    async def test_check_quota(self, manager):
        """Test check quota."""
        with patch.object(manager, "_get_limit", return_value=100):
            quota = await manager.check("t1", "api_calls_day")

        assert quota.current == 50
        assert quota.limit == 100
        assert quota.remaining == 50

    @pytest.mark.asyncio
    async def test_check_and_increment_allowed(self, manager, mock_redis):
        """Test incremento permesso."""
        mock_redis.incrby.return_value = 51

        with patch.object(manager, "_get_limit", return_value=100):
            allowed, current, limit = await manager.check_and_increment(
                "t1", "api_calls_day"
            )

        assert allowed is True
        assert current == 51

    @pytest.mark.asyncio
    async def test_check_and_increment_exceeded(self, manager, mock_redis):
        """Test incremento negato (quota superata)."""
        mock_redis.incrby.return_value = 101

        with patch.object(manager, "_get_limit", return_value=100):
            allowed, current, limit = await manager.check_and_increment(
                "t1", "api_calls_day"
            )

        assert allowed is False
        # Rollback
        mock_redis.decrby.assert_called()

    @pytest.mark.asyncio
    async def test_increment(self, manager, mock_redis):
        """Test incremento senza check."""
        mock_redis.incrby.return_value = 60

        result = await manager.increment("t1", "storage_mb", 10)

        assert result == 60

    @pytest.mark.asyncio
    async def test_decrement(self, manager, mock_redis):
        """Test decremento."""
        mock_redis.decrby.return_value = 40

        result = await manager.decrement("t1", "storage_mb", 10)

        assert result == 40

    @pytest.mark.asyncio
    async def test_reset(self, manager, mock_redis):
        """Test reset."""
        await manager.reset("t1", "api_calls_day")

        mock_redis.delete.assert_called()

    @pytest.mark.asyncio
    async def test_get_usage(self, manager, mock_redis):
        """Test get usage completo."""
        usage = await manager.get_usage("t1")

        assert usage.tenant_id == "t1"
        assert usage.api_calls_today == 100
        assert usage.llm_tokens_this_month == 1000

    def test_get_ttl_day(self, manager):
        """Test TTL giornaliero."""
        ttl = manager._get_ttl("api_calls_day")
        assert ttl == 86400

    def test_get_ttl_minute(self, manager):
        """Test TTL minuto."""
        ttl = manager._get_ttl("api_calls_minute")
        assert ttl == 60

    def test_get_ttl_storage(self, manager):
        """Test no TTL per storage."""
        ttl = manager._get_ttl("storage_mb")
        assert ttl is None
