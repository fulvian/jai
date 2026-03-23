"""Tests for ResponseSynthesizer streaming with thinking token extraction.

Tests the three thinking detection strategies:
1. Native reasoning field (delta.reasoning)
2. Explicit <think>...</think> tags in content
3. No-tag fallback (treat everything as content)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from me4brain.engine.synthesizer import ResponseSynthesizer
from me4brain.engine.types import StreamChunk, ToolResult


def _get_type(event) -> str | None:
    """Extract type from StreamChunk or dict."""
    if isinstance(event, StreamChunk):
        return event.type
    if isinstance(event, dict):
        return event.get("type")
    return None


def _get_content(event) -> str | None:
    """Extract content from StreamChunk or dict."""
    if isinstance(event, StreamChunk):
        return event.content
    if isinstance(event, dict):
        return event.get("content")
    return None


def _get_thinking(event) -> str | None:
    """Extract thinking from StreamChunk or dict."""
    if isinstance(event, StreamChunk):
        return event.thinking
    if isinstance(event, dict):
        return event.get("thinking")
    return None


def _get_phase(event) -> str | None:
    """Extract phase from StreamChunk or dict."""
    if isinstance(event, StreamChunk):
        return event.phase
    if isinstance(event, dict):
        return event.get("phase")
    return None


def _make_chunk(content=None, reasoning=None):
    """Create a mock LLMChunk with given content and/or reasoning."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta.content = content
    chunk.choices[0].delta.reasoning = reasoning
    return chunk


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    return AsyncMock()


@pytest.fixture
def synthesizer(mock_llm_client):
    """Create a ResponseSynthesizer instance."""
    return ResponseSynthesizer(mock_llm_client, model="deepseek-chat")


@pytest.fixture
def sample_results():
    """Create sample tool results."""
    return [
        ToolResult(
            tool_name="test_tool",
            success=True,
            data={"result": "test data"},
            latency_ms=100,
        )
    ]


def _setup_mock_stream(mock_llm_client, chunks):
    """Setup mock LLM client to return async generator of chunks.

    Uses side_effect to properly create async generators for each call.
    AsyncMock.return_value wraps in coroutine which breaks 'async for'.
    """

    async def mock_stream(*args, **kwargs):
        for chunk in chunks:
            yield chunk

    mock_llm_client.stream_response = mock_stream


class TestSynthesizeStreamingBasic:
    """Test basic streaming synthesis functionality."""

    @pytest.mark.asyncio
    async def test_empty_results(self, synthesizer):
        """Test handling of empty results."""
        events = []
        async for event in synthesizer.synthesize_streaming("test query", []):
            events.append(event)

        assert len(events) == 1
        assert _get_type(events[0]) == "content"
        assert "Non sono riuscito" in _get_content(events[0])

    @pytest.mark.asyncio
    async def test_all_tools_failed(self, synthesizer):
        """Test handling when all tools fail."""
        results = [
            ToolResult(
                tool_name="test_tool",
                success=False,
                error="Tool failed",
                latency_ms=100,
            )
        ]

        events = []
        async for event in synthesizer.synthesize_streaming("test query", results):
            events.append(event)

        assert len(events) >= 1
        assert _get_type(events[0]) == "content"


