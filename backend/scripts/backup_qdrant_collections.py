#!/usr/bin/env python3
"""Script di backup per le collection Qdrant esistenti.

Esegue un backup completo di tutte le collection Qdrant prima della migrazione.
Crea file JSON separati per ogni collection e un manifest con metadata.

Usage:
    python scripts/backup_qdrant_collections.py [--output-dir ./backups]
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# Configurazione Qdrant
QDRANT_URL = "http://qdrant:6334"
QDRANT_URL_LOCAL = "http://localhost:6334"
TIMEOUT = 60

# Collection da backuppare
COLLECTIONS_TO_BACKUP = [
    "tool_catalog",
    "tools_and_skills",
    "me4brain_skills",
    "tools",
]


def get_qdrant_client():
    """Ottiene client Qdrant, provando Docker prima, poi localhost."""
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(url=QDRANT_URL, timeout=TIMEOUT)
        client.get_collections()
        print(f"✅ Connesso a Qdrant (Docker): {QDRANT_URL}")
        return client
    except Exception as e:
        print(f"⚠️ Docker non disponibile: {e}")
        try:
            client = QdrantClient(url=QDRANT_URL_LOCAL, timeout=TIMEOUT)
            client.get_collections()
            print(f"✅ Connesso a Qdrant (Local): {QDRANT_URL_LOCAL}")
            return client
        except Exception as e2:
            print(f"❌ Impossibile connettersi a Qdrant: {e2}")
            sys.exit(1)


def export_collection(client, collection_name: str) -> dict[str, Any]:
    """Esporta una collection completa in dizionario."""
    try:
        # Verifica se la collection esiste
        collections = client.get_collections().collections
        if not any(c.name == collection_name for c in collections):
            return {"exists": False, "points": [], "count": 0}

        # Ottieni info collection
        info = client.get_collection(collection_name)

        # Esporta tutti i punti
        points_data = []
        offset = None
        limit = 100

        while True:
            if offset:
                results, offset = client.scroll(
                    collection_name=collection_name,
                    limit=limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,  # Non esportiamo vettori per risparmiare spazio
                )
            else:
                results, offset = client.scroll(
                    collection_name=collection_name,
                    limit=limit,
                    with_payload=True,
                    with_vectors=False,
                )

            points_data.extend(
                [
                    {
                        "id": str(p.id),
                        "payload": p.payload,
                    }
                    for p in results
                ]
            )

            if not offset or len(results) < limit:
                break

        return {
            "exists": True,
            "collection_name": collection_name,
            "info": {
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": str(info.status),
            },
            "points": points_data,
            "count": len(points_data),
            "exported_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        return {
            "exists": False,
            "collection_name": collection_name,
            "error": str(e),
            "points": [],
            "count": 0,
        }


def create_manifest(backups: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    """Crea file manifest con metadata del backup."""
    total_points = sum(b.get("count", 0) for b in backups.values())
    existing_collections = sum(1 for b in backups.values() if b.get("exists", False))

    manifest = {
        "backup_id": str(uuid.uuid4()),
        "created_at": datetime.utcnow().isoformat(),
        "total_collections": len(COLLECTIONS_TO_BACKUP),
        "existing_collections": existing_collections,
        "total_points": total_points,
        "collections": list(backups.keys()),
        "files": [f"{name}.json" for name in backups.keys()],
    }

    return manifest


async def main():
    """Main function per il backup."""
    print("=" * 60)
    print("🔧 BACKUP COLLECTION QDRANT")
    print("=" * 60)

    # Determina directory output
    import argparse

    parser = argparse.ArgumentParser(description="Backup Qdrant collections")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./backups",
        help="Directory per i backup (default: ./backups)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = output_dir / f"qdrant_backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 Directory backup: {backup_dir}")

    # Connetti a Qdrant
    client = get_qdrant_client()

    # Elenca collection esistenti
    print("\n📋 Collection esistenti:")
    collections = client.get_collections().collections
    existing_names = [c.name for c in collections]
    for c in collections:
        info = client.get_collection(c.name)
        print(f"   - {c.name}: {info.points_count} punti")

    # Backup di ogni collection
    backups = {}
    for col_name in COLLECTIONS_TO_BACKUP:
        print(f"\n📦 Backup: {col_name}...")

        if col_name not in existing_names:
            print(f"   ⚠️ Collection non esiste, skip")
            backups[col_name] = {"exists": False, "points": [], "count": 0}
            continue

        data = export_collection(client, col_name)
        backups[col_name] = data

        if data.get("exists"):
            filename = f"{col_name}.json"
            filepath = backup_dir / filename

            # Salva JSON (senza vettori per risparmiare spazio)
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)

            print(f"   ✅ {data['count']} punti salvati in {filename}")
        else:
            print(f"   ❌ Errore: {data.get('error', 'Collection non esiste')}")

    # Crea manifest
    manifest = create_manifest(backups, backup_dir)
    manifest_path = backup_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    print("\n" + "=" * 60)
    print("📊 RIEPILOGO BACKUP")
    print("=" * 60)
    print(f"   Backup ID: {manifest['backup_id']}")
    print(
        f"   Collection esistenti: {manifest['existing_collections']}/{manifest['total_collections']}"
    )
    print(f"   Totale punti: {manifest['total_points']}")
    print(f"   Directory: {backup_dir}")

    print("\n📄 File creati:")
    for fname in manifest["files"]:
        fpath = backup_dir / fname
        if fpath.exists():
            size_kb = fpath.stat().st_size / 1024
            print(f"   - {fname}: {size_kb:.1f} KB")

    print(f"\n✅ Backup completato!")
    print(f"\n💾 Per ripristinare in caso di necessità:")
    print(f"   python scripts/restore_qdrant_collections.py --backup-dir {backup_dir}")

    await asyncio.sleep(0.1)  # Keep event loop alive
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
