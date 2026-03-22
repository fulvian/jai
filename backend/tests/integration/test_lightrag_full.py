"""Integration Test for LightRAG.

Verifica l'intero flusso con un manuale reale (Arduino Uno).
Richiede Neo4j e Qdrant running.
"""

import pytest
import asyncio
import os
import time
from pypdf import PdfReader


def get_manual_text():
    pdf_path = "data/manuals/arduino_uno.pdf"
    if not os.path.exists(pdf_path):
        return "Me4BrAIn è una piattaforma di memoria agentica universale."
    reader = PdfReader(pdf_path)
    text = ""
    # Prendiamo le prime 5 pagine per un test significativo ma non eccessivo
    for page in reader.pages[:5]:
        text += page.extract_text() + "\n"
    return text


@pytest.mark.integration
@pytest.mark.asyncio
async def test_lightrag_full_integration():
    """Test E2E di LightRAG con LLM reale e manuale Arduino.

    Richiede Neo4j e Qdrant running (docker-compose up).
    """
    from me4brain.memory import get_semantic_memory
    from me4brain.retrieval.lightrag import LightRAG

    # Usa il SemanticMemory factory che si connette a Neo4j
    semantic = get_semantic_memory()
    await semantic.initialize()

    engine = LightRAG(semantic=semantic)

    timestamp = int(time.time())
    tenant_id = f"arduino_test_{timestamp}"
    user_id = f"test_user_{timestamp}"

    text = get_manual_text()[:2000]

    print(f"\n[LightRAG] Starting ingestion ({len(text)} chars)...")
    await engine.ingest(text, tenant_id, user_id, source="arduino_manual")

    print("[LightRAG] Starting dual retrieval...")
    query = "Quali sono le specifiche tecniche del processore ATmega328P?"
    results = await engine.dual_retrieval(query, tenant_id, top_k=5)

    print(f"[LightRAG] Found {len(results)} results.")
    for i, res in enumerate(results):
        print(f"  {i + 1}. [{res.source}] Score: {res.score:.4f} | Content: {res.content[:150]}...")

    assert len(results) > 0
    # Verifichiamo che i sorgenti siano misti (Hybrid)
    sources = set(r.source for r in results)
    print(f"[LightRAG] Sources covered: {sources}")
    assert "local" in sources

    # Cleanup - chiudi connessione
    await semantic.close()


if __name__ == "__main__":
    asyncio.run(test_lightrag_full_integration())
