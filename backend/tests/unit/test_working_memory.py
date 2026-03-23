"""Test Working Memory Module."""

from unittest.mock import AsyncMock

import pytest

from me4brain.memory.working import WorkingMemory, get_working_memory


class TestWorkingMemory:
    """Test suite per Working Memory."""

    def test_stream_key_generation(self) -> None:
        """Verifica generazione chiavi Redis corretta."""
        key = WorkingMemory._stream_key("tenant1", "user1", "session1")
        assert key == "tenant:tenant1:user:user1:session:session1:stream"

    def test_graph_key_generation(self) -> None:
        """Verifica generazione chiavi grafo corretta."""
        key = WorkingMemory._graph_key("t1", "u1", "s1")
        assert key == "tenant:t1:user:u1:session:s1:graph"

    def test_session_id_generation(self) -> None:
        """Verifica generazione ID sessione."""
        sid = WorkingMemory._session_id("t1", "u1", "s1")
        assert sid == "t1:u1:s1"

    def test_session_graph_creation(self) -> None:
        """Verifica creazione grafo NetworkX."""
        wm = WorkingMemory()
        graph = wm.get_session_graph("t1", "u1", "s1")

        assert graph is not None
        assert graph.number_of_nodes() == 0
        assert graph.number_of_edges() == 0

    def test_add_entity_to_graph(self) -> None:
        """Verifica aggiunta entità al grafo."""
        wm = WorkingMemory()

        wm.add_entity(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            entity_id="person:1",
            entity_type="Person",
            label="Mario Rossi",
            properties={"email": "mario@example.com"},
        )

        graph = wm.get_session_graph("t1", "u1", "s1")
        assert graph.number_of_nodes() == 1
        assert "person:1" in graph.nodes
        assert graph.nodes["person:1"]["type"] == "Person"
        assert graph.nodes["person:1"]["label"] == "Mario Rossi"

    def test_add_relation_to_graph(self) -> None:
        """Verifica aggiunta relazione al grafo."""
        wm = WorkingMemory()

        # Aggiungi due entità
        wm.add_entity("t1", "u1", "s1", "person:1", "Person", "Mario")
        wm.add_entity("t1", "u1", "s1", "project:1", "Project", "Progetto X")

        # Aggiungi relazione
        wm.add_relation(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            source_id="person:1",
            target_id="project:1",
            relation_type="WORKS_ON",
        )

        graph = wm.get_session_graph("t1", "u1", "s1")
        assert graph.number_of_edges() == 1
        assert graph.has_edge("person:1", "project:1")

    def test_resolve_reference_with_focus(self) -> None:
        """Verifica risoluzione riferimenti con FOCUS_ON."""
        wm = WorkingMemory()

        # Setup: entità con FOCUS_ON
        wm.add_entity("t1", "u1", "s1", "project:1", "Project", "Progetto X")
        wm.add_entity("t1", "u1", "s1", "user:current", "User", "Current")

        wm.add_relation(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            source_id="user:current",
            target_id="project:1",
            relation_type="FOCUS_ON",
        )

        # Risolvi "il progetto"
        resolved = wm.resolve_reference(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            reference="il progetto",
            entity_type="Project",
        )

        assert resolved == "project:1"

    def test_resolve_reference_not_found(self) -> None:
        """Verifica risoluzione riferimenti quando non esiste corrispondenza."""
        wm = WorkingMemory()

        # Grafo vuoto
        resolved = wm.resolve_reference(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            reference="qualcosa",
            entity_type="NonExistent",
        )

        assert resolved is None

    def test_resolve_reference_fallback_by_type(self) -> None:
        """Verifica risoluzione fallback per tipo quando non c'è FOCUS_ON."""
        wm = WorkingMemory()

        # Aggiungi entità senza FOCUS_ON
        wm.add_entity("t1", "u1", "s1", "doc:1", "Document", "Doc A")
        wm.add_entity("t1", "u1", "s1", "doc:2", "Document", "Doc B")

        # Risolvi cercando per tipo
        resolved = wm.resolve_reference(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            reference="il documento",
            entity_type="Document",
        )

        # Deve trovare uno dei due
        assert resolved in ["doc:1", "doc:2"]

    def test_compression_roundtrip(self) -> None:
        """Verifica compressione/decompressione zlib+pickle."""
        wm = WorkingMemory()

        test_data = {
            "key": "value",
            "nested": {"a": 1, "b": [1, 2, 3]},
            "unicode": "Testo con accenti àèìòù",
        }

        compressed = wm._compress(test_data)
        decompressed = wm._decompress(compressed)

        assert decompressed == test_data
        # Verifica che la compressione riduca la dimensione
        import json

        original_size = len(json.dumps(test_data).encode())
        assert len(compressed) < original_size * 2  # Tolleranza per piccoli dati


