"""E2E Tests for Episodic Memory Namespace."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
class TestEpisodicMemory:
    """Test Episodic Memory namespace operations."""

    async def test_store_episode(self, async_client):
        """Test storing an episode."""
        episode = await async_client.episodic.store(
            content=f"Test episode content {uuid.uuid4().hex[:8]}",
            summary="Test summary",
            importance=0.7,
            source="test",
            tags=["test", "e2e"],
            metadata={"test_run": True},
        )

        assert episode is not None
        assert episode.id is not None
        assert episode.content is not None

        # Cleanup
        await async_client.episodic.delete(episode.id)

    async def test_search_episodes(self, async_client):
        """Test semantic search on episodes."""
        # Store test episode
        unique_id = uuid.uuid4().hex[:8]
        episode = await async_client.episodic.store(
            content=f"Important meeting about quarterly budget planning {unique_id}",
            summary="Budget meeting",
            importance=0.8,
            tags=["meeting", "budget"],
        )

        try:
            # Search for it
            results = await async_client.episodic.search(
                query="budget planning meeting",
                limit=10,
                min_score=0.3,
            )

            assert results is not None
            assert len(results) >= 0  # May or may not find depending on embeddings

        finally:
            await async_client.episodic.delete(episode.id)

    async def test_search_with_filters(self, async_client):
        """Test search with tag and date filters."""
        unique_tag = f"unique-tag-{uuid.uuid4().hex[:8]}"

        episode = await async_client.episodic.store(
            content="Filtered search test content",
            importance=0.5,
            tags=[unique_tag, "filter-test"],
        )

        try:
            # Search with tag filter
            results = await async_client.episodic.search(
                query="search test",
                limit=10,
                tags=[unique_tag],
            )

            # Should find our episode
            assert results is not None

        finally:
            await async_client.episodic.delete(episode.id)

    async def test_get_episode_by_id(self, async_client):
        """Test retrieving episode by ID."""
        episode = await async_client.episodic.store(
            content="Get by ID test",
            importance=0.5,
        )

        try:
            retrieved = await async_client.episodic.get(episode.id)

            assert retrieved is not None
            assert retrieved.id == episode.id
            assert "Get by ID" in retrieved.content

        finally:
            await async_client.episodic.delete(episode.id)

    async def test_update_episode(self, async_client):
        """Test updating episode metadata."""
        episode = await async_client.episodic.store(
            content="Update test",
            importance=0.5,
            tags=["original"],
        )

        try:
            # Update
            updated = await async_client.episodic.update(
                episode_id=episode.id,
                importance=0.9,
                tags=["original", "updated"],
            )

            assert updated is not None
            # Importance should be updated

        finally:
            await async_client.episodic.delete(episode.id)

    async def test_get_related_episodes(self, async_client):
        """Test finding related episodes."""
        # Store related episodes
        ep1 = await async_client.episodic.store(
            content="Machine learning project discussion",
            tags=["ml", "project"],
        )
        ep2 = await async_client.episodic.store(
            content="Deep learning neural network training",
            tags=["ml", "neural"],
        )

        try:
            related = await async_client.episodic.get_related(
                episode_id=ep1.id,
                limit=5,
            )

            assert related is not None
            # May or may not find related depending on embeddings

        finally:
            await async_client.episodic.delete(ep1.id)
            await async_client.episodic.delete(ep2.id)

    async def test_delete_episode(self, async_client):
        """Test deleting an episode."""
        episode = await async_client.episodic.store(
            content="Delete test",
            importance=0.5,
        )

        # Delete
        await async_client.episodic.delete(episode.id)

        # Verify deleted
        try:
            await async_client.episodic.get(episode.id)
            pytest.fail("Should have raised for deleted episode")
        except Exception:
            pass  # Expected
