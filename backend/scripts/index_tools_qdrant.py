#!/usr/bin/env python3
"""
Script per indicizzare tutti i tool esistenti in Qdrant.

Legge i tool da KuzuDB e li indicizza in Qdrant per ricerca vettoriale veloce.
Eseguire una volta sola, poi i nuovi tool verranno indicizzati automaticamente.

Usage:
    python scripts/index_tools_qdrant.py

    # Con batch size personalizzato
    python scripts/index_tools_qdrant.py --batch-size 32

    # Solo tenant specifico
    python scripts/index_tools_qdrant.py --tenant me4brain_core
"""

import argparse
import asyncio
import json
import time
from typing import Any

import structlog

from me4brain.config import get_settings
from me4brain.embeddings import get_embedding_service
from me4brain.memory import get_procedural_memory
from me4brain.memory.procedural import Tool

logger = structlog.get_logger(__name__)


async def count_tools_in_kuzu(tenant_id: str) -> int:
    """Conta i tool presenti in KuzuDB."""
    procedural = get_procedural_memory()
    semantic = procedural.get_semantic()
    conn = semantic.get_connection()

    result = conn.execute(
        """
        MATCH (t:Entity)
        WHERE t.type = 'Tool' AND t.tenant_id = $tenant_id
        RETURN count(t) AS cnt
        """,
        {"tenant_id": tenant_id},
    )

    if result.has_next():
        return result.get_next()[0]
    return 0


async def get_tools_from_kuzu(
    tenant_id: str,
    offset: int = 0,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    """Recupera tool da KuzuDB con paginazione."""
    procedural = get_procedural_memory()
    semantic = procedural.get_semantic()
    conn = semantic.get_connection()

    result = conn.execute(
        """
        MATCH (t:Entity)
        WHERE t.type = 'Tool' AND t.tenant_id = $tenant_id
        RETURN t.id, t.name, t.properties
        SKIP $offset LIMIT $limit
        """,
        {"tenant_id": tenant_id, "offset": offset, "limit": limit},
    )

    tools = []
    while result.has_next():
        row = result.get_next()
        props = json.loads(row[2]) if row[2] else {}
        tools.append(
            {
                "id": row[0],
                "name": row[1],
                "description": props.get("description", ""),
                "endpoint": props.get("endpoint"),
                "method": props.get("method", "POST"),
                "status": props.get("status", "ACTIVE"),
                "tenant_id": tenant_id,
            }
        )

    return tools


async def index_tools_batch(
    tools: list[dict[str, Any]],
    batch_size: int = 16,
) -> int:
    """Indicizza un batch di tool in Qdrant."""
    if not tools:
        return 0

    procedural = get_procedural_memory()
    embedding_service = get_embedding_service()

    # Prepara descrizioni per embedding
    descriptions = [(t["description"] or t["name"])[:500] for t in tools]

    # Genera embedding in batch
    indexed = 0
    for i in range(0, len(descriptions), batch_size):
        batch_tools = tools[i : i + batch_size]
        batch_descs = descriptions[i : i + batch_size]

        try:
            embeddings = embedding_service.embed_documents(batch_descs)

            for j, tool_dict in enumerate(batch_tools):
                tool = Tool(
                    id=tool_dict["id"],
                    name=tool_dict["name"],
                    tenant_id=tool_dict["tenant_id"],
                    description=tool_dict.get("description", ""),
                    endpoint=tool_dict.get("endpoint"),
                    method=tool_dict.get("method", "POST"),
                    status=tool_dict.get("status", "ACTIVE"),
                )

                await procedural.index_tool_in_qdrant(tool, embeddings[j])
                indexed += 1

        except Exception as e:
            logger.error("batch_indexing_failed", batch_start=i, error=str(e))
            continue

    return indexed


async def main():
    parser = argparse.ArgumentParser(description="Indicizza tool esistenti in Qdrant")
    parser.add_argument("--tenant", default=None, help="Tenant ID specifico (default: tutti)")
    parser.add_argument("--batch-size", type=int, default=16, help="Batch size per embedding")
    parser.add_argument("--page-size", type=int, default=1000, help="Page size per lettura KuzuDB")
    args = parser.parse_args()

    settings = get_settings()
    tenant_id = args.tenant or settings.default_tenant_id

    print(f"🔧 Indicizzazione Tool in Qdrant")
    print(f"=" * 60)
    print(f"Tenant: {tenant_id}")
    print(f"Batch size: {args.batch_size}")
    print()

    # Inizializza collection Qdrant
    procedural = get_procedural_memory()
    await procedural.initialize()
    print("✅ Collection Qdrant inizializzata")

    # Conta tool
    total = await count_tools_in_kuzu(tenant_id)
    print(f"📊 Tool totali in KuzuDB: {total:,}")

    if total == 0:
        print("⚠️  Nessun tool trovato in KuzuDB")
        return

    # Indicizza con paginazione
    start_time = time.time()
    indexed_total = 0
    offset = 0

    while offset < total:
        tools = await get_tools_from_kuzu(tenant_id, offset, args.page_size)
        if not tools:
            break

        indexed = await index_tools_batch(tools, args.batch_size)
        indexed_total += indexed
        offset += len(tools)

        progress = (offset / total) * 100
        print(
            f"  📦 Progresso: {offset:,}/{total:,} ({progress:.1f}%) - Indicizzati: {indexed_total:,}"
        )

    elapsed = time.time() - start_time
    rate = indexed_total / elapsed if elapsed > 0 else 0

    print()
    print(f"✅ Indicizzazione completata!")
    print(f"   Tool indicizzati: {indexed_total:,}")
    print(f"   Tempo totale: {elapsed:.1f}s")
    print(f"   Rate: {rate:.1f} tool/s")


if __name__ == "__main__":
    asyncio.run(main())
