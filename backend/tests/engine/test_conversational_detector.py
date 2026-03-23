"""Tests for ConversationalDetector."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from me4brain.engine.conversational_detector import ConversationalDetector


@pytest.fixture
def detector():
    """Create a ConversationalDetector instance."""
    return ConversationalDetector()


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = AsyncMock()
    return client


class TestConversationalDetectorFastPath:
    """Test fast-path regex pattern matching."""

    @pytest.mark.asyncio
    async def test_greeting_detection(self, detector, mock_llm_client):
        """Test detection of greeting patterns."""
        test_cases = [
            ("ciao", True, "matched_pattern:greeting"),
            ("hello", True, "matched_pattern:greeting"),
            ("buongiorno", True, "matched_pattern:greeting"),
            ("salve", True, "matched_pattern:greeting"),
        ]

        for query, expected_is_conv, expected_reason in test_cases:
            is_conv, reason = await detector.is_conversational(query, mock_llm_client)
            assert is_conv == expected_is_conv, f"Failed for query: {query}"
            assert reason == expected_reason, f"Wrong reason for query: {query}"

    @pytest.mark.asyncio
    async def test_farewell_detection(self, detector, mock_llm_client):
        """Test detection of farewell patterns."""
        test_cases = [
            ("arrivederci", True, "matched_pattern:farewell"),
            ("addio", True, "matched_pattern:farewell"),
            ("bye", True, "matched_pattern:farewell"),
            ("grazie", True, "matched_pattern:farewell"),
        ]

        for query, expected_is_conv, expected_reason in test_cases:
            is_conv, reason = await detector.is_conversational(query, mock_llm_client)
            assert is_conv == expected_is_conv, f"Failed for query: {query}"
            assert reason == expected_reason, f"Wrong reason for query: {query}"

    @pytest.mark.asyncio
    async def test_small_talk_detection(self, detector, mock_llm_client):
        """Test detection of small talk patterns."""
        test_cases = [
            ("come stai", True, "matched_pattern:small_talk"),
            ("come va", True, "matched_pattern:small_talk"),
            ("what's up", True, "matched_pattern:small_talk"),
        ]

        for query, expected_is_conv, expected_reason in test_cases:
            is_conv, reason = await detector.is_conversational(query, mock_llm_client)
            assert is_conv == expected_is_conv, f"Failed for query: {query}"
            assert reason == expected_reason, f"Wrong reason for query: {query}"

    @pytest.mark.asyncio
    async def test_meta_detection(self, detector, mock_llm_client):
        """Test detection of meta questions about the bot."""
        test_cases = [
            ("chi sei", True, "matched_pattern:meta_about_bot"),
            ("cosa puoi fare", True, "matched_pattern:meta_about_bot"),
            ("what are you", True, "matched_pattern:meta_about_bot"),
        ]

        for query, expected_is_conv, expected_reason in test_cases:
            is_conv, reason = await detector.is_conversational(query, mock_llm_client)
            assert is_conv == expected_is_conv, f"Failed for query: {query}"
            assert reason == expected_reason, f"Wrong reason for query: {query}"


class TestConversationalDetectorToolRequired:
    """Test detection of tool-required queries."""

    @pytest.mark.asyncio
    async def test_long_query_not_conversational(self, detector, mock_llm_client):
        """Test that long queries are not classified as conversational."""
        long_query = (
            "Cerca le email sul progetto X e gli appuntamenti correlati e poi analizza i dati"
        )
        is_conv, reason = await detector.is_conversational(long_query, mock_llm_client)
        assert is_conv is False
        assert "too_long_for_conversational" in reason

    @pytest.mark.asyncio
    async def test_very_short_query_assumed_conversational(self, detector, mock_llm_client):
        """Test that very short queries are assumed conversational."""
        is_conv, reason = await detector.is_conversational("ok", mock_llm_client)
        assert is_conv is True
        assert "very_short_query_heuristic" in reason


class TestConversationalDetectorSlowPath:
    """Test slow-path LLM classification."""

    @pytest.mark.asyncio
    async def test_llm_classification_conversational(self, detector, mock_llm_client):
        """Test LLM-based classification for conversational query."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = '{"is_conversational": true, "reason": "opinion_ask"}'
        mock_llm_client.generate_response.return_value = mock_response

        is_conv, reason = await detector.is_conversational("cosa pensi di questo", mock_llm_client)
        assert is_conv is True
        assert "llm_classification" in reason

    @pytest.mark.asyncio
    async def test_llm_classification_tool_required(self, detector, mock_llm_client):
        """Test LLM-based classification for tool-required query."""
        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = '{"is_conversational": false, "reason": "requires_search"}'
        mock_llm_client.generate_response.return_value = mock_response

        is_conv, reason = await detector.is_conversational(
            "quali sono le ultime notizie", mock_llm_client
        )
        assert is_conv is False
        assert "llm_classification" in reason

    @pytest.mark.asyncio
    async def test_llm_json_parse_error(self, detector, mock_llm_client):
        """Test handling of LLM JSON parse errors."""
        # Mock LLM response with invalid JSON
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "invalid json"
        mock_llm_client.generate_response.return_value = mock_response

        is_conv, reason = await detector.is_conversational("ambiguous query", mock_llm_client)
        assert is_conv is False
        assert "llm_json_parse_failed" in reason

    @pytest.mark.asyncio
    async def test_llm_empty_response(self, detector, mock_llm_client):
        """Test handling of empty LLM responses."""
        # Mock empty LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""
        mock_llm_client.generate_response.return_value = mock_response

        is_conv, reason = await detector.is_conversational("ambiguous query", mock_llm_client)
        assert is_conv is False
        assert "llm_empty_response" in reason

    @pytest.mark.asyncio
    async def test_llm_exception_handling(self, detector, mock_llm_client):
        """Test handling of LLM exceptions."""
        # Mock LLM exception
        mock_llm_client.generate_response.side_effect = Exception("LLM error")

        is_conv, reason = await detector.is_conversational("ambiguous query", mock_llm_client)
        assert is_conv is False
        assert "detection_error" in reason
