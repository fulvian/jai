"""
Security module - Encryption utilities for JAI.

Provides field-level encryption for sensitive data at rest.
Uses Fernet symmetric encryption for secure data storage.
"""

from __future__ import annotations

import base64
import hashlib
import os
import structlog
from typing import Any, Optional

logger = structlog.get_logger(__name__)


class EncryptionError(Exception):
    """Exception raised when encryption fails."""

    pass


class FieldEncryptor:
    """Field-level encryption for sensitive data.

    Uses Fernet symmetric encryption for secure storage of
    sensitive fields like API keys, PII, etc.
    """

    def __init__(self, key: Optional[str] = None):
        """Initialize the encryptor.

        Args:
            key: Encryption key. If None, uses ENCRYPTION_KEY from environment.
                The key must be 32 url-safe base64-encoded bytes.
        """
        if key is None:
            key = os.environ.get("ENCRYPTION_KEY", "")

        if not key:
            # Generate a key for development (NOT for production)
            logger.warning(
                "encryption_key_not_set",
                message="Using insecure development key. Set ENCRYPTION_KEY env var.",
            )
            key = self._generate_insecure_key()

        self._cipher = self._get_cipher(key)

    def _get_cipher(self, key: str):
        """Get Fernet cipher from key.

        Args:
            key: Encryption key string

        Returns:
            Fernet cipher instance
        """
        try:
            from cryptography.fernet import Fernet

            # Derive a proper Fernet key from the provided key
            key_bytes = hashlib.sha256(key.encode()).digest()
            fernet_key = base64.urlsafe_b64encode(key_bytes)
            return Fernet(fernet_key)
        except ImportError:
            logger.warning(
                "cryptography_not_installed",
                message="Install cryptography for encryption: pip install cryptography",
            )
            return None

    @staticmethod
    def _generate_insecure_key() -> str:
        """Generate an insecure key for development only.

        Returns:
            A development-only key
        """
        return "dev-only-encryption-key-do-not-use-in-production"

    def encrypt(self, value: str) -> str:
        """Encrypt a string value.

        Args:
            value: The plaintext value to encrypt

        Returns:
            Base64-encoded encrypted value

        Raises:
            EncryptionError: If encryption fails
        """
        if not value:
            return value

        if self._cipher is None:
            logger.warning("encryption_unavailable")
            return value

        try:
            encrypted = self._cipher.encrypt(value.encode())
            return base64.urlsafe_b64encode(encrypted).decode()
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt value: {e}") from e

    def decrypt(self, encrypted: str) -> str:
        """Decrypt an encrypted value.

        Args:
            encrypted: Base64-encoded encrypted value

        Returns:
            The decrypted plaintext value

        Raises:
            EncryptionError: If decryption fails
        """
        if not encrypted:
            return encrypted

        if self._cipher is None:
            logger.warning("decryption_unavailable")
            return encrypted

        try:
            encrypted_bytes = base64.urlsafe_b64decode(encrypted.encode())
            decrypted = self._cipher.decrypt(encrypted_bytes)
            return decrypted.decode()
        except Exception as e:
            raise EncryptionError(f"Failed to decrypt value: {e}") from e

    def encrypt_dict(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Encrypt specific fields in a dictionary.

        Args:
            data: Dictionary containing data to encrypt
            fields: List of field names to encrypt

        Returns:
            Dictionary with specified fields encrypted
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        return result

    def decrypt_dict(self, data: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        """Decrypt specific fields in a dictionary.

        Args:
            data: Dictionary containing encrypted data
            fields: List of field names to decrypt

        Returns:
            Dictionary with specified fields decrypted
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                try:
                    result[field] = self.decrypt(result[field])
                except EncryptionError:
                    logger.error("decrypt_field_failed", field=field)
        return result


# Global encryptor instance
_encryptor: Optional[FieldEncryptor] = None


def get_encryptor() -> FieldEncryptor:
    """Get the global encryptor instance.

    Returns:
        The global FieldEncryptor
    """
    global _encryptor
    if _encryptor is None:
        _encryptor = FieldEncryptor()
    return _encryptor


def encrypt_value(value: str) -> str:
    """Convenience function to encrypt a value.

    Args:
        value: The plaintext value to encrypt

    Returns:
        The encrypted value
    """
    return get_encryptor().encrypt(value)


def decrypt_value(encrypted: str) -> str:
    """Convenience function to decrypt a value.

    Args:
        encrypted: The encrypted value to decrypt

    Returns:
        The decrypted plaintext value
    """
    return get_encryptor().decrypt(encrypted)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key for storage.

    Args:
        api_key: The raw API key

    Returns:
        The encrypted API key
    """
    return encrypt_value(api_key)


def decrypt_api_key(encrypted: str) -> str:
    """Decrypt an API key from storage.

    Args:
        encrypted: The encrypted API key

    Returns:
        The raw API key
    """
    return decrypt_value(encrypted)


def mask_sensitive_data(data: str, visible_chars: int = 4) -> str:
    """Mask sensitive data for logging/display.

    Args:
        data: The sensitive data to mask
        visible_chars: Number of characters to keep visible at the end

    Returns:
        Masked string (e.g., "****1234")
    """
    if not data or len(data) <= visible_chars:
        return "****"
    return "*" * (len(data) - visible_chars) + data[-visible_chars:]
