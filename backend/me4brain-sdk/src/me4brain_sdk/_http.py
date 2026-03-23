from __future__ import annotations

"""HTTP client with retry logic, connection pooling, and error handling."""

from typing import Any, AsyncIterator
import json

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
)

from me4brain_sdk.exceptions import (
    Me4BrAInAPIError,
    Me4BrAInAuthError,
    Me4BrAInConnectionError,
    Me4BrAInRateLimitError,
    Me4BrAInTimeoutError,
    Me4BrAInNotFoundError,
    Me4BrAInValidationError,
)


class HTTPClient:
    """Async HTTP client with retry, pooling, and error handling.

    Features:
    - Connection pooling for high throughput
    - Automatic retries with exponential backoff
    - Proper error mapping to SDK exceptions
    - Streaming support for large responses
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_POOL_CONNECTIONS = 100
    DEFAULT_POOL_MAXSIZE = 100

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        pool_connections: int = DEFAULT_POOL_CONNECTIONS,
        pool_maxsize: int = DEFAULT_POOL_MAXSIZE,
        tenant_id: str | None = None,
        user_id: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize HTTP client.

        Args:
            base_url: Base URL of Me4BrAIn API
            api_key: API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            pool_connections: Connection pool size
            pool_maxsize: Max connections per host
            tenant_id: Default tenant ID for requests
            user_id: Default user ID for requests
            extra_headers: Additional headers to include
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self._tenant_id = tenant_id
        self._user_id = user_id

        # Build default headers
        headers = {
            "User-Agent": "me4brain-sdk/1.0.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if api_key:
            headers["X-API-Key"] = api_key

        if tenant_id:
            headers["X-Tenant-ID"] = tenant_id

        if user_id:
            headers["X-User-ID"] = user_id

        if extra_headers:
            headers.update(extra_headers)

        # Create async client
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            limits=httpx.Limits(
                max_connections=pool_connections,
                max_keepalive_connections=pool_maxsize,
            ),
            headers=headers,
        )

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        await self._client.aclose()

    async def __aenter__(self) -> "HTTPClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _handle_error(self, response: httpx.Response) -> None:
        """Convert HTTP errors to SDK exceptions."""
        status = response.status_code

        try:
            body = response.json()
            message = body.get("detail", body.get("message", response.text))
        except (json.JSONDecodeError, ValueError):
            message = response.text or f"HTTP {status}"
            body = None

        if status == 401:
            raise Me4BrAInAuthError(message)
        elif status == 403:
            raise Me4BrAInAuthError(f"Access denied: {message}")
        elif status == 404:
            raise Me4BrAInNotFoundError("Resource", "unknown")
        elif status == 422:
            errors = body.get("detail", []) if body else []
            raise Me4BrAInValidationError(message, errors)
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            raise Me4BrAInRateLimitError(
                message,
                retry_after=float(retry_after) if retry_after else None,
            )
        else:
            raise Me4BrAInAPIError(message, status, body)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=10),
        retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
        reraise=True,
    )
    async def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path (e.g., "/v1/memory/search")
            params: Query parameters
            json_data: JSON body
            headers: Additional headers

        Returns:
            Parsed JSON response

        Raises:
            Me4BrAInAPIError: On API errors
            Me4BrAInConnectionError: On connection failures
            Me4BrAInTimeoutError: On timeout
        """
        try:
            response = await self._client.request(
                method=method,
                url=path,
                params=params,
                json=json_data,
                headers=headers,
            )

            if response.status_code >= 400:
                self._handle_error(response)

            # Handle empty responses
            if response.status_code == 204 or not response.content:
                return {}

            return response.json()

        except httpx.ConnectError as e:
            raise Me4BrAInConnectionError(f"Failed to connect: {e}") from e
        except httpx.TimeoutException as e:
            raise Me4BrAInTimeoutError(f"Request timed out: {e}") from e

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """HTTP GET request."""
        return await self.request("GET", path, params=params, **kwargs)

    async def post(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """HTTP POST request."""
        return await self.request("POST", path, json_data=json_data, **kwargs)

    async def put(
        self,
        path: str,
        json_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """HTTP PUT request."""
        return await self.request("PUT", path, json_data=json_data, **kwargs)

    async def delete(
        self,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """HTTP DELETE request."""
        return await self.request("DELETE", path, **kwargs)

    async def stream(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream response as Server-Sent Events.

        Yields:
            Parsed JSON chunks from SSE stream
        """
        try:
            async with self._client.stream(
                method=method,
                url=path,
                json=json_data,
                **kwargs,
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    self._handle_error(response)

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            yield json.loads(data)
                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError as e:
            raise Me4BrAInConnectionError(f"Stream connection failed: {e}") from e
        except httpx.TimeoutException as e:
            raise Me4BrAInTimeoutError(f"Stream timed out: {e}") from e
