"""Pytest Configuration for Me4BrAIn Tests."""

import pytest


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
