"""Secrets Manager.

Multi-backend secrets management with intelligent fallback:
1. Doppler (cross-platform, team sync, production)
2. macOS Keychain via keyring (local dev on Mac)
3. Environment variables (universal fallback)

Usage:
    manager = get_secrets_manager()
    api_key = await manager.get_secret("OPENAI_API_KEY")

    # Or with specific backend
    api_key = await manager.get_secret("OPENAI_API_KEY", backend="doppler")
"""

import asyncio
import os
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SecretBackend(str, Enum):
    """Available secret backends."""

    DOPPLER = "doppler"
    KEYCHAIN = "keychain"
    ENV = "env"


@dataclass
class SecretValue:
    """Wrapper for secret with metadata."""

    value: str
    backend: SecretBackend
    cached: bool = False


class SecretsManager:
    """Multi-backend secrets manager with cascade lookup."""

    # Backend order for cascade lookup
    DEFAULT_BACKENDS = [
        SecretBackend.DOPPLER,
        SecretBackend.KEYCHAIN,
        SecretBackend.ENV,
    ]

    def __init__(
        self,
        backends: list[SecretBackend] | None = None,
        doppler_project: str | None = None,
        doppler_config: str = "dev",
        keychain_service: str = "me4brain",
    ):
        """Initialize secrets manager.

        Args:
            backends: List of backends to use (in order of preference)
            doppler_project: Doppler project name (uses DOPPLER_PROJECT if not set)
            doppler_config: Doppler config name (dev, staging, prod)
            keychain_service: Service name for keychain entries
        """
        self.backends = backends or self.DEFAULT_BACKENDS
        self.doppler_project = doppler_project or os.getenv("DOPPLER_PROJECT")
        self.doppler_config = doppler_config
        self.keychain_service = keychain_service

        # Cache for secrets (in-memory)
        self._cache: dict[str, SecretValue] = {}

        # Check which backends are available
        self._available_backends = self._detect_available_backends()

        logger.info(
            "secrets_manager_initialized",
            available_backends=[b.value for b in self._available_backends],
            doppler_configured=SecretBackend.DOPPLER in self._available_backends,
        )

    def _detect_available_backends(self) -> list[SecretBackend]:
        """Detect which backends are available on this system."""
        available = []

        # Check Doppler
        if self._is_doppler_available():
            available.append(SecretBackend.DOPPLER)

        # Check Keychain (macOS only)
        if platform.system() == "Darwin" and self._is_keyring_available():
            available.append(SecretBackend.KEYCHAIN)

        # Env is always available
        available.append(SecretBackend.ENV)

        return available

    def _is_doppler_available(self) -> bool:
        """Check if Doppler CLI is installed and configured."""
        try:
            result = subprocess.run(
                ["doppler", "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _is_keyring_available(self) -> bool:
        """Check if keyring library is available."""
        try:
            import keyring

            return True
        except ImportError:
            return False

    async def get_secret(
        self,
        key: str,
        backend: SecretBackend | None = None,
        use_cache: bool = True,
    ) -> str | None:
        """Get a secret value.

        Args:
            key: Secret key name
            backend: Specific backend to use (None = cascade lookup)
            use_cache: Whether to use cached values

        Returns:
            Secret value or None if not found
        """
        # Check cache first
        if use_cache and key in self._cache:
            cached = self._cache[key]
            logger.debug("secret_cache_hit", key=key, backend=cached.backend.value)
            return cached.value

        # Try specific backend if requested
        if backend:
            if backend not in self._available_backends:
                logger.warning(
                    "secret_backend_unavailable",
                    key=key,
                    requested_backend=backend.value,
                )
                return None

            value = await self._get_from_backend(backend, key)
            if value:
                self._cache[key] = SecretValue(value, backend, cached=True)
            return value

        # Cascade lookup through available backends
        for b in self.backends:
            if b not in self._available_backends:
                continue

            value = await self._get_from_backend(b, key)
            if value:
                logger.debug(
                    "secret_found",
                    key=key,
                    backend=b.value,
                )
                self._cache[key] = SecretValue(value, b, cached=True)
                return value

        logger.warning("secret_not_found", key=key)
        return None

    async def _get_from_backend(
        self,
        backend: SecretBackend,
        key: str,
    ) -> str | None:
        """Get secret from specific backend.

        Args:
            backend: Backend to query
            key: Secret key

        Returns:
            Secret value or None
        """
        if backend == SecretBackend.DOPPLER:
            return await self._doppler_get(key)
        elif backend == SecretBackend.KEYCHAIN:
            return self._keychain_get(key)
        elif backend == SecretBackend.ENV:
            return os.getenv(key)

        return None

    async def _doppler_get(self, key: str) -> str | None:
        """Get secret from Doppler.

        Args:
            key: Secret key

        Returns:
            Secret value or None
        """
        try:
            cmd = ["doppler", "secrets", "get", key, "--plain"]

            if self.doppler_project:
                cmd.extend(["--project", self.doppler_project])
            if self.doppler_config:
                cmd.extend(["--config", self.doppler_config])

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=10,
                ),
            )

            if result.returncode == 0:
                return result.stdout.strip()

            return None

        except Exception as e:
            logger.debug(
                "doppler_get_failed",
                key=key,
                error=str(e),
            )
            return None

    def _keychain_get(self, key: str) -> str | None:
        """Get secret from macOS Keychain via keyring.

        Args:
            key: Secret key

        Returns:
            Secret value or None
        """
        try:
            import keyring

            value = keyring.get_password(self.keychain_service, key)
            return value

        except Exception as e:
            logger.debug(
                "keychain_get_failed",
                key=key,
                error=str(e),
            )
            return None

    async def set_secret(
        self,
        key: str,
        value: str,
        backend: SecretBackend = SecretBackend.KEYCHAIN,
    ) -> bool:
        """Set a secret value.

        Note: Only Keychain and local ENV are writable.
        Doppler requires using their CLI or dashboard.

        Args:
            key: Secret key
            value: Secret value
            backend: Backend to store in

        Returns:
            True if successful
        """
        if backend == SecretBackend.KEYCHAIN:
            return self._keychain_set(key, value)
        elif backend == SecretBackend.ENV:
            os.environ[key] = value
            self._cache[key] = SecretValue(value, backend)
            return True

        logger.warning(
            "secret_set_not_supported",
            backend=backend.value,
        )
        return False

    def _keychain_set(self, key: str, value: str) -> bool:
        """Set secret in macOS Keychain.

        Args:
            key: Secret key
            value: Secret value

        Returns:
            True if successful
        """
        try:
            import keyring

            keyring.set_password(self.keychain_service, key, value)
            self._cache[key] = SecretValue(value, SecretBackend.KEYCHAIN)

            logger.info("secret_stored_in_keychain", key=key)
            return True

        except Exception as e:
            logger.error(
                "keychain_set_failed",
                key=key,
                error=str(e),
            )
            return False

    async def delete_secret(
        self,
        key: str,
        backend: SecretBackend = SecretBackend.KEYCHAIN,
    ) -> bool:
        """Delete a secret.

        Args:
            key: Secret key
            backend: Backend to delete from

        Returns:
            True if successful
        """
        if backend == SecretBackend.KEYCHAIN:
            try:
                import keyring

                keyring.delete_password(self.keychain_service, key)
                self._cache.pop(key, None)

                logger.info("secret_deleted_from_keychain", key=key)
                return True

            except Exception as e:
                logger.error(
                    "keychain_delete_failed",
                    key=key,
                    error=str(e),
                )
                return False

        return False

    def clear_cache(self) -> None:
        """Clear the in-memory secret cache."""
        self._cache.clear()
        logger.info("secrets_cache_cleared")

    def get_stats(self) -> dict[str, Any]:
        """Get secrets manager statistics.

        Returns:
            Dictionary with stats
        """
        return {
            "available_backends": [b.value for b in self._available_backends],
            "configured_backends": [b.value for b in self.backends],
            "cached_secrets": len(self._cache),
            "doppler_project": self.doppler_project,
            "keychain_service": self.keychain_service,
        }


# Singleton instance
_secrets_manager: SecretsManager | None = None


def get_secrets_manager() -> SecretsManager:
    """Get or create the global SecretsManager instance.

    Returns:
        SecretsManager singleton
    """
    global _secrets_manager

    if _secrets_manager is None:
        _secrets_manager = SecretsManager()

    return _secrets_manager


def configure_secrets_manager(
    backends: list[SecretBackend] | None = None,
    doppler_project: str | None = None,
    doppler_config: str = "dev",
    keychain_service: str = "me4brain",
) -> SecretsManager:
    """Configure and get the global SecretsManager.

    Args:
        backends: List of backends to use
        doppler_project: Doppler project name
        doppler_config: Doppler config
        keychain_service: Keychain service name

    Returns:
        Configured SecretsManager
    """
    global _secrets_manager

    _secrets_manager = SecretsManager(
        backends=backends,
        doppler_project=doppler_project,
        doppler_config=doppler_config,
        keychain_service=keychain_service,
    )

    return _secrets_manager
