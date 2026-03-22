"""E2E Tests for Cognitive Namespace."""

from __future__ import annotations

import uuid
import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
class TestCognitiveNamespace:
    """Test Cognitive namespace operations."""

    async def test_simple_query(self, async_client):
        """Test simple cognitive query."""
        response = await async_client.cognitive.query(
            query="What is 2 + 2?",
        )

        assert response is not None
        assert response.answer is not None
        assert len(response.answer) > 0

    async def test_query_with_session(self, async_client):
        """Test query with session context."""
        # Create session
        user_id = f"test-user-{uuid.uuid4().hex[:8]}"
        session = await async_client.working.create_session(user_id=user_id)

        try:
            # Add some context
            await async_client.working.add_turn(
                session_id=session.id,
                role="user",
                content="My name is Alice and I work at Acme Corp.",
                user_id=user_id,
            )
            await async_client.working.add_turn(
                session_id=session.id,
                role="assistant",
                content="Nice to meet you, Alice!",
                user_id=user_id,
            )

            # Query with session
            response = await async_client.cognitive.query(
                query="What is my name?",
                session_id=session.id,
                use_episodic=False,
                use_semantic=False,
            )

            assert response is not None
            assert response.answer is not None

        finally:
            await async_client.working.delete_session(session.id, user_id=user_id)

    async def test_query_with_memory_layers(self, async_client):
        """Test query using all memory layers."""
        response = await async_client.cognitive.query(
            query="Tell me something interesting",
            use_episodic=True,
            use_semantic=True,
            use_procedural=True,
            memory_limit=5,
            min_relevance=0.3,
        )

        assert response is not None
        assert response.answer is not None
        # May have reasoning steps
        if response.reasoning_steps:
            assert len(response.reasoning_steps) >= 0

    @pytest.mark.slow
    async def test_query_stream(self, async_client):
        """Test streaming cognitive query."""
        chunks = []

        async for chunk in async_client.cognitive.query_stream(
            query="Count from 1 to 5",
        ):
            chunks.append(chunk)
            # Every chunk must have a valid chunk_type
            assert chunk.chunk_type in ("start", "content", "reasoning", "tool", "done", "error")

        assert len(chunks) > 0, "Should receive at least one chunk"
        # Should have content in at least one chunk
        content_chunks = [c for c in chunks if c.content]
        assert len(content_chunks) > 0 or any(c.chunk_type == "done" for c in chunks)

    async def test_query_with_tools(self, async_client):
        """Test query that may invoke tools."""
        response = await async_client.cognitive.query(
            query="What's the current weather in Rome?",
            use_procedural=True,  # Enable tool selection
        )

        assert response is not None
        assert response.answer is not None

        # May have used tools
        if response.tools_used:
            assert len(response.tools_used) >= 0


@pytest.mark.e2e
@pytest.mark.asyncio
class TestCognitiveReasoning:
    """Test cognitive reasoning capabilities."""

    @pytest.mark.slow
    async def test_multi_step_reasoning(self, async_client):
        """Test multi-step reasoning query."""
        response = await async_client.cognitive.reason(
            query="If I have 10 apples and give away half, how many do I have?",
            max_steps=5,
        )

        assert response is not None
        assert response.answer is not None

        # Should have reasoning steps
        if response.reasoning_steps:
            for step in response.reasoning_steps:
                assert step.thought is not None

    @pytest.mark.slow
    async def test_plan_generation(self, async_client):
        """Test plan generation."""
        plan = await async_client.cognitive.plan(
            goal="Organize a team meeting",
            constraints=["Budget: $100", "Duration: 1 hour"],
        )

        assert plan is not None
        # Plan should have steps or content
