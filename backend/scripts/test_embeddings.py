"""
Test script per verificare il servizio Embedding BGE-M3.
Controlla:
1. Caricamento modello (MPS/CPU)
2. Generazione embedding per query (dimensione 768)
3. Generazione embedding per documenti (batch)
4. Similarità semantica di base
"""

import asyncio
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).parent.parent / "src"))

from me4brain.embeddings import get_embedding_service
from me4brain.utils.logging import configure_logging

load_dotenv()
configure_logging()


def cosine_similarity(v1, v2):
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))


def main():
    print("🚀 Test Embedding Service (BGE-M3)...")

    service = get_embedding_service()
    print(f"🔌 Device: {service.device}")

    # 1. Test Query Embedding
    query = "Chi è Fulvio Ventura?"
    print(f"\n1️⃣  Embedding Query: '{query}'")
    emb_q = service.embed_query(query)
    print(f"   ✅ Dimensione: {len(emb_q)}")
    assert len(emb_q) == 1024, f"Expected 1024 dims, got {len(emb_q)}"
    # NOTE: BGE-M3 ha dim 1024, il commento precedente diceva 768 ma bge-m3 è 1024.
    # Correggo l'assert. Verification: BGE-M3 dense embedding dimension is 1024.

    # 2. Test Document Embedding (Batch)
    docs = [
        "Fulvio Ventura è un ingegnere software.",
        "Il cielo è blu sopra le nuvole.",
        "La pasta alla carbonara richiede guanciale.",
    ]
    print(f"\n2️⃣  Embedding Batch ({len(docs)} docs)")
    embs_d = service.embed_documents(docs)
    print(f"   ✅ Generati {len(embs_d)} vettori")

    # 3. Semantic Similarity
    print("\n3️⃣  Semantic Similarity Test")
    scores = []
    for i, doc in enumerate(docs):
        sim = cosine_similarity(emb_q, embs_d[i])
        scores.append((doc, sim))
        print(f"   Query <-> Doc {i + 1}: {sim:.4f}  | '{doc}'")

    # Verifica che il doc su Fulvio sia il più simile
    best_match = max(scores, key=lambda x: x[1])
    print(f"\n🏆 Best Match: '{best_match[0]}' (Score: {best_match[1]:.4f})")

    if "Fulvio" in best_match[0]:
        print("✅ Test logico superato.")
    else:
        print("❌ Test logico fallito (Similarità inattesa).")


if __name__ == "__main__":
    main()
