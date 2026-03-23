from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.memory.episodic import Episode
from me4brain.memory.semantic import Entity
from me4brain.retrieval.lightrag import LightRAG, LightRAGResult


@pytest.fixture
def mock_memories():
    with (
        patch("me4brain.retrieval.lightrag.get_episodic_memory") as mock_epi,
        patch("me4brain.retrieval.lightrag.get_semantic_memory") as mock_sem,
        patch("me4brain.retrieval.lightrag.get_embedding_service") as mock_emb,
        patch("me4brain.retrieval.lightrag.get_llm_client") as mock_llm,
    ):
        epi = AsyncMock()
        sem = AsyncMock()  # Changed to AsyncMock for async methods
        emb = MagicMock()
        llm = AsyncMock()

        mock_epi.return_value = epi
        mock_sem.return_value = sem
        mock_emb.return_value = emb
        mock_llm.return_value = llm

        yield epi, sem, emb, llm


@pytest.mark.asyncio
async def test_ingest_logic(mock_memories):
    epi, sem, emb, llm = mock_memories
    lightrag = LightRAG()

    # Mock LLM extraction
    llm_resp = MagicMock()
    llm_resp.choices = [MagicMock()]
    llm_resp.choices[
        0
    ].message.content = '{"entities": [{"id": "e1", "name": "E1", "type": "T1", "description": "D1"}], "relations": [{"source": "e1", "target": "e2", "type": "R1", "weight": 0.5}]}'
    llm.generate_response.return_value = llm_resp

    emb.embed_query.return_value = [0.1] * 1024

    await lightrag.ingest("test text", "t1", "u1")

    # Verify semantic calls
    assert sem.add_entity.call_count == 1
    assert sem.add_relation.call_count == 1

    # Verify episodic calls
    assert epi.add_episode.call_count == 1
    call_args = epi.add_episode.call_args
    assert isinstance(call_args.args[0], Episode)
    assert call_args.args[0].tenant_id == "t1"


@pytest.mark.asyncio
async def test_dual_retrieval_flow(mock_memories):
    epi, sem, emb, llm = mock_memories
    lightrag = LightRAG()

    # Mock Episodic Search (Local)
    mock_episode = MagicMock(spec=Episode)
    mock_episode.content = "local content"
    mock_episode.summary = "EntityName"
    epi.search_similar.return_value = [(mock_episode, 0.9)]

    # Mock Semantic PPR (Global)
    sem.personalized_pagerank.return_value = [("e1", 0.8)]
    mock_entity = MagicMock(spec=Entity)
    mock_entity.name = "EntityName"
    mock_entity.properties = {"description": "global content"}
    sem.get_entity.return_value = mock_entity

    emb.embed_query.return_value = [0.1] * 1024

    results = await lightrag.dual_retrieval("test query", "t1")

    assert len(results) > 0
    assert results[0].content in ["local content", "EntityName: global content"]

    # Check that PPR was called with seeds from vector search
    sem.personalized_pagerank.assert_called_once()
    args = sem.personalized_pagerank.call_args
    assert "EntityName" in args.kwargs["seed_entities"]


def test_rrf_fusion_logic():
    lightrag = LightRAG()

    # Setup results with overlapping content to test fusion
    local_res = [
        (MagicMock(content="C1"), 0.9),
        (MagicMock(content="C2"), 0.8),
    ]

    # Semantic results are list of dict
    e1 = MagicMock(spec=Entity)
    e1.name = "C1_Name"
    # Mapping in _rrf_fusion: key = f"{entity.name}: {entity.properties.get('description', '')}"
    # This might make it hard to 100% overlap, but let's test the ranking
    e1.properties = {"description": "desc"}

    graph_res = [{"entity": e1, "score": 0.9}]

    final = lightrag._rrf_fusion(local_res, graph_res, top_k=5)

    assert len(final) == 3  # C1, C2 from local, C1_Name from graph
    # Check scores are > 0
    for res in final:
        assert res.score > 0
        assert isinstance(res, LightRAGResult)
