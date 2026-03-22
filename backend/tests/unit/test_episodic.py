import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from me4brain.memory.episodic import EpisodicMemory, Episode
from qdrant_client.models import PointStruct, ScoredPoint


@pytest.fixture
def mock_qdrant_client():
    client = AsyncMock()
    # Mock collections list response
    mock_collection = MagicMock()
    mock_collection.name = "memories"
    collections_resp = MagicMock()
    collections_resp.collections = [mock_collection]
    client.get_collections.return_value = collections_resp
    return client


@pytest.fixture
async def episodic_memory(mock_qdrant_client):
    memory = EpisodicMemory(client=mock_qdrant_client)
    return memory


@pytest.mark.asyncio
async def test_initialize_existing_collection(episodic_memory, mock_qdrant_client):
    """Test initialization when collection already exists."""
    await episodic_memory.initialize()

    # Should check for existence
    mock_qdrant_client.get_collections.assert_called_once()
    # Should NOT create new collection
    mock_qdrant_client.create_collection.assert_not_called()


@pytest.mark.asyncio
async def test_initialize_new_collection(mock_qdrant_client):
    """Test initialization when collection does NOT exist."""
    # Setup mock to return empty collections
    empty_resp = MagicMock()
    empty_resp.collections = []
    mock_qdrant_client.get_collections.return_value = empty_resp

    memory = EpisodicMemory(client=mock_qdrant_client)
    await memory.initialize()

    # Should create collection and indexes
    mock_qdrant_client.create_collection.assert_called_once()
    assert mock_qdrant_client.create_payload_index.call_count == 3  # tenant, user, time


@pytest.mark.asyncio
async def test_add_episode(episodic_memory, mock_qdrant_client):
    """Test adding an episode."""
    episode = Episode(
        tenant_id="t1",
        user_id="u1",
        content="test content",
        event_time=datetime(2024, 1, 1, tzinfo=UTC),
    )
    embedding = [0.1] * 1024

    episode_id = await episodic_memory.add_episode(episode, embedding)

    assert episode_id == episode.id
    mock_qdrant_client.upsert.assert_called_once()

    # Verify payload structure
    call_args = mock_qdrant_client.upsert.call_args
    assert call_args.kwargs["collection_name"] == "memories"
    points = call_args.kwargs["points"]
    assert len(points) == 1
    assert points[0].payload["tenant_id"] == "t1"
    assert points[0].payload["content"] == "test content"


@pytest.mark.asyncio
async def test_search_similar(episodic_memory, mock_qdrant_client):
    """Test searching for similar episodes."""
    # Setup mock response
    mock_point = ScoredPoint(
        id="test-id",
        version=1,
        score=0.9,
        payload={
            "tenant_id": "t1",
            "user_id": "u1",
            "content": "found content",
            "event_time": datetime.now(UTC).isoformat(),
            "ingestion_time": datetime.now(UTC).isoformat(),
        },
        vector=None,
    )
    response = MagicMock()
    response.points = [mock_point]
    mock_qdrant_client.query_points.return_value = response

    results = await episodic_memory.search_similar(
        tenant_id="t1", user_id="u1", query_embedding=[0.1] * 1024
    )

    assert len(results) == 1
    episode, score = results[0]
    assert episode.content == "found content"
    assert score <= 0.9  # Could be less due to time decay logic

    # Verify filter construction
    call_args = mock_qdrant_client.query_points.call_args
    query_filter = call_args.kwargs["query_filter"]
    assert len(query_filter.must) == 2  # tenant_id + user_id logic


@pytest.mark.asyncio
async def test_forget_user(episodic_memory, mock_qdrant_client):
    """Test GDPR forget user functionality."""
    # Mock count response
    count_resp = MagicMock()
    count_resp.count = 5
    mock_qdrant_client.count.return_value = count_resp

    deleted = await episodic_memory.forget_user("t1", "u1")

    assert deleted == 5
    mock_qdrant_client.delete.assert_called_once()
