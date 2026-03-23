from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from me4brain.api.main import create_app
from me4brain.api.middleware.auth import AuthenticatedUser
from me4brain.memory.episodic import Episode
from me4brain.memory.semantic import Entity

# Mock user for authentication
MOCK_USER = AuthenticatedUser(user_id="test_user", tenant_id="test_tenant", roles=["user"])


@pytest.fixture
def client():
    app = create_app()
    # Override dependency for authentication
    from me4brain.api.routes.memory import get_current_user

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER
    return TestClient(app)


@pytest.fixture
def mock_services():
    with (
        patch("me4brain.api.routes.memory.get_episodic_memory") as mock_epi,
        patch("me4brain.api.routes.memory.get_semantic_memory") as mock_sem,
        patch("me4brain.api.routes.memory.get_embedding_service") as mock_emb,
        patch("me4brain.api.routes.memory.run_cognitive_cycle") as mock_cycle,
    ):
        epi = AsyncMock()
        sem = AsyncMock()  # Changed to AsyncMock for async methods
        emb = MagicMock()

        mock_epi.return_value = epi
        mock_sem.return_value = sem
        mock_emb.return_value = emb

        yield epi, sem, emb, mock_cycle


def test_store_episode(client, mock_services):
    epi, sem, emb, _ = mock_services
    emb.embed_document.return_value = [0.1] * 1024
    epi.add_episode.return_value = "epi_123"

    response = client.post(
        "/v1/memory/episodes",
        json={
            "content": "Test episode content",
            "source": "unit_test",
            "tags": ["test"],
            "metadata": {"importance": 0.8},
        },
    )

    assert response.status_code == 201
    assert response.json()["id"] == "epi_123"
    epi.add_episode.assert_called_once()
    emb.embed_document.assert_called_once_with("Test episode content")


def test_get_episode(client, mock_services):
    epi, _, _, _ = mock_services
    mock_epi = Episode(
        id="epi_123",
        tenant_id="test_tenant",
        user_id="test_user",
        content="Hello world",
        source="test",
    )
    epi.get_by_id.return_value = mock_epi

    response = client.get("/v1/memory/episodes/epi_123")

    assert response.status_code == 200
    assert response.json()["content"] == "Hello world"
    epi.get_by_id.assert_called_once_with("me4brain_core", "epi_123")  # dev mode tenant


def test_get_episode_not_found(client, mock_services):
    epi, _, _, _ = mock_services
    epi.get_by_id.return_value = None

    response = client.get("/v1/memory/episodes/missing")
    assert response.status_code == 404


def test_delete_episode(client, mock_services):
    epi, _, _, _ = mock_services
    epi.delete_episode.return_value = True

    response = client.delete("/v1/memory/episodes/epi_123")
    assert response.status_code == 204
    epi.delete_episode.assert_called_once_with("me4brain_core", "epi_123")  # dev mode tenant


def test_store_entity(client, mock_services):
    _, sem, _, _ = mock_services
    sem.add_entity.return_value = "ent_456"

    response = client.post(
        "/v1/memory/entities",
        json={"name": "Arduino", "type": "Hardware", "properties": {"version": "Uno"}},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "ent_456"
    sem.add_entity.assert_called_once()


def test_get_entity(client, mock_services):
    _, sem, _, _ = mock_services
    mock_ent = Entity(
        id="ent_456",
        type="Hardware",
        name="Arduino",
        tenant_id="test_tenant",
        properties={"version": "Uno"},
    )
    sem.get_entity.return_value = mock_ent

    response = client.get("/v1/memory/entities/ent_456")
    assert response.status_code == 200
    assert response.json()["name"] == "Arduino"


def test_store_relation(client, mock_services):
    _, sem, _, _ = mock_services

    response = client.post(
        "/v1/memory/relations",
        json={"source_id": "e1", "target_id": "e2", "type": "RELATES_TO", "weight": 0.5},
    )

    assert response.status_code == 201
    sem.add_relation.assert_called_once()


@pytest.mark.asyncio
async def test_search_memory(client, mock_services):
    epi, sem, emb, _ = mock_services
    emb.embed_query.return_value = [0.1] * 1024

    mock_epi = Episode(id="e1", tenant_id="t1", user_id="u1", content="epi content")
    epi.search_similar.return_value = [(mock_epi, 0.9)]

    # Mocking working memory for semantic seed
    with patch("me4brain.api.routes.memory.get_working_memory") as mock_wk:
        wk = MagicMock()
        mock_wk.return_value = wk
        wk.get_session_graph.return_value = MagicMock()  # Empty graph

        response = client.post(
            "/v1/memory/search", json={"query": "test query", "sources": ["episodic"]}
        )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["source"] == "episodic"


@pytest.mark.asyncio
async def test_cognitive_query(client, mock_services):
    _, _, _, cycle = mock_services
    cycle.return_value = {
        "final_response": "The answer is 42",
        "confidence": 1.0,
        "sources_used": ["episodic"],
        "thread_id": "thread_abc",
    }

    response = client.post("/v1/memory/query", json={"query": "What is the meaning of life?"})

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "The answer is 42"
    assert data["thread_id"] == "thread_abc"