class TestWorkingMemoryAsync:
    """Test asincroni per Working Memory."""

    @pytest.mark.asyncio
    async def test_add_message(self) -> None:
        """Verifica aggiunta messaggio (mock Redis)."""
        mock_redis = AsyncMock()
        mock_redis.xadd = AsyncMock(return_value=b"1234567890-0")
        mock_redis.expire = AsyncMock()

        wm = WorkingMemory(redis_client=mock_redis)

        msg_id = await wm.add_message(
            tenant_id="t1",
            user_id="u1",
            session_id="s1",
            role="human",
            content="Ciao, come stai?",
        )

        assert msg_id == "1234567890-0"
        mock_redis.xadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_messages(self) -> None:
        """Verifica recupero messaggi (mock Redis)."""
        mock_redis = AsyncMock()
        mock_redis.xrevrange = AsyncMock(
            return_value=[
                (
                    b"1234567890-1",
                    {
                        b"role": b"ai",
                        b"content": b"Sto bene!",
                        b"timestamp": b"2026-01-27T12:00:00+00:00",
                    },
                ),
                (
                    b"1234567890-0",
                    {
                        b"role": b"human",
                        b"content": b"Ciao",
                        b"timestamp": b"2026-01-27T11:59:00+00:00",
                    },
                ),
            ]
        )

        wm = WorkingMemory(redis_client=mock_redis)

        messages = await wm.get_messages("t1", "u1", "s1", count=10)

        assert len(messages) == 2
        # Verifica ordine cronologico (reversed)
        assert messages[0]["role"] == "human"
        assert messages[1]["role"] == "ai"

    @pytest.mark.asyncio
    async def test_clear_session(self) -> None:
        """Verifica pulizia sessione completa."""
        mock_redis = AsyncMock()
        mock_redis.delete = AsyncMock()

        wm = WorkingMemory(redis_client=mock_redis)

        # Setup: aggiungi grafo in memoria
        wm.add_entity("t1", "u1", "s1", "entity:1", "Type", "Label")
        assert "t1:u1:s1" in wm._session_graphs

        await wm.clear_session("t1", "u1", "s1")

        # Verifica che delete sia stato chiamato
        mock_redis.delete.assert_called_once()
        # Verifica che il grafo sia stato rimosso dalla memoria
        assert "t1:u1:s1" not in wm._session_graphs

    @pytest.mark.asyncio
    async def test_persist_graph(self) -> None:
        """Verifica persistenza grafo su Redis."""
        mock_redis = AsyncMock()
        mock_redis.set = AsyncMock()

        wm = WorkingMemory(redis_client=mock_redis)

        # Setup: aggiungi entità al grafo
        wm.add_entity("t1", "u1", "s1", "entity:1", "Type", "Label")
        wm.add_entity("t1", "u1", "s1", "entity:2", "Type", "Label2")

        await wm.persist_graph("t1", "u1", "s1")

        mock_redis.set.assert_called_once()
        # Verifica che la chiave corretta sia usata
        call_args = mock_redis.set.call_args
        assert "graph" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_load_graph(self) -> None:
        """Verifica caricamento grafo da Redis."""
        import networkx as nx

        # Prepara dati grafo compressi
        wm_temp = WorkingMemory()
        wm_temp.add_entity("t1", "u1", "s1", "entity:1", "Type", "Label")
        graph_data = nx.node_link_data(wm_temp.get_session_graph("t1", "u1", "s1"))
        compressed = wm_temp._compress(graph_data)

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=compressed)

        wm = WorkingMemory(redis_client=mock_redis)

        result = await wm.load_graph("t1", "u1", "s1")

        assert result is not None
        assert result.number_of_nodes() == 1
        assert "entity:1" in result.nodes

    @pytest.mark.asyncio
    async def test_load_graph_not_found(self) -> None:
        """Verifica che load_graph ritorni None se non esiste."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        wm = WorkingMemory(redis_client=mock_redis)

        result = await wm.load_graph("t1", "u1", "s1")

        assert result is None

    @pytest.mark.asyncio
    async def test_close(self) -> None:
        """Verifica chiusura connessione Redis."""
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()

        wm = WorkingMemory(redis_client=mock_redis)

        await wm.close()

        mock_redis.close.assert_called_once()


class TestWorkingMemorySingleton:
    """Test per singleton Working Memory."""

    def test_get_working_memory_singleton(self) -> None:
        """Verifica che get_working_memory ritorni singleton."""
        import me4brain.memory.working as working_module

        # Reset
        working_module._working_memory = None

        wm1 = get_working_memory()
        wm2 = get_working_memory()

        assert wm1 is wm2

        # Cleanup
        working_module._working_memory = None