class TestSynthesizeStreamingThinkTags:
    """Test thinking extraction using explicit <think>...</think> tags."""

    @pytest.mark.asyncio
    async def test_think_tags_basic(self, synthesizer, mock_llm_client, sample_results):
        """Test basic <think>...</think> tag extraction."""

        _setup_mock_stream(
            mock_llm_client,
            [
                _make_chunk("<think>"),
                _make_chunk("Analyzing the data..."),
                _make_chunk(" Let me check the results."),
                _make_chunk("</think>"),
                _make_chunk("Here is the answer."),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        assert len(thinking_events) > 0, "Should have thinking events"
        assert len(content_events) > 0, "Should have content events"

        # Verify thinking content doesn't appear in content events
        all_thinking = "".join(_get_content(e) or _get_thinking(e) or "" for e in thinking_events)
        all_content = "".join(_get_content(e) or "" for e in content_events)

        assert "Analyzing the data" in all_thinking
        assert "Here is the answer" in all_content
        assert "Analyzing the data" not in all_content

    @pytest.mark.asyncio
    async def test_think_tags_in_single_chunk(self, synthesizer, mock_llm_client, sample_results):
        """Test when <think>...</think> appears in a single initial chunk."""

        _setup_mock_stream(
            mock_llm_client,
            [
                _make_chunk("<think>Quick thought</think>The answer is 42."),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        assert len(thinking_events) > 0
        assert len(content_events) > 0

        all_thinking = "".join(_get_content(e) or "" for e in thinking_events)
        all_content = "".join(_get_content(e) or "" for e in content_events)

        assert "Quick thought" in all_thinking
        assert "The answer is 42" in all_content

    @pytest.mark.asyncio
    async def test_long_thinking_with_markdown(self, synthesizer, mock_llm_client, sample_results):
        """Test that markdown markers inside <think> DON'T cause premature content transition.

        This is the KEY test that validates the fix: previously, markers like '-', '**', '##', '1.'
        inside thinking would prematurely end the thinking phase.
        """

        _setup_mock_stream(
            mock_llm_client,
            [
                _make_chunk("<think>"),
                _make_chunk("## Analysis\n"),
                _make_chunk("- Point 1: check data\n"),
                _make_chunk("- Point 2: **important** finding\n"),
                _make_chunk("1. First step\n"),
                _make_chunk("### Conclusion\n"),
                _make_chunk("The data looks good."),
                _make_chunk("</think>"),
                _make_chunk("\n## Risultati\n"),
                _make_chunk("Ecco i risultati dell'analisi."),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        all_thinking = "".join(_get_content(e) or "" for e in thinking_events)
        all_content = "".join(_get_content(e) or "" for e in content_events)

        # ALL of the analysis should be in thinking, not content
        assert "## Analysis" in all_thinking
        assert "- Point 1" in all_thinking
        assert "**important**" in all_thinking
        assert "1. First step" in all_thinking

        # Content should only have the actual response
        assert "Risultati" in all_content
        assert "## Analysis" not in all_content

    @pytest.mark.asyncio
    async def test_think_tag_split_across_chunks(
        self, synthesizer, mock_llm_client, sample_results
    ):
        """Test handling of </think> tag split across two chunks."""

        _setup_mock_stream(
            mock_llm_client,
            [
                _make_chunk("<think>"),
                _make_chunk("Reasoning here..."),
                _make_chunk("end of thought</thi"),  # Partial tag
                _make_chunk("nk>"),  # Rest of tag
                _make_chunk("Content after thinking."),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        all_thinking = "".join(_get_content(e) or "" for e in thinking_events)
        all_content = "".join(_get_content(e) or "" for e in content_events)

        assert "Reasoning here" in all_thinking
        assert "Content after thinking" in all_content

    @pytest.mark.asyncio
    async def test_thinking_phase_metadata(self, synthesizer, mock_llm_client, sample_results):
        """Test that thinking events have correct phase metadata."""

        _setup_mock_stream(
            mock_llm_client,
            [
                _make_chunk("<think>Some thought</think>Answer."),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        for event in thinking_events:
            assert _get_phase(event) == "synthesis"


class TestSynthesizeStreamingNativeReasoning:
    """Test thinking extraction via native reasoning field."""

    @pytest.mark.asyncio
    async def test_native_reasoning_field(self, synthesizer, mock_llm_client, sample_results):
        """Test that native reasoning field is properly handled."""

        _setup_mock_stream(
            mock_llm_client,
            [
                # Native reasoning chunks (content=None, reasoning has the thinking)
                _make_chunk(content=None, reasoning="Let me think about this..."),
                _make_chunk(content=None, reasoning=" The data shows..."),
                # Then content chunks
                _make_chunk(content="Here is the answer.", reasoning=None),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        assert len(thinking_events) == 2
        assert len(content_events) >= 1

        # Native reasoning should populate both .content and .thinking fields
        for event in thinking_events:
            assert _get_thinking(event) is not None

    @pytest.mark.asyncio
    async def test_native_reasoning_has_both_fields(
        self, synthesizer, mock_llm_client, sample_results
    ):
        """Test that StreamChunk for native reasoning has both content and thinking populated."""

        _setup_mock_stream(
            mock_llm_client,
            [
                _make_chunk(content=None, reasoning="Native thought"),
                _make_chunk(content="Final answer", reasoning=None),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        assert len(thinking_events) == 1
        # Both .content and .thinking should have the reasoning text
        assert _get_content(thinking_events[0]) == "Native thought"
        assert _get_thinking(thinking_events[0]) == "Native thought"


class TestSynthesizeStreamingNoThinking:
    """Test fallback when model doesn't use thinking tags."""

    @pytest.mark.asyncio
    async def test_no_think_tags(self, synthesizer, mock_llm_client, sample_results):
        """Test that content without <think> tags is treated as pure content."""

        _setup_mock_stream(
            mock_llm_client,
            [
                # Model directly outputs content without thinking
                _make_chunk("Ecco i risultati: "),
                _make_chunk("il prezzo è 50.000€"),
                _make_chunk(" e il trend è positivo."),
            ],
        )

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        # Should have NO thinking events and all content
        assert len(thinking_events) == 0, f"Unexpected thinking events: {thinking_events}"
        assert len(content_events) >= 1

        all_content = "".join(_get_content(e) or "" for e in content_events)
        assert "risultati" in all_content
        assert "50.000€" in all_content

    @pytest.mark.asyncio
    async def test_no_think_tags_long_content(self, synthesizer, mock_llm_client, sample_results):
        """Test that long content without <think> tags is all treated as content."""

        # Generate enough content to exceed DETECT_WINDOW (100 chars)
        chunks = [_make_chunk(f"Word{i} ") for i in range(30)]
        _setup_mock_stream(mock_llm_client, chunks)

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        thinking_events = [e for e in events if _get_type(e) == "thinking"]
        content_events = [e for e in events if _get_type(e) == "content"]

        assert len(thinking_events) == 0
        assert len(content_events) >= 1


class TestSynthesizeStreamingErrorHandling:
    """Test error handling in streaming synthesis."""

    @pytest.mark.asyncio
    async def test_stream_timeout(self, synthesizer, mock_llm_client, sample_results):
        """Test handling of stream timeout."""
        import asyncio

        async def mock_stream_timeout(*args, **kwargs):
            await asyncio.sleep(1)
            raise TimeoutError()
            yield  # Make it an async generator

        mock_llm_client.stream_response = mock_stream_timeout

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        assert len(events) >= 1
        assert _get_type(events[-1]) == "content"

    @pytest.mark.asyncio
    async def test_stream_exception(self, synthesizer, mock_llm_client, sample_results):
        """Test handling of stream exceptions."""

        async def mock_stream_error(*args, **kwargs):
            raise Exception("Stream error")
            yield  # Make it an async generator

        mock_llm_client.stream_response = mock_stream_error

        events = []
        async for event in synthesizer.synthesize_streaming("test query", sample_results):
            events.append(event)

        assert len(events) >= 1
        assert _get_type(events[-1]) == "content"
