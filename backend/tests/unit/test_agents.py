"""Unit tests for Agent-to-Agent module (M3)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.core.agents.types import (
    AgentMessage,
    AgentProfile,
    AgentResponse,
    AgentStatus,
    AgentType,
    HandoffRequest,
    MessageFlag,
    RegisterAgentRequest,
    SendMessageRequest,
    TaskContext,
)
from me4brain.core.agents.registry import AgentRegistry
from me4brain.core.agents.messenger import AgentMessenger
from me4brain.core.agents.supervisor import SupervisorAgent
from me4brain.core.agents.context import SharedContext


# --- Types Tests ---


class TestAgentTypes:
    """Test per modelli Pydantic agents."""

    def test_agent_type_enum(self):
        """Test enum valori."""
        assert AgentType.SUPERVISOR.value == "supervisor"
        assert AgentType.SPECIALIST.value == "specialist"
        assert AgentType.WORKER.value == "worker"

    def test_agent_status_enum(self):
        """Test status enum."""
        assert AgentStatus.IDLE.value == "idle"
        assert AgentStatus.BUSY.value == "busy"
        assert AgentStatus.OFFLINE.value == "offline"

    def test_agent_profile_creation(self):
        """Test creazione AgentProfile."""
        profile = AgentProfile(
            id="agent-123",
            name="Research Agent",
            type=AgentType.SPECIALIST,
            capabilities=["research", "analysis"],
        )
        assert profile.id == "agent-123"
        assert profile.status == AgentStatus.IDLE
        assert len(profile.capabilities) == 2

    def test_agent_profile_success_rate(self):
        """Test calcolo success rate."""
        profile = AgentProfile(
            id="test",
            name="Test",
            tasks_completed=8,
            tasks_failed=2,
        )
        assert profile.success_rate == 0.8

    def test_agent_profile_success_rate_zero(self):
        """Test success rate senza task."""
        profile = AgentProfile(id="test", name="Test")
        assert profile.success_rate == 1.0

    def test_agent_message_creation(self):
        """Test creazione AgentMessage."""
        msg = AgentMessage(
            id="msg-123",
            from_agent="agent-1",
            to_agent="agent-2",
            content="Hello!",
            context={"key": "value"},
        )
        assert msg.from_agent == "agent-1"
        assert msg.acknowledged is False

    def test_message_flag_enum(self):
        """Test message flags."""
        assert MessageFlag.REPLY_SKIP.value == "REPLY_SKIP"
        assert MessageFlag.PRIORITY_HIGH.value == "PRIORITY_HIGH"

    def test_handoff_request_creation(self):
        """Test creazione HandoffRequest."""
        req = HandoffRequest(
            id="handoff-123",
            from_agent="main",
            to_agent="research",
            task="Analyze this document",
            priority=1,
        )
        assert req.status == "pending"
        assert req.priority == 1

    def test_agent_response_from_profile(self):
        """Test conversione AgentResponse."""
        profile = AgentProfile(
            id="agent-123",
            name="Test Agent",
            type=AgentType.WORKER,
            capabilities=["coding"],
            status=AgentStatus.IDLE,
            tasks_completed=5,
        )
        response = AgentResponse.from_profile(profile)
        assert response.id == "agent-123"
        assert response.type == "worker"
        assert response.success_rate == 1.0


# --- Registry Tests ---


class TestAgentRegistry:
    """Test per AgentRegistry."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = AsyncMock()
        redis.set = AsyncMock()
        redis.get = AsyncMock()
        redis.sadd = AsyncMock()
        redis.srem = AsyncMock()
        redis.smembers = AsyncMock(return_value=set())
        redis.delete = AsyncMock()
        redis.exists = AsyncMock(return_value=True)
        return redis

    @pytest.mark.asyncio
    async def test_register_agent(self, mock_redis):
        """Test registrazione agente."""
        registry = AgentRegistry(mock_redis)

        request = RegisterAgentRequest(
            name="Test Agent",
            type=AgentType.WORKER,
            capabilities=["test"],
        )

        profile = await registry.register(request, "agent-123")

        assert profile.id == "agent-123"
        assert profile.name == "Test Agent"
        mock_redis.set.assert_called_once()
        mock_redis.sadd.assert_called()

    @pytest.mark.asyncio
    async def test_get_agent(self, mock_redis):
        """Test recupero agente."""
        registry = AgentRegistry(mock_redis)

        profile = AgentProfile(
            id="agent-123",
            name="Test",
            type=AgentType.WORKER,
        )
        mock_redis.get.return_value = profile.model_dump_json()

        result = await registry.get("agent-123")

        assert result is not None
        assert result.id == "agent-123"

    @pytest.mark.asyncio
    async def test_get_agent_not_found(self, mock_redis):
        """Test recupero agente inesistente."""
        registry = AgentRegistry(mock_redis)
        mock_redis.get.return_value = None

        result = await registry.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_unregister_agent(self, mock_redis):
        """Test rimozione agente."""
        registry = AgentRegistry(mock_redis)

        profile = AgentProfile(id="agent-123", name="Test")
        mock_redis.get.return_value = profile.model_dump_json()

        result = await registry.unregister("agent-123")

        assert result is True
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_agents(self, mock_redis):
        """Test lista agenti."""
        registry = AgentRegistry(mock_redis)

        profile1 = AgentProfile(id="agent-1", name="Agent 1")
        profile2 = AgentProfile(id="agent-2", name="Agent 2")

        mock_redis.smembers.return_value = {"agent-1", "agent-2"}
        mock_redis.get.side_effect = [
            profile1.model_dump_json(),
            profile2.model_dump_json(),
        ]

        agents = await registry.list_agents()
        assert len(agents) == 2


