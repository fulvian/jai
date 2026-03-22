"""
Input validation and sanitization module for JAI.

Provides comprehensive input validation, XSS prevention,
and data sanitization utilities.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

# Optional bleach import - will work without it but with reduced security
BLEACH_AVAILABLE = False
bleach = None
try:
    import bleach

    BLEACH_AVAILABLE = True
except ImportError:
    bleach = None


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


class SanitizedString:
    """A string that has been sanitized for safe use.

    This class wraps a sanitized string and provides
    safe access to its content.
    """

    def __init__(self, value: str, original_length: int):
        self._value = value
        self._original_length = original_length

    @property
    def value(self) -> str:
        """Get the sanitized value."""
        return self._value

    def __str__(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return f"SanitizedString({self._value!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SanitizedString):
            return self._value == other._value
        if isinstance(other, str):
            return self._value == other
        return False


def sanitize_html(content: str, strip: bool = True) -> str:
    """Sanitize HTML content to prevent XSS attacks.

    Args:
        content: The content to sanitize
        strip: If True, remove all HTML tags. If False, allow no tags.

    Returns:
        Sanitized string safe for display
    """
    if not content:
        return ""

    if not BLEACH_AVAILABLE:
        # Fallback: basic tag stripping without bleach
        if strip:
            # Remove HTML tags using regex
            cleaned = re.sub(r"<[^>]+>", "", content)
            # Remove javascript: URIs
            cleaned = re.sub(r"javascript:", "", cleaned, flags=re.IGNORECASE)
            # Remove on* event handlers
            cleaned = re.sub(r"\bon\w+\s*=", "", cleaned, flags=re.IGNORECASE)
            return cleaned.strip()
        return content

    if strip:
        # Remove all HTML tags
        assert bleach is not None
        return bleach.clean(content, tags=[], strip=True)

    # For allowing some tags, use bleach.clean with allowed tags
    assert bleach is not None
    return bleach.clean(
        content,
        tags=["b", "i", "em", "strong", "a", "code", "pre"],
        attributes={},
        strip=True,
    )


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal attacks.

    Args:
        filename: The filename to sanitize

    Returns:
        Sanitized filename safe for file system operations
    """
    if not filename:
        return "unnamed"

    # Remove path components
    filename = filename.replace("/", "_").replace("\\", "_")

    # Remove null bytes
    filename = filename.replace("\x00", "")

    # Remove common traversal patterns
    filename = re.sub(r"\.\.+", "", filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip(". ")

    # Limit length
    max_length = 255
    if len(filename) > max_length:
        name, ext = filename.rsplit(".", 1) if "." in filename else (filename, "")
        ext = f".{ext}" if ext else ""
        name = name[: max_length - len(ext)]
        filename = name + ext

    return filename or "unnamed"


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace in text.

    Args:
        text: The text to normalize

    Returns:
        Text with normalized whitespace
    """
    if not text:
        return ""

    # Replace multiple whitespace with single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def validate_length(
    value: str,
    field_name: str,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> str:
    """Validate string length.

    Args:
        value: The string to validate
        field_name: Name of the field for error messages
        min_length: Minimum allowed length
        max_length: Maximum allowed length

    Returns:
        The validated string

    Raises:
        ValidationError: If validation fails
    """
    if min_length is not None and len(value) < min_length:
        raise ValidationError(field_name, f"Must be at least {min_length} characters")
    if max_length is not None and len(value) > max_length:
        raise ValidationError(field_name, f"Must be at most {max_length} characters")
    return value


def validate_alphanumeric(
    value: str,
    field_name: str,
    allow_spaces: bool = False,
    allow_dashes: bool = False,
    allow_underscores: bool = False,
) -> str:
    """Validate that a string contains only alphanumeric characters.

    Args:
        value: The string to validate
        field_name: Name of the field for error messages
        allow_spaces: Allow space characters
        allow_dashes: Allow dash characters
        allow_underscores: Allow underscore characters

    Returns:
        The validated string

    Raises:
        ValidationError: If validation fails
    """
    pattern_parts = [r"[a-zA-Z0-9]"]
    if allow_spaces:
        pattern_parts.append(" ")
    if allow_dashes:
        pattern_parts.append("-")
    if allow_underscores:
        pattern_parts.append("_")

    pattern = "".join(pattern_parts)
    if not re.match(f"^{pattern}*$", value):
        raise ValidationError(
            field_name,
            "Must contain only alphanumeric characters"
            + (", spaces" if allow_spaces else "")
            + (", dashes" if allow_dashes else "")
            + (", underscores" if allow_underscores else ""),
        )
    return value


def validate_uuid(value: str, field_name: str) -> str:
    """Validate UUID format.

    Args:
        value: The string to validate
        field_name: Name of the field for error messages

    Returns:
        The validated UUID string

    Raises:
        ValidationError: If validation fails
    """
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )
    if not uuid_pattern.match(value):
        raise ValidationError(field_name, "Must be a valid UUID")
    return value.lower()


def validate_email(email: str) -> str:
    """Validate email format.

    Args:
        email: The email to validate

    Returns:
        The validated email

    Raises:
        ValidationError: If validation fails
    """
    email_pattern = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
    if not email_pattern.match(email):
        raise ValidationError("email", "Must be a valid email address")
    return email.lower()


def validate_api_key_format(key: str) -> str:
    """Validate API key format.

    Args:
        key: The API key to validate

    Returns:
        The validated key

    Raises:
        ValidationError: If validation fails
    """
    if not key:
        raise ValidationError("api_key", "API key cannot be empty")

    # Keys should start with mk_ and be URL-safe base64
    if not key.startswith("mk_"):
        raise ValidationError("api_key", "API key must start with 'mk_'")

    if len(key) < 20:
        raise ValidationError("api_key", "API key is too short")

    return key


def sanitize_user_input(
    content: str,
    max_length: int = 10000,
    strip_html: bool = True,
) -> SanitizedString:
    """Sanitize user input for safe storage and display.

    This function:
    1. Normalizes Unicode characters
    2. Strips or sanitizes HTML tags
    3. Normalizes whitespace
    4. Validates length

    Args:
        content: The user input to sanitize
        max_length: Maximum allowed length
        strip_html: Whether to strip HTML tags

    Returns:
        SanitizedString wrapper with sanitized content
    """
    if not content:
        return SanitizedString("", 0)

    original_length = len(content)

    # Normalize Unicode
    content = unicodedata.normalize("NFKC", content)

    # Strip HTML if requested
    if strip_html:
        content = sanitize_html(content, strip=True)

    # Normalize whitespace
    content = normalize_whitespace(content)

    # Truncate if too long
    if len(content) > max_length:
        content = content[:max_length]

    return SanitizedString(content, original_length)


# =============================================================================
# Pydantic Validators for API Models
# =============================================================================


class ValidatedModel(BaseModel):
    """Base model with additional validation."""

    @field_validator("*", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Any) -> Any:
        """Strip whitespace from string values."""
        if isinstance(v, str):
            return v.strip()
        return v


class ConversationRequest(ValidatedModel):
    """Validated conversation creation request."""

    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = Field(None, max_length=2048)
    user_id: str = Field(..., min_length=1, max_length=128)

    @field_validator("title", "description", mode="before")
    @classmethod
    def sanitize_text_fields(cls, v: Any) -> Any:
        """Sanitize text fields."""
        if isinstance(v, str):
            v = sanitize_html(v, strip=True)
            v = normalize_whitespace(v)
        return v


class MessageContent(ValidatedModel):
    """Validated message content."""

    content: str = Field(..., min_length=1, max_length=32000)
    role: str = Field(...)
    name: Optional[str] = Field(None, max_length=256)

    @field_validator("content", mode="before")
    @classmethod
    def sanitize_content(cls, v: Any) -> Any:
        """Sanitize message content."""
        if isinstance(v, str):
            v = sanitize_html(v, strip=True)
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        """Validate message role."""
        allowed = {"user", "assistant", "system", "tool"}
        if v.lower() not in allowed:
            raise ValueError(f"Role must be one of: {allowed}")
        return v.lower()


class APIKeyCreateRequest(ValidatedModel):
    """Validated API key creation request."""

    name: str = Field(..., min_length=1, max_length=128)
    scopes: list[str] = Field(default_factory=list)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)

    @field_validator("name", mode="before")
    @classmethod
    def sanitize_name(cls, v: Any) -> Any:
        """Sanitize API key name."""
        if isinstance(v, str):
            v = sanitize_html(v, strip=True)
            v = normalize_whitespace(v)
        return v

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        """Validate API key scopes."""
        allowed = {"read", "write", "admin"}
        for scope in v:
            if scope not in allowed:
                raise ValueError(f"Invalid scope: {scope}. Allowed: {allowed}")
        return v


# =============================================================================
# Rate Limiting Helpers
# =============================================================================


def get_client_identifier(
    request: Any,
    api_key: Optional[str] = None,
) -> str:
    """Get a unique identifier for a client for rate limiting.

    Uses API key if available, otherwise falls back to IP address.

    Args:
        request: FastAPI request object
        api_key: Optional API key

    Returns:
        Client identifier string
    """
    if api_key:
        # Hash the API key for privacy
        import hashlib

        return hashlib.sha256(api_key.encode()).hexdigest()[:16]

    # Fall back to IP address
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"
