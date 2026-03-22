from __future__ import annotations

"""Me4BrAIn SDK - Python client for Me4BrAIn Agentic Memory Platform.

Usage:
    from me4brain_sdk import AsyncMe4BrAInClient

    async with AsyncMe4BrAInClient(
        base_url="http://localhost:8100",
        api_key="your-api-key",
    ) as client:
        response = await client.cognitive.query("What did we discuss?")
        print(response.answer)
"""

from me4brain_sdk.client import AsyncMe4BrAInClient
from me4brain_sdk._sync import Me4BrAInClient
from me4brain_sdk.exceptions import (
    Me4BrAInError,
    Me4BrAInAPIError,
    Me4BrAInConnectionError,
    Me4BrAInTimeoutError,
    Me4BrAInAuthError,
    Me4BrAInRateLimitError,
)
from me4brain_sdk.namespaces.engine import EngineQueryResponse, ToolCallInfo as ToolInfo

__version__ = "1.0.0"
__all__ = [
    "AsyncMe4BrAInClient",
    "Me4BrAInClient",
    "EngineQueryResponse",
    "ToolInfo",
    "Me4BrAInError",
    "Me4BrAInAPIError",
    "Me4BrAInConnectionError",
    "Me4BrAInTimeoutError",
    "Me4BrAInAuthError",
    "Me4BrAInRateLimitError",
]
