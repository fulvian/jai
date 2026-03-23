"""
API Key management module.

Provides secure API key generation, validation, and revocation.
Keys are stored as hashed values for security.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import structlog

logger = structlog.get_logger(__name__)


class APIKeyScope(str, Enum):
    """Scopes for API keys."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass
class APIKey:
    """API Key model.

    Represents an API key with associated metadata.
    Note: The actual key value is only returned once at creation time.
    """

    id: str
    user_id: str
    name: str
    key_hash: str  # SHA-256 hash of the key
    key_prefix: str  # First 8 chars for identification
    scopes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    is_active: bool = True
    rate_limit: int = 60  # requests per minute
    metadata: dict = field(default_factory=dict)

    def is_expired(self) -> bool:
        """Check if the API key has expired.

        Returns:
            True if expired, False otherwise
        """
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_valid(self) -> bool:
        """Check if the API key is valid.

        Returns:
            True if valid (active and not expired)
        """
        return self.is_active and not self.is_expired()

    def has_scope(self, scope: str) -> bool:
        """Check if the key has a specific scope.

        Args:
            scope: The scope to check

        Returns:
            True if the key has the scope
        """
        return scope in self.scopes or APIKeyScope.ADMIN.value in self.scopes

    def to_dict(self) -> dict:
        """Convert to dictionary (excluding sensitive data).

        Returns:
            API key data as dictionary
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "key_prefix": f"{self.key_prefix}...",
            "scopes": self.scopes,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_active": self.is_active,
            "rate_limit": self.rate_limit,
        }


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns a tuple of (raw_key, key_hash, key_prefix).
    The raw key should be shown to the user only once.

    Returns:
        Tuple of (raw_key, key_hash, key_prefix)
    """
    raw_key = f"mk_{secrets.token_urlsafe(32)}"
    key_hash = hash_api_key(raw_key)
    key_prefix = raw_key[:8]
    return raw_key, key_hash, key_prefix


def hash_api_key(key: str) -> str:
    """Hash an API key using SHA-256.

    Args:
        key: The raw API key

    Returns:
        Hexadecimal hash of the key
    """
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Verify an API key against its hash.

    Args:
        raw_key: The raw API key to verify
        stored_hash: The stored hash to compare against

    Returns:
        True if the key matches the hash
    """
    computed_hash = hash_api_key(raw_key)
    return secrets.compare_digest(computed_hash, stored_hash)


class APIKeyManager:
    """Manages API keys for users.

    Provides CRUD operations for API keys with secure storage.
    """

    def __init__(self):
        # In-memory storage for demonstration
        # In production, this would use a database
        self._keys: dict[str, APIKey] = {}
        self._keys_by_hash: dict[str, str] = {}  # hash -> key_id
        self._keys_by_user: dict[str, list[str]] = {}  # user_id -> [key_ids]

    async def create_key(
        self,
        user_id: str,
        name: str,
        scopes: list[str] | None = None,
        expires_at: datetime | None = None,
        rate_limit: int = 60,
    ) -> tuple[APIKey, str]:
        """Create a new API key for a user.

        Args:
            user_id: The user ID to create the key for
            name: Human-readable name for the key
            scopes: List of scopes for the key
            expires_at: Optional expiration datetime
            rate_limit: Requests per minute limit

        Returns:
            Tuple of (APIKey object, raw_key)
            The raw_key should be shown to the user only once
        """
        import uuid

        key_id = f"key_{uuid.uuid4().hex[:16]}"
        raw_key, key_hash, key_prefix = generate_api_key()

        api_key = APIKey(
            id=key_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes or [APIKeyScope.READ.value],
            expires_at=expires_at,
            rate_limit=rate_limit,
        )

        # Store
        self._keys[key_id] = api_key
        self._keys_by_hash[key_hash] = key_id
        if user_id not in self._keys_by_user:
            self._keys_by_user[user_id] = []
        self._keys_by_user[user_id].append(key_id)

        logger.info(
            "api_key_created",
            key_id=key_id,
            user_id=user_id,
            name=name,
            expires_at=expires_at.isoformat() if expires_at else None,
        )

        return api_key, raw_key

    async def get_key(self, key_id: str) -> APIKey | None:
        """Get an API key by ID.

        Args:
            key_id: The API key ID

        Returns:
            APIKey if found, None otherwise
        """
        return self._keys.get(key_id)

    async def get_key_by_hash(self, key_hash: str) -> APIKey | None:
        """Get an API key by its hash.

        Args:
            key_hash: The hashed API key

        Returns:
            APIKey if found, None otherwise
        """
        key_id = self._keys_by_hash.get(key_hash)
        if key_id:
            return self._keys.get(key_id)
        return None

    async def get_user_keys(self, user_id: str) -> list[APIKey]:
        """Get all API keys for a user.

        Args:
            user_id: The user ID

        Returns:
            List of APIKey objects
        """
        key_ids = self._keys_by_user.get(user_id, [])
        return [self._keys[kid] for kid in key_ids if kid in self._keys]

    async def validate_key(self, raw_key: str) -> APIKey | None:
        """Validate an API key and return the associated APIKey object.

        Args:
            raw_key: The raw API key to validate

        Returns:
            APIKey if valid, None if invalid
        """
        key_hash = hash_api_key(raw_key)
        api_key = await self.get_key_by_hash(key_hash)

        if api_key is None:
            logger.warning("api_key_not_found", key_prefix=raw_key[:8])
            return None

        if not api_key.is_valid():
            logger.warning("api_key_invalid", key_id=api_key.id, reason="expired or inactive")
            return None

        # Update last used
        api_key.last_used_at = datetime.utcnow()

        logger.debug("api_key_validated", key_id=api_key.id, user_id=api_key.user_id)
        return api_key

    async def revoke_key(self, key_id: str) -> bool:
        """Revoke (deactivate) an API key.

        Args:
            key_id: The API key ID to revoke

        Returns:
            True if revoked, False if not found
        """
        api_key = self._keys.get(key_id)
        if api_key is None:
            return False

        api_key.is_active = False
        logger.info("api_key_revoked", key_id=key_id, user_id=api_key.user_id)
        return True

    async def delete_key(self, key_id: str) -> bool:
        """Permanently delete an API key.

        Args:
            key_id: The API key ID to delete

        Returns:
            True if deleted, False if not found
        """
        api_key = self._keys.get(key_id)
        if api_key is None:
            return False

        # Remove from all indexes
        del self._keys[key_id]
        del self._keys_by_hash[api_key.key_hash]
        if api_key.user_id in self._keys_by_user:
            self._keys_by_user[api_key.user_id].remove(key_id)

        logger.info("api_key_deleted", key_id=key_id, user_id=api_key.user_id)
        return True

    async def cleanup_expired_keys(self) -> int:
        """Remove expired keys from storage.

        Returns:
            Number of keys removed
        """
        expired_ids = [kid for kid, key in self._keys.items() if key.is_expired()]
        for kid in expired_ids:
            await self.delete_key(kid)

        if expired_ids:
            logger.info("expired_keys_cleaned", count=len(expired_ids))
        return len(expired_ids)


# Singleton instance
_api_key_manager: APIKeyManager | None = None


def get_api_key_manager() -> APIKeyManager:
    """Get the global API key manager instance.

    Returns:
        The global API key manager
    """
    global _api_key_manager
    if _api_key_manager is None:
        _api_key_manager = APIKeyManager()
    return _api_key_manager
