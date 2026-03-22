"""E2E Test Configuration for Me4BrAIn SDK."""

from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Set test environment
os.environ.setdefault("ME4BRAIN_BASE_URL", "http://localhost:8100")
os.environ.setdefault("ME4BRAIN_API_KEY", "test-api-key")


@pytest_asyncio.fixture
async def async_client():
    """Create async client for E2E tests - per-function scope."""
    from me4brain_sdk import AsyncMe4BrAInClient

    client = AsyncMe4BrAInClient(
        base_url=os.environ["ME4BRAIN_BASE_URL"],
        api_key=os.environ.get("ME4BRAIN_API_KEY", ""),
        timeout=30.0,
        max_retries=2,
    )
    await client.__aenter__()
    yield client
    await client.__aexit__(None, None, None)


@pytest.fixture
def sync_client():
    """Create sync client for E2E tests."""
    from me4brain_sdk import Me4BrAInClient

    client = Me4BrAInClient(
        base_url=os.environ["ME4BRAIN_BASE_URL"],
        api_key=os.environ.get("ME4BRAIN_API_KEY", ""),
        timeout=30.0,
    )
    yield client
    client.close()


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: End-to-end tests against live API")
    config.addinivalue_line("markers", "slow: Tests that take longer to run")
    config.addinivalue_line("markers", "requires_google: Tests requiring Google OAuth")
    config.addinivalue_line("markers", "requires_auth: Tests requiring API authentication")
