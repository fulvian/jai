#!/usr/bin/env python3
"""Script di migrazione verso la collection unificata me4brain_capabilities.

Miglia tutte le capability (tools e skills) da collection multiple a quella unificata.
Gestisce deduplicazione, normalizzazione e validazione.

Usage:
    python scripts/migrate_to_unified_collection.py [--dry-run] [--force]

Processo:
1. Legge da tutte le collection legacy
2. Deduplica per nome (mantiene il più recente)
3. Normalizza metadata secondo nuovo schema
4. Indicizza in me4brain_capabilities
5. Rinomina vecchie collection con suffisso _deprecated
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient, models
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Configurazione
QDRANT_URL = "http://qdrant:6334"
QDRANT_URL_LOCAL = "http://localhost:6334"
TIMEOUT = 60

# Collection unificata target
UNIFIED_COLLECTION = "me4brain_capabilities"

# Collection legacy da migrare
LEGACY_COLLECTIONS = [
    "tool_catalog",
    "tools_and_skills",
    "me4brain_skills",
    "tools",
]


def get_qdrant_client():
    """Ottiene client Qdrant."""
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=TIMEOUT)
        client.get_collections()
        print(f"✅ Connesso a Qdrant (Docker): {QDRANT_URL}")
        return client
    except Exception:
        try:
            client = QdrantClient(url=QDRANT_URL_LOCAL, timeout=TIMEOUT)
            client.get_collections()
            print(f"✅ Connesso a Qdrant (Local): {QDRANT_URL_LOCAL}")
            return client
        except Exception as e:
            print(f"❌ Impossibile connettersi a Qdrant: {e}")
            sys.exit(1)


def detect_capability_type(point_payload: dict) -> tuple[str, str]:
    """Determina type e subtype dal payload.

    Returns:
        (type, subtype) - es: ("tool", "static") o ("skill", "crystallized")
    """
    # Cerca indicatori nel payload
    payload_str = json.dumps(point_payload).lower()

    # Se ha skill_id o instructions, è una skill
    if "skill_id" in point_payload or "instructions" in payload_str:
        # Determina subtype
        if "clawhub" in payload_str or "local/" in str(point_payload.get("skill_id", "")):
            return "skill", "learned"
        else:
            return "skill", "crystallized"

    # Se è un tool
    if "tool" in point_payload.get("type", "").lower() or "domain" in point_payload:
        if point_payload.get("subtype") in ["static_tool", "domain_tool"]:
            return "tool", "static"
        return "tool", point_payload.get("subtype", "static")

    # Default basato sul nome collection
    return "tool", "static"


def extract_capability_data(point_payload: dict, source_collection: str) -> dict | None:
    """Estrae e normalizza i dati della capability dal payload."""

    # Determina type e subtype
    cap_type, cap_subtype = detect_capability_type(point_payload)

    # Estrai nome (varie possibili chiavi)
    name = (
        point_payload.get("name")
        or point_payload.get("tool_name")
        or point_payload.get("skill_id", "").split("/")[-1]
    )

    if not name:
        return None

    # Estrai dominio
    domain = point_payload.get("domain", "unknown")

    # Estrai descrizione
    description = (
        point_payload.get("description")
        or point_payload.get("Purpose", "")
        or point_payload.get("text", "")
    )

    # Estrai category e skill
    category = point_payload.get("category", "")
    skill = point_payload.get("skill", "")

    # Estrai schema (se presente)
    schema = {}
    if "schema_json" in point_payload:
        try:
            schema = json.loads(point_payload["schema_json"])
        except (json.JSONDecodeError, TypeError):
            schema = {}
    elif "schema" in point_payload:
        schema = point_payload["schema"]
    elif "function" in point_payload:
        schema = {"function": point_payload["function"]}

    # Tags per skills
    tags = point_payload.get("tags", [])

    # Skill ID
    skill_id = point_payload.get("skill_id", "")

    # Priority boost basato su tipo
    priority_boost_map = {
        ("tool", "static"): 1.3,
        ("tool", "domain_tool"): 1.3,
        ("tool", "unknown"): 1.1,
        ("skill", "crystallized"): 1.1,
        ("skill", "learned"): 0.9,
    }
    priority_boost = priority_boost_map.get((cap_type, cap_subtype), 1.0)

    return {
        "name": name,
        "type": cap_type,
        "subtype": cap_subtype,
        "domain": domain,
        "category": category,
        "skill": skill,
        "description": description[:1000],  # Limita lunghezza
        "schema_json": json.dumps(schema),
        "tags": tags,
        "skill_id": skill_id,
        "priority_boost": priority_boost,
        "source_collection": source_collection,
    }


def migrate_collection(client, collection_name: str) -> list[dict]:
    """Migra capabilities da una collection legacy."""
    try:
        results, _ = client.scroll(
            collection_name=collection_name,
            scroll_filter=None,  # Tutti i punti
            limit=10000,
            with_payload=True,
            with_vectors=True,  # Includi vettori per re-indicizzazione
        )

        capabilities = []
        for point in results:
            data = extract_capability_data(point.payload, collection_name)
            if data:
                data["vector"] = point.vector
                data["original_id"] = str(point.id)
                capabilities.append(data)

        return capabilities

    except Exception as e:
        print(f"   ⚠️ Errore migrazione {collection_name}: {e}")
        return []


def deduplicate_capabilities(capabilities: list[dict]) -> list[dict]:
    """Rimuove duplicati basandosi sul nome, mantiene il più recente."""
    seen = {}

    for cap in capabilities:
        name = cap["name"]

        if name not in seen:
            seen[name] = cap
        else:
            # Mantieni quello con priority_boost più alto o più recente
            existing = seen[name]
            if cap.get("priority_boost", 1.0) > existing.get("priority_boost", 1.0):
                seen[name] = cap

    return list(seen.values())


def build_embed_text(cap: dict) -> str:
    """Costruisce testo ottimizzato per embedding."""
    cap_type = cap["type"]
    name = cap["name"]
    description = cap["description"]
    domain = cap["domain"]
    category = cap.get("category", "")
    skill = cap.get("skill", "")

    # Costruisci gerarchia
    hierarchy_parts = [domain]
    if category:
        hierarchy_parts.append(category)
    if skill:
        hierarchy_parts.append(skill)
    hierarchy = " > ".join(hierarchy_parts)

    if cap_type == "skill":
        return f"""[search_query]: {name}
