"""Test the retry mechanism in domain classification (Phase 1.3.2)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.engine.hybrid_router.domain_classifier import (
    MAX_CLASSIFICATION_RETRIES,
    DomainClassifier,
)
from me4brain.engine.hybrid_router.types import HybridRouterConfig


@pytest.mark.asyncio
async def test_classify_retries_on_timeout_then_succeeds():
    """Test that classify retries after timeout and succeeds on retry."""
    # Setup
    llm_client = AsyncMock()
    config = HybridRouterConfig()
    classifier = DomainClassifier(llm_client, ["sports_nba", "web_search"], config)

    # First attempt: timeout
    # Second attempt: success
    success_response = MagicMock()
    success_response.choices[0].message.content = (
        '{"domains": [{"name": "sports_nba", "complexity": "low"}], '
        '"confidence": 0.9, "query_summary": "NBA query"}'
    )

    llm_client.generate_response.side_effect = [
        TimeoutError("timeout"),  # First call times out
        success_response,  # Second call succeeds
    ]

    with patch("asyncio.wait_for") as mock_wait_for:
        # Make first call raise TimeoutError, second call return response
        async def side_effect(coro, timeout):
            if mock_wait_for.call_count == 1:
                raise TimeoutError("timeout")
            return success_response

        mock_wait_for.side_effect = side_effect

        # Reset call count
        mock_wait_for.reset_mock()

        # Call multiple times to verify retry works
        result = await classifier.classify("Quali sono le partite NBA stasera?")

    # Assert: should have retried and succeeded
    assert result.domain_names == ["sports_nba"]
    assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_classify_falls_back_after_max_retries():
    """Test that classify falls back after exhausting all retries."""
    # Setup
    llm_client = AsyncMock()
    config = HybridRouterConfig()
    classifier = DomainClassifier(llm_client, ["sports_nba", "web_search"], config)

    # All attempts timeout
    async def timeout_coro(*args, **kwargs):
        raise TimeoutError("persistent timeout")

    llm_client.generate_response = timeout_coro

    with patch("asyncio.wait_for") as mock_wait_for:
        mock_wait_for.side_effect = TimeoutError("timeout")

        result = await classifier.classify("NBA query with timeout")

    # Assert: should have fallen back to keyword detection
    assert result.confidence == 0.6  # Fallback confidence
    assert "Fallback classification" in result.query_summary


@pytest.mark.asyncio
async def test_classify_retries_on_json_parse_error():
    """Test that classify retries on JSON parse error."""
    llm_client = AsyncMock()
    config = HybridRouterConfig()
    classifier = DomainClassifier(llm_client, ["sports_nba", "web_search"], config)

    # First attempt: invalid JSON
    # Second attempt: valid JSON
    bad_response = MagicMock()
    bad_response.choices[0].message.content = "this is not json"

    success_response = MagicMock()
    success_response.choices[0].message.content = (
        '{"domains": [{"name": "sports_nba", "complexity": "low"}], '
        '"confidence": 0.95, "query_summary": "NBA query"}'
    )

    call_count = 0

    async def generate_response_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return bad_response
        return success_response

    llm_client.generate_response = generate_response_side_effect

    with patch("asyncio.wait_for") as mock_wait_for:

        async def side_effect(coro, timeout):
            return await coro

        mock_wait_for.side_effect = side_effect

        result = await classifier.classify("Quali sono le partite NBA stasera?")

    # Assert: should have retried and succeeded
    assert result.domain_names == ["sports_nba"]
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_with_trace_retries():
    """Test that classify_with_trace also implements retry logic."""
    llm_client = AsyncMock()
    config = HybridRouterConfig()
    classifier = DomainClassifier(llm_client, ["sports_nba", "web_search"], config)

    # First attempt: timeout
    # Second attempt: success
    success_response = MagicMock()
    success_response.choices[0].message.content = (
        '{"domains": [{"name": "sports_nba", "complexity": "low"}], '
        '"confidence": 0.92, "query_summary": "NBA query"}'
    )

    call_count = 0

    async def generate_response_side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TimeoutError("timeout")
        return success_response

    llm_client.generate_response = generate_response_side_effect

    with patch("asyncio.wait_for") as mock_wait_for:

        async def side_effect(coro, timeout):
            try:
                return await coro
            except TimeoutError:
                if mock_wait_for.call_count <= 1:
                    raise
                return success_response

        mock_wait_for.side_effect = side_effect

        classification, trace = await classifier.classify_with_trace(
            "Quali sono le partite NBA stasera?"
        )

    # Assert: should have retried and succeeded
    assert classification.domain_names == ["sports_nba"]
    assert classification.confidence == 0.92
    assert trace.success
    assert not trace.fallback_applied


@pytest.mark.asyncio
async def test_classify_with_trace_fallback_after_retries():
    """Test that classify_with_trace falls back and sets trace properly."""
    llm_client = AsyncMock()
    config = HybridRouterConfig()
    classifier = DomainClassifier(llm_client, ["sports_nba", "web_search"], config)

    # All attempts fail with empty response
    bad_response = MagicMock()
    bad_response.choices[0].message.content = ""

    llm_client.generate_response = AsyncMock(return_value=bad_response)

    with patch("asyncio.wait_for") as mock_wait_for:

        async def side_effect(coro, timeout):
            return await coro

        mock_wait_for.side_effect = side_effect

        classification, trace = await classifier.classify_with_trace("NBA query that fails")

    # Assert: should have fallen back
    assert not trace.success
    assert trace.fallback_applied
    assert trace.error_code == "EMPTY_RESPONSE"
    assert classification.confidence == 0.6  # Fallback confidence


def test_max_retries_constant_is_three():
    """Verify that MAX_CLASSIFICATION_RETRIES is set to 3."""
    assert MAX_CLASSIFICATION_RETRIES == 3
