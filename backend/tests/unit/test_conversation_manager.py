# Phase 7: Conversation Manager Tests
# Tests for ConversationManager

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from me4brain.engine.conversation_manager import ConversationManager
from me4brain.models.conversation import (
    Conversation,
    ConversationSummary,
    Message,
    MessageRole,
)


class TestConversationManager:
    """Test suite for ConversationManager."""

    @pytest.fixture
    def mock_repository(self):
        """Create mock ConversationRepository."""
        mock = MagicMock()
        mock.create_conversation = AsyncMock()
        mock.get_conversation = AsyncMock()
        mock.list_conversations = AsyncMock()
        mock.add_message = AsyncMock()
        mock.get_messages = AsyncMock()
        mock.update_conversation = AsyncMock()
        mock.archive_conversation = AsyncMock()
        mock.delete_conversation = AsyncMock()
        mock.get_conversation_context = AsyncMock()
        return mock

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_session, mock_repository):
        """Create ConversationManager with mocked dependencies."""
        manager = ConversationManager(mock_session)
        manager._repository = mock_repository
        return manager

    @pytest.mark.asyncio
    async def test_start_conversation(self, manager, mock_repository):
        """Test starting a new conversation."""
        mock_conversation = Conversation(
            id="conv_new",
            user_id="user_123",
            title="New Chat",
        )
        mock_repository.create_conversation.return_value = mock_conversation

        result = await manager.start_conversation(
            user_id="user_123",
            title="New Chat",
        )

        assert result.id == "conv_new"
        mock_repository.create_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_user_message(self, manager, mock_repository):
        """Test adding a user message."""
        mock_message = Message(
            id="msg_new",
            role=MessageRole.USER,
            content="Hello!",
        )
        mock_repository.add_message.return_value = mock_message

        result = await manager.add_user_message(
            conversation_id="conv_123",
            content="Hello!",
        )

        assert result.id == "msg_new"
        assert result.role == MessageRole.USER
        mock_repository.add_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_assistant_message(self, manager, mock_repository):
        """Test adding an assistant message."""
        mock_message = Message(
            id="msg_resp",
            role=MessageRole.ASSISTANT,
            content="Hi there!",
        )
        mock_repository.add_message.return_value = mock_message

        result = await manager.add_assistant_message(
            conversation_id="conv_123",
            content="Hi there!",
        )

        assert result.role == MessageRole.ASSISTANT
        mock_repository.add_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_conversation(self, manager, mock_repository):
        """Test getting a conversation."""
        mock_conversation = Conversation(
            id="conv_123",
            user_id="user_123",
            title="Test",
        )
        mock_repository.get_conversation.return_value = mock_conversation

        result = await manager.get_conversation("conv_123", "user_123")

        assert result is not None
        assert result.id == "conv_123"
        mock_repository.get_conversation.assert_called_once_with("conv_123", "user_123")

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, manager, mock_repository):
        """Test getting a non-existent conversation."""
        mock_repository.get_conversation.return_value = None

        result = await manager.get_conversation("conv_missing", "user_123")

        assert result is None

    @pytest.mark.asyncio
    async def test_list_conversations(self, manager, mock_repository):
        """Test listing conversations."""
        mock_summaries = [
            ConversationSummary(
                id="conv_1",
                title="First",
                updated_at=datetime.utcnow(),
                message_count=5,
            ),
            ConversationSummary(
                id="conv_2",
                title="Second",
                updated_at=datetime.utcnow(),
                message_count=10,
            ),
        ]
        mock_repository.list_conversations.return_value = (mock_summaries, 2)

        convs, total = await manager.list_conversations("user_123", limit=20)

        assert len(convs) == 2
        assert total == 2
        mock_repository.list_conversations.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_conversation(self, manager, mock_repository):
        """Test archiving a conversation."""
        mock_repository.archive_conversation.return_value = True

        result = await manager.archive_conversation("conv_123", "user_123")

        assert result is True
        mock_repository.archive_conversation.assert_called_once_with("conv_123", "user_123")

    @pytest.mark.asyncio
    async def test_delete_conversation(self, manager, mock_repository):
        """Test deleting a conversation."""
        mock_repository.delete_conversation.return_value = True

        result = await manager.delete_conversation("conv_123", "user_123")

        assert result is True
        mock_repository.delete_conversation.assert_called_once_with("conv_123", "user_123")

    @pytest.mark.asyncio
    async def test_get_context(self, manager, mock_repository):
        """Test getting conversation context."""
        mock_repository.get_conversation_context.return_value = (
            "Previous: Hello\nCurrent: How are you?"
        )

        result = await manager.get_context("conv_123", max_tokens=2000)

        assert result is not None
        assert "Previous" in result
        mock_repository.get_conversation_context.assert_called_once_with("conv_123", 2000)

    @pytest.mark.asyncio
    async def test_get_context_no_conversation(self, manager, mock_repository):
        """Test getting context for non-existent conversation."""
        mock_repository.get_conversation_context.return_value = None

        result = await manager.get_context("conv_missing")

        assert result is None


class TestConversationManagerWithLLM:
    """Test ConversationManager with LLM client for classification."""

    @pytest.fixture
    def mock_llm_client(self):
        """Create mock LLM client."""
        mock = MagicMock()
        mock.generate = AsyncMock(return_value="sports_nba")
        return mock

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        mock = MagicMock()
        mock.get_conversation_context = AsyncMock(return_value="Previous context")
        return mock

    @pytest.fixture
    def mock_classifier(self):
        """Create mock domain classifier."""
        return AsyncMock(return_value="sports_nba")

    @pytest.mark.asyncio
    async def test_classify_with_context(self, mock_repository, mock_classifier):
        """Test classification with conversation context."""
        manager = ConversationManager(MagicMock(), llm_client=MagicMock())
        manager._repository = mock_repository

        enriched, domain = await manager.classify_with_context(
            conversation_id="conv_123",
            query="Lakers game tonight",
            domain_classifier=mock_classifier,
        )

        assert domain == "sports_nba"
        assert enriched is not None
        assert "Previous context" in enriched
        assert "Lakers game tonight" in enriched

    @pytest.mark.asyncio
    async def test_classify_without_context(self, mock_repository, mock_classifier):
        """Test classification without conversation context."""
        manager = ConversationManager(MagicMock(), llm_client=MagicMock())
        manager._repository = mock_repository
        mock_repository.get_conversation_context.return_value = None

        enriched, domain = await manager.classify_with_context(
            conversation_id=None,
            query="Simple query",
            domain_classifier=mock_classifier,
        )

        assert domain == "sports_nba"
        assert enriched == "Simple query"

    @pytest.mark.asyncio
    async def test_classify_no_classifier(self, mock_repository):
        """Test that query is still enriched without classifier."""
        manager = ConversationManager(MagicMock(), llm_client=MagicMock())
        manager._repository = mock_repository

        enriched, domain = await manager.classify_with_context(
            conversation_id="conv_123",
            query="Query without classifier",
            domain_classifier=None,
        )

        assert enriched is not None
        assert domain is None
