# Phase 7: Conversation Summarizer Tests
# Tests for ConversationSummarizer

from unittest.mock import AsyncMock, MagicMock

import pytest

from me4brain.engine.conversation_summarizer import ConversationSummarizer
from me4brain.models.conversation import Message, MessageRole


class TestConversationSummarizer:
    """Test suite for ConversationSummarizer."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock ConversationRepository."""
        mock = MagicMock()
        mock.get_messages = AsyncMock()
        return mock

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        mock = MagicMock()
        mock.generate = AsyncMock(return_value="This is a summary of the conversation.")
        return mock

    @pytest.fixture
    def summarizer(self, mock_repository, mock_llm_client):
        """Create ConversationSummarizer with mocked dependencies."""
        summarizer = ConversationSummarizer(
            session=MagicMock(),
            llm_client=mock_llm_client,
        )
        summarizer._repository = mock_repository
        return summarizer

    @pytest.mark.asyncio
    async def test_generate_title(self, summarizer, mock_repository, mock_llm_client):
        """Test generating a title from first user message."""
        mock_repository.get_messages.return_value = [
            Message(
                id="msg_1",
                role=MessageRole.USER,
                content="Help me write a Python function",
            ),
            Message(
                id="msg_2",
                role=MessageRole.ASSISTANT,
                content="I'll help you with that",
            ),
        ]
        mock_llm_client.generate.return_value = "Python Function Help"

        title = await summarizer.generate_title("conv_123")

        assert title is not None
        assert "Python" in title or "Help" in title
        mock_llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_title_no_messages(self, summarizer, mock_repository):
        """Test title generation with no messages."""
        mock_repository.get_messages.return_value = []

        title = await summarizer.generate_title("conv_123")

        assert title is None

    @pytest.mark.asyncio
    async def test_generate_title_no_user_message(self, summarizer, mock_repository):
        """Test title generation when no user message exists."""
        mock_repository.get_messages.return_value = [
            Message(
                id="msg_1",
                role=MessageRole.ASSISTANT,
                content="Hello, how can I help?",
            ),
        ]

        title = await summarizer.generate_title("conv_123")

        assert title is None

    @pytest.mark.asyncio
    async def test_summarize_conversation(self, summarizer, mock_repository, mock_llm_client):
        """Test summarizing a conversation."""
        mock_repository.get_messages.return_value = [
            Message(
                id="msg_1",
                role=MessageRole.USER,
                content="Hello",
            ),
            Message(
                id="msg_2",
                role=MessageRole.ASSISTANT,
                content="Hi there!",
            ),
        ] * 15  # 30 messages total
        mock_llm_client.generate.return_value = "A conversation about greeting each other."

        summary = await summarizer.summarize_conversation("conv_123")

        assert summary is not None
        assert len(summary) > 0
        mock_llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_without_llm_client(self, mock_repository):
        """Test that summarize returns None without LLM client."""
        summarizer = ConversationSummarizer(
            session=MagicMock(),
            llm_client=None,
        )
        summarizer._repository = mock_repository
        mock_repository.get_messages.return_value = [
            Message(id="msg_1", role=MessageRole.USER, content="Test"),
        ]

        summary = await summarizer.summarize_conversation("conv_123")

        assert summary is None

    @pytest.mark.asyncio
    async def test_should_summarize_true(self, summarizer, mock_repository):
        """Test should_summarize returns True when enough messages."""
        mock_repository.get_messages.return_value = [
            Message(id=f"msg_{i}", role=MessageRole.USER, content=f"Message {i}")
            for i in range(25)  # Over threshold of 20
        ]

        result = await summarizer.should_summarize("conv_123")

        assert result is True

    @pytest.mark.asyncio
    async def test_should_summarize_false(self, summarizer, mock_repository):
        """Test should_summarize returns False with few messages."""
        mock_repository.get_messages.return_value = [
            Message(id="msg_1", role=MessageRole.USER, content="Test"),
            Message(id="msg_2", role=MessageRole.ASSISTANT, content="Response"),
        ]

        result = await summarizer.should_summarize("conv_123")

        assert result is False

    @pytest.mark.asyncio
    async def test_auto_summarize_if_needed(self, summarizer, mock_repository, mock_llm_client):
        """Test auto summarization when conditions are met."""
        # Return enough messages to trigger summarization
        mock_repository.get_messages.return_value = [
            Message(id=f"msg_{i}", role=MessageRole.USER, content=f"Message {i}") for i in range(25)
        ]
        mock_llm_client.generate.return_value = "Auto-generated summary."

        summary = await summarizer.auto_summarize_if_needed("conv_123")

        assert summary is not None
        mock_llm_client.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_summarize_not_needed(self, summarizer, mock_repository, mock_llm_client):
        """Test auto summarization skips when not needed."""
        mock_repository.get_messages.return_value = [
            Message(id="msg_1", role=MessageRole.USER, content="Test"),
        ]

        summary = await summarizer.auto_summarize_if_needed("conv_123")

        assert summary is None
        mock_llm_client.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarize_handles_llm_error(self, summarizer, mock_repository, mock_llm_client):
        """Test that summarization handles LLM errors gracefully."""
        mock_repository.get_messages.return_value = [
            Message(id=f"msg_{i}", role=MessageRole.USER, content=f"Message {i}") for i in range(25)
        ]
        mock_llm_client.generate.side_effect = Exception("LLM Error")

        summary = await summarizer.summarize_conversation("conv_123")

        # Should return None instead of raising
        assert summary is None


class TestConversationSummarizerPromptTemplates:
    """Test prompt templates used by summarizer."""

    def test_summary_prompt_includes_messages(self, mock_repository=MagicMock()):
        """Test that summary prompt includes conversation messages."""
        summarizer = ConversationSummarizer(session=MagicMock())
        # Check that the prompt template contains placeholder
        assert "{messages}" in summarizer.SUMMARY_PROMPT

    def test_title_prompt_includes_first_message(self):
        """Test that title prompt includes first message placeholder."""
        summarizer = ConversationSummarizer(session=MagicMock())
        # Check that the prompt template contains placeholder
        assert "{first_message}" in summarizer.TITLE_PROMPT
