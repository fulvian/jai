"""Pytest Configuration for Me4BrAIn Tests."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from me4brain.api.routes.session_title import router as session_title_router


@pytest.fixture
def test_settings():
    """Override settings per i test."""
    from me4brain.config.settings import Settings

    return Settings(
        debug=True,
        log_level="DEBUG",
        postgres_host="localhost",
        postgres_port=5489,
        redis_host="localhost",
        redis_port=6389,
    )


@pytest.fixture
async def test_client():
    """Client HTTP per test degli endpoint API con app minimale."""
    app = FastAPI()
    app.include_router(session_title_router, prefix="/v1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
