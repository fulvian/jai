"""Test script per l'Orchestratore Cognitivo.

Esegue un ciclo completo del grafo LangGraph, mockando i layer di memoria
per testare isolatamente la logica di flusso e la generazione finale con NanoGPT.
"""

import asyncio
import sys
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from dotenv import load_dotenv

# Configura path
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent / "src"))

from me4brain.core.orchestrator import run_cognitive_cycle
from me4brain.utils.logging import configure_logging

load_dotenv()
configure_logging()


async def main():
    print("🚀 Test Orchestrator Cognitivo (Mocked Memories)...")

    # Mock delle dipendenze esterne
    with (
        patch("me4brain.core.orchestrator.get_embedding_service") as mock_embed,
        patch("me4brain.core.orchestrator.get_semantic_router") as mock_router,
        patch("me4brain.core.orchestrator.get_episodic_memory") as mock_episodic,
        patch("me4brain.core.orchestrator.get_semantic_memory") as mock_semantic,
        patch("me4brain.core.orchestrator.get_working_memory") as mock_working,
        patch("me4brain.core.orchestrator.get_procedural_memory") as mock_procedural,
    ):
        # Timestamp ISO fisso per i mock
        now_iso = datetime.now(UTC).isoformat()

        # Setup Mocks
        # 1. Embedding
        mock_embed.return_value.embed_query.return_value = [0.1] * 1024

        # 2. Router (Hybrid Retrieval)
        mock_router_obj = MagicMock()
        mock_router_obj.route.return_value.query_type.value = "factual"
        mock_router_obj.route.return_value.decision.value = "hybrid"
        mock_router_obj.route.return_value.confidence = 0.9
        mock_router.return_value = mock_router_obj

        # 3. Episodic Memory
        mock_episodic_obj = AsyncMock()
        episode = MagicMock()
        episode.content = "L'utente si chiama Fulvio."
        episode.id = "ep1"
        episode.source = "chat"
        episode.tags = []
        episode.event_time.isoformat.return_value = now_iso
        episode.metadata = {
            "event_time": now_iso
        }  # Importante per dict access in risoluzione conflitti se usato

        # Nota: nel codice orchestrator si usa episode.event_time nell'oggetto Episode,
        # ma poi nel dict result si usa episode.event_time.isoformat().

        mock_episodic_obj.search_similar.return_value = [(episode, 0.8)]
        mock_episodic.return_value = mock_episodic_obj

        # 4. Semantic Memory
        mock_semantic_obj = MagicMock()
        mock_semantic_obj.personalized_pagerank.return_value = [("ent1", 0.75)]

        ent1 = MagicMock()
        ent1.name = "Me4BrAIn"
        ent1.properties = {"type": "Project", "status": "Active"}
        ent1.id = "ent1"
        ent1.type = "Project"
        ent1.created_at.isoformat.return_value = now_iso

        mock_semantic_obj.get_entity.return_value = ent1
        mock_semantic.return_value = mock_semantic_obj

        # 5. Working Memory (Session Graph)
        mock_working_obj = MagicMock()
        mock_working_obj.get_session_graph.return_value.nodes = MagicMock(return_value=["ent1"])
        mock_working_obj.add_message = AsyncMock()
        mock_working_obj.persist_graph = AsyncMock()
        mock_working.return_value = mock_working_obj

        # 6. Procedural Memory
        mock_procedural.return_value.find_similar_execution = AsyncMock(return_value=None)

        # START TEST
        input_query = "Chi sono io e qual è lo stato del progetto Me4BrAIn?"
        print(f"\n👤 Input User: {input_query}")

        try:
            state = await run_cognitive_cycle(
                tenant_id="default",
                user_id="user_123",
                session_id="session_test_01",
                user_input=input_query,
            )

            print("\n🤖 Final State:")
            print(f"   Confidence: {state.get('confidence')}")
            print(f"   Sources Used: {state.get('sources_used')}")
            print(f"\n📝 Final Response:\n{state.get('final_response')}")

            if state.get("reasoning_trace"):
                print(f"\n🧠 Reasoning Trace:\n{state.get('reasoning_trace')[0][:500]}...")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback

            traceback.print_exc()

    print("\n🎉 Test completato.")


if __name__ == "__main__":
    asyncio.run(main())
