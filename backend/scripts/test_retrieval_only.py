#!/usr/bin/env python3
"""Test SOLO retrieval embedding - SENZA chiamate LLM.

Testa direttamente:
1. BGE-M3 embedding con prompt engineering
2. LlamaIndex VectorIndexRetriever
3. Score di similarità Qdrant

NON fa chiamate LLM!
"""

import asyncio
import json
import sys

sys.path.insert(0, "/app/src")

from llama_index.core.vector_stores.types import MetadataFilters, MetadataFilter, FilterOperator
from llama_index.core.retrievers import VectorIndexRetriever

# Query test
QUERIES = [
    ("Bitcoin price", "finance_crypto"),
    ("Cerca documenti ANCI", "google_workspace"),
    ("Che tempo fa a Milano", "geo_weather"),
]


async def test_retrieval():
    print("\n" + "=" * 70)
    print("TEST RETRIEVAL EMBEDDING - SOLO BGE-M3 + LLAMAINDEX (NO LLM)")
    print("=" * 70)

    # Importa dopo sys.path
    from me4brain.engine.hybrid_router.tool_index import ToolIndexManager, TOOL_CATALOG_COLLECTION
    from me4brain.engine.hybrid_router.types import HybridRouterConfig
    from me4brain.embeddings import get_embedding_service
    from qdrant_client import AsyncQdrantClient
    import os

    # Config
    config = HybridRouterConfig()
    print(f"\n📋 Config:")
    print(f"   - coarse_top_k: {config.coarse_top_k}")
    print(f"   - min_similarity_score: {config.min_similarity_score}")
    print(f"   - use_llm_reranker: {config.use_llm_reranker}")

    # Carica embedding service
    print("\n⏳ Caricamento BGE-M3...")
    emb_service = get_embedding_service()
    print("✅ BGE-M3 caricato")

    # Verifica prompt engineering
    test_text = "Bitcoin"
    expected_prefix = "Represent this query for retrieval: "
    print(f"\n🔬 Verifica Prompt Engineering:")
    print(f"   - QUERY_PREFIX atteso: '{expected_prefix}'")
    print(f"   - QUERY_PREFIX presente: {hasattr(emb_service, 'QUERY_PREFIX')}")

    # Connect to Qdrant
    qdrant_host = os.getenv("QDRANT_HOST", "me4brain-qdrant")
    print(f"\n🔗 Connessione Qdrant: {qdrant_host}:6333")
    client = AsyncQdrantClient(url=f"http://{qdrant_host}:6333")

    # Check collection
    try:
        info = await client.get_collection(TOOL_CATALOG_COLLECTION)
        print(f"✅ Collection '{TOOL_CATALOG_COLLECTION}': {info.points_count} tools indicizzati")
    except Exception as e:
        print(f"❌ Collection error: {e}")
        return

    # Test queries
    for query, expected_domain in QUERIES:
        print(f"\n{'=' * 70}")
        print(f"📝 Query: '{query}'")
        print(f"   Expected Domain: {expected_domain}")
        print("-" * 70)

        # Generate embedding
        query_vec = emb_service.embed_query(query)
        vec_norm = sum(v**2 for v in query_vec) ** 0.5
        print(f"   Embedding dim: {len(query_vec)}, norm: {vec_norm:.4f}")

        # Search Qdrant directly
        try:
            results = await client.query_points(
                collection_name=TOOL_CATALOG_COLLECTION,
                query=query_vec,
                limit=15,
                with_payload=True,
            )

            print(f"\n   {'Tool':<35} {'Score':>8} {'Domain':<18}")
            print(f"   {'-' * 63}")

            above_threshold = 0
            for point in results.points[:10]:
                tool_name = point.payload.get("tool_name", "?")
                domain = point.payload.get("domain", "?")
                score = point.score if point.score else 0.0

                # Markers
                if score >= 0.70:
                    marker = "🟢"  # Excellent
                elif score >= config.min_similarity_score:
                    marker = "🟡"  # Above threshold
                    above_threshold += 1
                else:
                    marker = "🔴"  # Below threshold

                domain_match = "✓" if domain == expected_domain else ""
                print(f"   {marker} {tool_name:<33} {score:>7.4f} {domain:<15} {domain_match}")

            # Stats
            scores = [p.score for p in results.points if p.score]
            if scores:
                print(
                    f"\n   📊 Stats: max={max(scores):.4f}, min={min(scores):.4f}, avg={sum(scores) / len(scores):.4f}"
                )
                print(
                    f"   📊 Above threshold ({config.min_similarity_score}): {above_threshold} tools"
                )

        except Exception as e:
            print(f"   ❌ Query error: {e}")

    await client.close()
    print("\n" + "=" * 70)
    print("✅ TEST COMPLETATO")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_retrieval())