# --- Messenger Tests ---


class TestAgentMessenger:
    """Test per AgentMessenger."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = AsyncMock()
        redis.xgroup_create = AsyncMock()
        redis.xadd = AsyncMock(return_value="1234567890-0")
        redis.xreadgroup = AsyncMock(return_value=[])
        redis.xrevrange = AsyncMock(return_value=[])
        redis.xack = AsyncMock()
        redis.xpending = AsyncMock(return_value={})
        return redis

    @pytest.mark.asyncio
    async def test_send_message(self, mock_redis):
        """Test invio messaggio."""
        messenger = AgentMessenger(mock_redis)

        msg = AgentMessage(
            id="msg-123",
            from_agent="agent-1",
            to_agent="agent-2",
            content="Hello!",
        )

        redis_id = await messenger.send(msg)

        assert redis_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_messages(self, mock_redis):
        """Test ricezione messaggi."""
        messenger = AgentMessenger(mock_redis)
        messenger._stream_created.add("me4brain:agents:stream:agent-1")

        mock_redis.xreadgroup.return_value = []

        messages = await messenger.receive("agent-1", count=10)

        assert messages == []

    @pytest.mark.asyncio
    async def test_history(self, mock_redis):
        """Test storico messaggi."""
        messenger = AgentMessenger(mock_redis)

        mock_redis.xrevrange.return_value = []

        messages = await messenger.history("agent-1", limit=50)

        assert messages == []


# --- Supervisor Tests ---


class TestSupervisorAgent:
    """Test per SupervisorAgent."""

    @pytest.fixture
    def mock_registry(self):
        """Mock AgentRegistry."""
        registry = AsyncMock()
        registry.list_agents = AsyncMock(return_value=[])
        registry.get = AsyncMock()
        registry.find_best_agent = AsyncMock()
        registry.update_status = AsyncMock()
        registry.record_task_completion = AsyncMock()
        return registry

    @pytest.fixture
    def mock_messenger(self):
        """Mock AgentMessenger."""
        messenger = AsyncMock()
        messenger.send = AsyncMock(return_value="1234-0")
        return messenger

    def test_infer_capability_research(self):
        """Test inferenza capability research."""
        supervisor = SupervisorAgent()
        cap = supervisor._infer_capability("Please search for information about AI")
        assert cap == "research"

    def test_infer_capability_coding(self):
        """Test inferenza capability coding."""
        supervisor = SupervisorAgent()
        cap = supervisor._infer_capability("Can you fix this code bug?")
        assert cap == "coding"

    def test_infer_capability_none(self):
        """Test inferenza senza match."""
        supervisor = SupervisorAgent()
        cap = supervisor._infer_capability("Random text without keywords")
        assert cap is None

    @pytest.mark.asyncio
    async def test_route_with_capability(self, mock_registry):
        """Test routing con capability."""
        profile = AgentProfile(
            id="research-agent",
            name="Research",
            capabilities=["research"],
        )
        mock_registry.find_best_agent.return_value = profile

        supervisor = SupervisorAgent(registry=mock_registry)

        result = await supervisor.route(
            task="Search for documents",
            context={},
            required_capability="research",
        )

        assert result is not None
        assert result.id == "research-agent"

    @pytest.mark.asyncio
    async def test_route_no_agent(self, mock_registry):
        """Test routing senza agenti disponibili."""
        mock_registry.find_best_agent.return_value = None
        mock_registry.list_agents.return_value = []

        supervisor = SupervisorAgent(registry=mock_registry)

        result = await supervisor.route(
            task="Do something",
            context={},
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_monitor(self, mock_registry):
        """Test monitor status."""
        profiles = [
            AgentProfile(
                id="agent-1",
                name="Agent 1",
                status=AgentStatus.IDLE,
            ),
            AgentProfile(
                id="agent-2",
                name="Agent 2",
                status=AgentStatus.BUSY,
                current_task="Doing work",
            ),
        ]
        mock_registry.list_agents.return_value = profiles

        supervisor = SupervisorAgent(registry=mock_registry)

        status = await supervisor.monitor()

        assert "agent-1" in status
        assert "agent-2" in status
        assert status["agent-2"]["current_task"] == "Doing work"


# --- SharedContext Tests ---


class TestSharedContext:
    """Test per SharedContext."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = AsyncMock()
        redis.hset = AsyncMock()
        redis.hget = AsyncMock()
        redis.hgetall = AsyncMock(return_value={})
        redis.hdel = AsyncMock()
        redis.delete = AsyncMock()
        redis.expire = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_set_value(self, mock_redis):
        """Test set valore."""
        ctx = SharedContext(mock_redis)

        await ctx.set("task-123", "key1", "value1")

        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_dict_value(self, mock_redis):
        """Test set valore dict (serializzato)."""
        ctx = SharedContext(mock_redis)

        await ctx.set("task-123", "data", {"nested": "value"})

        mock_redis.hset.assert_called_once()
        # Verifica che sia stato serializzato
        call_args = mock_redis.hset.call_args
        assert "nested" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_get_value(self, mock_redis):
        """Test get valore."""
        ctx = SharedContext(mock_redis)
        mock_redis.hget.return_value = '"test_value"'

        result = await ctx.get("task-123", "key1")

        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_value_not_found(self, mock_redis):
        """Test get valore inesistente."""
        ctx = SharedContext(mock_redis)
        mock_redis.hget.return_value = None

        result = await ctx.get("task-123", "nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_all(self, mock_redis):
        """Test get tutto il context."""
        ctx = SharedContext(mock_redis)
        mock_redis.hgetall.return_value = {
            "key1": '"value1"',
            "key2": '{"nested": "data"}',
        }

        result = await ctx.get_all("task-123")

        assert "key1" in result
        assert result["key2"]["nested"] == "data"

    @pytest.mark.asyncio
    async def test_delete_key(self, mock_redis):
        """Test delete singola chiave."""
        ctx = SharedContext(mock_redis)

        await ctx.delete("task-123", "key1")

        mock_redis.hdel.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_all(self, mock_redis):
        """Test delete tutto il context."""
        ctx = SharedContext(mock_redis)

        await ctx.delete("task-123")

        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_extend_ttl(self, mock_redis):
        """Test estensione TTL."""
        ctx = SharedContext(mock_redis, ttl_seconds=1800)

        await ctx.extend_ttl("task-123", seconds=7200)

        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == 7200
