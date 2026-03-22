#!/usr/bin/env python3
"""Test SOLO score di retrieval - SENZA chiamate LLM.

Usa pattern di connessione da episodic.py (AsyncQdrantClient con gRPC).
"""

import asyncio
import sys

sys.path.insert(0, "/Users/fulvioventura/me4brain/src")

from qdrant_client import AsyncQdrantClient

# Query test
QUERIES = [
    "Qual è il prezzo del Bitcoin?",
    "Cerca documenti ANCI nel mio Google Drive",
    "Che tempo fa a Milano?",
]


async def main():
    print("\n" + "=" * 60)
    print("TEST SCORE RETRIEVAL - SOLO QDRANT (NO LLM)")
    print("normalize_embeddings=False per score più alti")
    print("=" * 60)

    # Load embedding model
    print("\n⏳ Caricamento BGE-M3...")
    from me4brain.embeddings.bge_m3 import BGEM3Service

    embedder = BGEM3Service()
    print("✅ BGE-M3 caricato\n")

    # Connect to Qdrant using production pattern (AsyncQdrantClient with gRPC)
    # Pattern from episodic.py
    qdrant = AsyncQdrantClient(
        host="localhost",
        port=6333,
        prefer_grpc=True,
        grpc_port=6334,
    )

    for query in QUERIES:
        print(f"\n📝 Query: {query}")
        print("-" * 55)

        # Generate embedding locally
        query_emb = embedder.embed_query(query)

        # Search Qdrant directly using async query_points
        try:
            response = await qdrant.query_points(
                collection_name="tool_catalog",
                query=query_emb,
                limit=10,
                with_payload=True,
            )

            print(f"{'Tool':<35} {'Score':>8} {'Domain':<18}")
            print("-" * 63)
            for point in response.points:
                tool = point.payload.get("tool_name", "?")
                domain = point.payload.get("domain", "?")
                score = point.score
                marker = "✅" if score >= 0.70 else "⚠️" if score >= 0.50 else "❌"
                print(f"{marker} {tool:<33} {score:>7.4f} {domain:<18}")

            # Stats
            scores = [p.score for p in response.points if p.score]
            if scores:
                print(
                    f"\n📊 max={max(scores):.4f} min={min(scores):.4f} avg={sum(scores) / len(scores):.4f}"
                )
        except Exception as e:
            print(f"❌ Errore: {e}")

    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())
