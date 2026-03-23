from __future__ import annotations

"""SDK-specific exceptions for Me4BrAIn."""

from typing import Any


class Me4BrAInError(Exception):
    """Base exception for all Me4BrAIn SDK errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class Me4BrAInAPIError(Me4BrAInError):
    """Error returned by the Me4BrAIn API."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message, {"status_code": status_code, "response": response_body})
        self.status_code = status_code
        self.response_body = response_body

    def __str__(self) -> str:
        return f"[{self.status_code}] {self.message}"


class Me4BrAInConnectionError(Me4BrAInError):
    """Failed to connect to Me4BrAIn API."""

    pass


class Me4BrAInTimeoutError(Me4BrAInError):
    """Request to Me4BrAIn API timed out."""

    pass


class Me4BrAInAuthError(Me4BrAInAPIError):
    """Authentication/authorization error (401/403)."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, status_code=401)


class Me4BrAInRateLimitError(Me4BrAInAPIError):
    """Rate limit exceeded (429)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class Me4BrAInNotFoundError(Me4BrAInAPIError):
    """Resource not found (404)."""

    def __init__(self, resource_type: str, resource_id: str) -> None:
        message = f"{resource_type} '{resource_id}' not found"
        super().__init__(message, status_code=404)
        self.resource_type = resource_type
        self.resource_id = resource_id


class Me4BrAInValidationError(Me4BrAInAPIError):
    """Validation error from API (422)."""

    def __init__(
        self,
        message: str,
        validation_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message, status_code=422)
        self.validation_errors = validation_errors or []