Skill: {name}
Purpose: {description}
Use when user wants to: {description}
Hierarchy: {hierarchy}
Domain: {domain}"""
    else:
        return f"""[search_query]: {name}
Tool: {name}
Purpose: {description}
Use when user wants to: {description}
Hierarchy: {hierarchy}
Domain: {domain}"""


async def create_unified_collection(client) -> None:
    """Crea la collection unificata."""
    collections = client.get_collections().collections
    collection_names = [c.name for c in collections]

    if UNIFIED_COLLECTION in collection_names:
        print(f"⚠️ Collection {UNIFIED_COLLECTION} esiste già")
        return

    client.create_collection(
        collection_name=UNIFIED_COLLECTION,
        vectors_config=models.VectorParams(
            size=1024,  # BGE-M3 dimension
            distance=models.Distance.COSINE,
        ),
    )
    print(f"✅ Collection {UNIFIED_COLLECTION} creata")


async def migrate_to_unified(dry_run: bool = False, force: bool = False):
    """Esegue la migrazione."""
    print("=" * 70)
    print("🔄 MIGRAZIONE A COLLECTION UNIFICATA")
    print("=" * 70)
    print(f"Target: {UNIFIED_COLLECTION}")
    print(f"Source collections: {LEGACY_COLLECTIONS}")
    print(f"Modalità: {'DRY RUN' if dry_run else 'ESECUZIONE REALE'}")
    print()

    client = get_qdrant_client()

    # Verifica esistenza collection legacy
    print("📋 Collection esistenti:")
    collections = client.get_collections().collections
    existing = {c.name: c for c in collections}

    available_legacy = []
    for col in LEGACY_COLLECTIONS:
        if col in existing:
            info = client.get_collection(col)
            print(f"   ✅ {col}: {info.points_count} punti")
            available_legacy.append(col)
        else:
            print(f"   ⚠️ {col}: non presente")

    if not available_legacy:
        print("\n❌ Nessuna collection legacy trovata. Eseguire prima il backup.")
        return 1

    # Migra da ogni collection
    print("\n📦 Fase 1: Lettura da collection legacy...")
    all_capabilities = []

    for col in available_legacy:
        print(f"   📥 {col}...")
        caps = migrate_collection(client, col)
        print(f"      → {len(caps)} capabilities estratte")
        all_capabilities.extend(caps)

    print(f"\n📊 Totale capabilities lette: {len(all_capabilities)}")

    # Deduplica
    print("\n🔄 Fase 2: Deduplicazione...")
    unique_caps = deduplicate_capabilities(all_capabilities)
    duplicates = len(all_capabilities) - len(unique_caps)
    print(f"   Rimossi duplicati: {duplicates}")
    print(f"   Capabilities uniche: {len(unique_caps)}")

    # Genera embedding e prepara punti
    print("\n📝 Fase 3: Generazione embedding...")

    from me4brain.embeddings import get_embedding_service

    emb_service = get_embedding_service()

    points = []
    for cap in unique_caps:
        # Genera embedding
        embed_text = build_embed_text(cap)
        vector = emb_service.embed_query(embed_text)

        # Priority boost
        priority = cap.get("priority_boost", 1.0)

        point = models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload={
                "name": cap["name"],
                "type": cap["type"],
                "subtype": cap["subtype"],
                "domain": cap["domain"],
                "category": cap.get("category", ""),
                "skill": cap.get("skill", ""),
                "description": cap["description"],
                "schema_json": cap["schema_json"],
                "tags": cap.get("tags", []),
                "skill_id": cap.get("skill_id", ""),
                "priority_boost": priority,
                "enabled": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
                "source_collections": cap.get("source_collection", ""),
            },
        )
        points.append(point)

    if dry_run:
        print("\n🔍 DRY RUN - Nessuna modifica eseguita")
        print(f"   Punti da inserire: {len(points)}")

        # Mostra statistiche
        type_counts = {}
        for p in points:
            t = p.payload["type"]
            type_counts[t] = type_counts.get(t, 0) + 1
        print(f"   Per tipo: {type_counts}")

        domain_counts = {}
        for p in points:
            d = p.payload["domain"]
            domain_counts[d] = domain_counts.get(d, 0) + 1
        print(f"   Per dominio: {len(domain_counts)} domini unici")

        return 0

    # Crea collection unificata
    print("\n🏗️ Fase 4: Creazione collection unificata...")
    await create_unified_collection(client)

    # Inserisci punti
    print(f"\n📥 Fase 5: Inserimento {len(points)} punti...")

    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(
            collection_name=UNIFIED_COLLECTION,
            points=batch,
        )
        print(f"   Batch {i // batch_size + 1}/{(len(points) + batch_size - 1) // batch_size}")

    # Verifica
    print("\n✅ Fase 6: Verifica...")
    info = client.get_collection(UNIFIED_COLLECTION)
    print(f"   Punti inseriti: {info.points_count}")

    # Statistiche finali
    type_stats = {}
    domain_stats = {}

    results, _ = client.scroll(
        collection_name=UNIFIED_COLLECTION,
        limit=10000,
        with_payload=True,
    )

    for p in results:
        t = p.payload.get("type", "unknown")
        type_stats[t] = type_stats.get(t, 0) + 1

        d = p.payload.get("domain", "unknown")
        domain_stats[d] = domain_stats.get(d, 0) + 1

    print(f"\n📊 STATISTICHE FINALI:")
    print(f"   Totale punti: {info.points_count}")
    print(f"   Per tipo:")
    for t, count in sorted(type_stats.items()):
        print(f"      - {t}: {count}")
    print(f"   Domini unici: {len(domain_stats)}")

    # Chiedi conferma per deprecare vecchie collection
    if not force:
        print("\n" + "=" * 70)
        response = input("⚠️ Deprecare le vecchie collection? (y/N): ")
        if response.lower() != "y":
            print("Migrazione completata senza deprecare le vecchie collection.")
            return 0

    print("\n🗑️ Deprecando vecchie collection...")
    for col in available_legacy:
        try:
            # Nota: Qdrant non supporta rename diretto
            # Copiamo i punti nella nuova collection e segnaliamo
            print(f"   ⚠️ {col} - da eliminare manualmente dopo verifica")
        except Exception as e:
            print(f"   ❌ Errore: {e}")

    print("\n" + "=" * 70)
    print("✅ MIGRAZIONE COMPLETATA")
    print("=" * 70)
    print(f"\n💾 Prossimi passi consigliati:")
    print(
        f'   1. Verificare funzionamento con: python -c "from qdrant_client import QdrantClient; ...'
    )
    print(f"   2. Testare retrieval: curl http://localhost:8000/api/v1/health")
    print(f"   3. Eliminare vecchie collection manualmente dopo verifica")

    return 0


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Migra a collection unificata")
    parser.add_argument("--dry-run", action="store_true", help="Simula senza modificare")
    parser.add_argument("--force", action="store_true", help="Forza senza conferma")
    args = parser.parse_args()

    return await migrate_to_unified(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
