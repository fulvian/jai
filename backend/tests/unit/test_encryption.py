"""
Unit tests for Encryption module.
"""

from __future__ import annotations

import os

from me4brain.security.encryption import (
    EncryptionError,
    FieldEncryptor,
    decrypt_api_key,
    decrypt_value,
    encrypt_api_key,
    encrypt_value,
    get_encryptor,
    mask_sensitive_data,
)


class TestFieldEncryptor:
    """Test FieldEncryptor class."""

    def test_encrypt_decrypt_roundtrip(self):
        """Test encrypting and decrypting returns original value."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        original = "Hello, World!"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_output(self):
        """Test encryption produces different output than input."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        original = "Hello, World!"
        encrypted = encryptor.encrypt(original)
        assert encrypted != original

    def test_encrypt_empty_string(self):
        """Test encrypting empty string returns empty."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        assert encryptor.encrypt("") == ""
        assert encryptor.decrypt("") == ""

    def test_encrypt_dict(self):
        """Test encrypting specific fields in a dictionary."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        data = {"name": "John", "api_key": "secret123", "email": "john@example.com"}
        encrypted = encryptor.encrypt_dict(data, fields=["api_key"])

        # Check api_key is encrypted
        assert encrypted["api_key"] != "secret123"
        assert encrypted["api_key"] != data["api_key"]
        # Check other fields unchanged
        assert encrypted["name"] == "John"
        assert encrypted["email"] == "john@example.com"

    def test_decrypt_dict(self):
        """Test decrypting specific fields in a dictionary."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        data = {"name": "John", "api_key": "secret123", "email": "john@example.com"}
        encrypted = encryptor.encrypt_dict(data, fields=["api_key"])
        decrypted = encryptor.decrypt_dict(encrypted, fields=["api_key"])

        # Check api_key is restored
        assert decrypted["api_key"] == "secret123"
        # Check other fields unchanged
        assert decrypted["name"] == "John"
        assert decrypted["email"] == "john@example.com"

    def test_encrypt_dict_missing_field(self):
        """Test encrypt_dict with missing field doesn't error."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        data = {"name": "John"}
        encrypted = encryptor.encrypt_dict(data, fields=["api_key"])
        assert "api_key" not in encrypted

    def test_encrypt_unicode(self):
        """Test encrypting unicode strings."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        original = "Hello, 世界! 🌍"
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original

    def test_encrypt_long_string(self):
        """Test encrypting a long string."""
        encryptor = FieldEncryptor(key="test-key-for-encryption-32bytes!")
        original = "A" * 10000
        encrypted = encryptor.encrypt(original)
        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original


class TestModuleFunctions:
    """Test module-level convenience functions."""

    def test_encrypt_value(self):
        """Test encrypt_value convenience function."""
        # Set a test key
        os.environ["ENCRYPTION_KEY"] = "test-key-for-encryption-32bytes!"
        result = encrypt_value("secret")
        assert result != "secret"

    def test_decrypt_value(self):
        """Test decrypt_value convenience function."""
        os.environ["ENCRYPTION_KEY"] = "test-key-for-encryption-32bytes!"
        encrypted = encrypt_value("secret")
        decrypted = decrypt_value(encrypted)
        assert decrypted == "secret"

    def test_encrypt_api_key(self):
        """Test encrypt_api_key convenience function."""
        os.environ["ENCRYPTION_KEY"] = "test-key-for-encryption-32bytes!"
        encrypted = encrypt_api_key("mk_testapikey123")
        assert encrypted != "mk_testapikey123"

    def test_decrypt_api_key(self):
        """Test decrypt_api_key convenience function."""
        os.environ["ENCRYPTION_KEY"] = "test-key-for-encryption-32bytes!"
        encrypted = encrypt_api_key("mk_testapikey123")
        decrypted = decrypt_api_key(encrypted)
        assert decrypted == "mk_testapikey123"

    def test_get_encryptor_singleton(self):
        """Test get_encryptor returns same instance."""
        # Set a consistent key
        os.environ["ENCRYPTION_KEY"] = "test-key-for-encryption-32bytes!"
        encryptor1 = get_encryptor()
        encryptor2 = get_encryptor()
        assert encryptor1 is encryptor2


class TestMaskSensitiveData:
    """Test mask_sensitive_data function."""

    def test_mask_long_data(self):
        """Test masking long data shows last characters."""
        # "my_secret_api_key_12345" has 23 chars, shows last 4
        masked = mask_sensitive_data("my_secret_api_key_12345")
        # 23 - 4 = 19 asterisks + "2345"
        assert masked == "*" * 19 + "2345"
        assert len(masked) == 23

    def test_mask_short_data(self):
        """Test masking short data shows nothing."""
        masked = mask_sensitive_data("abc")
        assert masked == "****"

    def test_mask_exact_length(self):
        """Test masking data of exact visible_chars length."""
        masked = mask_sensitive_data("abcde", visible_chars=5)
        assert masked == "****"

    def test_mask_empty_string(self):
        """Test masking empty string."""
        masked = mask_sensitive_data("")
        assert masked == "****"

    def test_mask_none(self):
        """Test masking None returns stars."""
        masked = mask_sensitive_data(None)  # type: ignore
        assert masked == "****"

    def test_mask_custom_visible_chars(self):
        """Test masking with custom visible_chars."""
        # "my_secret_key" has 13 chars, visible_chars=8 shows last 8
        # So 13 - 8 = 5 asterisks + "cret_key"
        masked = mask_sensitive_data("my_secret_key", visible_chars=8)
        assert masked == "*****" + "cret_key"


class TestEncryptionError:
    """Test EncryptionError exception."""

    def test_encryption_error_message(self):
        """Test EncryptionError has proper message."""
        error = EncryptionError("Test error")
        assert str(error) == "Test error"

    def test_encryption_error_inheritance(self):
        """Test EncryptionError inherits from Exception."""
        error = EncryptionError("Test")
        assert isinstance(error, Exception)
