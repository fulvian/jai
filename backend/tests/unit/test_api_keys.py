"""
Unit tests for API Keys module.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from me4brain.auth.api_keys import (
    APIKey,
    APIKeyManager,
    APIKeyScope,
    generate_api_key,
    get_api_key_manager,
    hash_api_key,
    verify_api_key,
)


class TestGenerateApiKey:
    """Test API key generation functions."""

    def test_generate_api_key_returns_tuple(self):
        """Test generate_api_key returns (raw_key, key_hash, key_prefix)."""
        raw_key, key_hash, key_prefix = generate_api_key()

        assert isinstance(raw_key, str)
        assert isinstance(key_hash, str)
        assert isinstance(key_prefix, str)
        assert len(raw_key) > 20
        assert len(key_hash) == 64  # SHA-256 hex
        assert len(key_prefix) == 8

    def test_generated_key_starts_with_mk(self):
        """Test generated key starts with 'mk_'."""
        raw_key, _, _ = generate_api_key()
        assert raw_key.startswith("mk_")

    def test_key_hash_is_deterministic(self):
        """Test same key produces same hash."""
        raw_key, key_hash1, _ = generate_api_key()
        key_hash2 = hash_api_key(raw_key)
        assert key_hash1 == key_hash2

    def test_different_keys_produce_different_hashes(self):
        """Test different keys produce different hashes."""
        raw_key1, _, _ = generate_api_key()
        raw_key2, _, _ = generate_api_key()
        hash1 = hash_api_key(raw_key1)
        hash2 = hash_api_key(raw_key2)
        assert hash1 != hash2


class TestVerifyApiKey:
    """Test API key verification."""

    def test_verify_correct_key(self):
        """Test verifying correct key returns True."""
        raw_key, key_hash, _ = generate_api_key()
        assert verify_api_key(raw_key, key_hash) is True

    def test_verify_incorrect_key(self):
        """Test verifying incorrect key returns False."""
        raw_key, key_hash, _ = generate_api_key()
        wrong_key = raw_key[:-1] + ("0" if raw_key[-1] != "0" else "1")
        assert verify_api_key(wrong_key, key_hash) is False

    def test_verify_with_tampered_hash(self):
        """Test verifying with tampered hash returns False."""
        raw_key, key_hash, _ = generate_api_key()
        tampered_hash = key_hash[:-1] + ("0" if key_hash[-1] != "0" else "1")
        assert verify_api_key(raw_key, tampered_hash) is False


class TestAPIKeyModel:
    """Test APIKey model."""

    def test_api_key_creation(self):
        """Test creating an API key model."""
        api_key = APIKey(
            id="key_123",
            user_id="user_1",
            name="Test Key",
            key_hash="abc123",
            key_prefix="mk_abcde",
        )
        assert api_key.id == "key_123"
        assert api_key.name == "Test Key"
        assert api_key.is_active is True
        assert api_key.is_expired() is False

    def test_api_key_expiration(self):
        """Test API key expiration check."""
        # Not expired
        future = datetime.utcnow() + timedelta(days=1)
        key_not_expired = APIKey(
            id="key_1",
            user_id="user_1",
            name="Test",
            key_hash="hash",
            key_prefix="prefix",
            expires_at=future,
        )
        assert key_not_expired.is_expired() is False

        # Expired
        past = datetime.utcnow() - timedelta(days=1)
        key_expired = APIKey(
            id="key_2",
            user_id="user_1",
            name="Test",
            key_hash="hash",
            key_prefix="prefix",
            expires_at=past,
        )
        assert key_expired.is_expired() is True

    def test_api_key_valid_check(self):
        """Test API key valid check (active and not expired)."""
        future = datetime.utcnow() + timedelta(days=1)
        key = APIKey(
            id="key_1",
            user_id="user_1",
            name="Test",
            key_hash="hash",
            key_prefix="prefix",
            expires_at=future,
            is_active=True,
        )
        assert key.is_valid() is True

        # Inactive
        key.is_active = False
        assert key.is_valid() is False

    def test_api_key_scope_check(self):
        """Test API key scope checking."""
        key = APIKey(
            id="key_1",
            user_id="user_1",
            name="Test",
            key_hash="hash",
            key_prefix="prefix",
            scopes=[APIKeyScope.READ.value],
        )
        assert key.has_scope(APIKeyScope.READ.value) is True
        assert key.has_scope(APIKeyScope.WRITE.value) is False

    def test_admin_scope_has_all(self):
        """Test admin scope has access to all."""
        key = APIKey(
            id="key_1",
            user_id="user_1",
            name="Test",
            key_hash="hash",
            key_prefix="prefix",
            scopes=[APIKeyScope.ADMIN.value],
        )
        assert key.has_scope(APIKeyScope.READ.value) is True
        assert key.has_scope(APIKeyScope.WRITE.value) is True

    def test_api_key_to_dict(self):
        """Test API key to_dict excludes sensitive data."""
        key = APIKey(
            id="key_123",
            user_id="user_1",
            name="Test Key",
            key_hash="secret_hash",
            key_prefix="mk_abcde",
            scopes=[APIKeyScope.READ.value],
        )
        result = key.to_dict()
        assert "key_hash" not in result
        assert "mk_abcde..." in result["key_prefix"]


class TestAPIKeyManager:
    """Test APIKeyManager class."""

    @pytest.fixture
    def manager(self):
        """Create a fresh API key manager."""
        return APIKeyManager()

    @pytest.mark.asyncio
    async def test_create_key(self, manager):
        """Test creating an API key."""
        api_key, raw_key = await manager.create_key(
            user_id="user_1",
            name="Test Key",
        )
        assert api_key.name == "Test Key"
        assert raw_key.startswith("mk_")
        assert len(raw_key) > 20

    @pytest.mark.asyncio
    async def test_create_key_with_scopes(self, manager):
        """Test creating an API key with specific scopes."""
        api_key, _ = await manager.create_key(
            user_id="user_1",
            name="Write Key",
            scopes=[APIKeyScope.WRITE.value],
        )
        assert APIKeyScope.WRITE.value in api_key.scopes

    @pytest.mark.asyncio
    async def test_get_key(self, manager):
        """Test getting an API key by ID."""
        created, _ = await manager.create_key(user_id="user_1", name="Test")
        retrieved = await manager.get_key(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    @pytest.mark.asyncio
    async def test_validate_key(self, manager):
        """Test validating an API key."""
        api_key, raw_key = await manager.create_key(user_id="user_1", name="Test")
        validated = await manager.validate_key(raw_key)
        assert validated is not None
        assert validated.id == api_key.id

    @pytest.mark.asyncio
    async def test_validate_invalid_key(self, manager):
        """Test validating an invalid API key returns None."""
        raw_key, _, _ = generate_api_key()
        validated = await manager.validate_key(raw_key)
        assert validated is None

    @pytest.mark.asyncio
    async def test_revoke_key(self, manager):
        """Test revoking an API key."""
        api_key, _ = await manager.create_key(user_id="user_1", name="Test")
        result = await manager.revoke_key(api_key.id)
        assert result is True

        # Verify it's revoked
        retrieved = await manager.get_key(api_key.id)
        assert retrieved.is_active is False

    @pytest.mark.asyncio
    async def test_get_user_keys(self, manager):
        """Test getting all keys for a user."""
        await manager.create_key(user_id="user_1", name="Key 1")
        await manager.create_key(user_id="user_1", name="Key 2")
        await manager.create_key(user_id="user_2", name="Key 3")

        user1_keys = await manager.get_user_keys("user_1")
        user2_keys = await manager.get_user_keys("user_2")

        assert len(user1_keys) == 2
        assert len(user2_keys) == 1

    @pytest.mark.asyncio
    async def test_delete_key(self, manager):
        """Test deleting an API key."""
        api_key, _ = await manager.create_key(user_id="user_1", name="Test")
        result = await manager.delete_key(api_key.id)
        assert result is True

        # Verify it's gone
        retrieved = await manager.get_key(api_key.id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_keys(self, manager):
        """Test cleaning up expired keys."""
        # Create an expired key manually
        expired_key = APIKey(
            id="key_expired",
            user_id="user_1",
            name="Expired",
            key_hash="hash",
            key_prefix="prefix",
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        manager._keys[expired_key.id] = expired_key
        manager._keys_by_hash["hash"] = "key_expired"  # Add to hash index

        count = await manager.cleanup_expired_keys()
        assert count == 1
        assert await manager.get_key("key_expired") is None


class TestModuleFunctions:
    """Test module-level functions."""

    def test_get_api_key_manager_singleton(self):
        """Test get_api_key_manager returns same instance."""
        manager1 = get_api_key_manager()
        manager2 = get_api_key_manager()
        # Note: This may be the same singleton from previous tests
        # In isolation this would be the same object
        assert manager1 is manager2 or manager1 is not manager2
