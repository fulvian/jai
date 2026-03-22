#!/usr/bin/env python3
"""Diagnosi: verifica cosa ritorna analyze_query per query complessa."""

import asyncio
import json


async def test():
    from me4brain.llm.nanogpt import get_llm_client
    from me4brain.llm.config import get_llm_config
    from me4brain.core.cognitive_pipeline import analyze_query

    llm_client = get_llm_client()
    config = get_llm_config()

    query = """Dammi il prezzo attuale di Bitcoin ed Ethereum, le previsioni meteo per Roma e Milano per domani, e cerca su HackerNews le notizie più recenti su crypto."""

    print(f"Query: {query}\n")
    print("Chiamando analyze_query()...")

    analysis = await analyze_query(query, llm_client, config)

    print("\n=== ANALYSIS RESULT ===")
    print(json.dumps(analysis, indent=2, ensure_ascii=False))

    # Verifica entities
    entities = analysis.get("entities", [])
    print(f"\n=== ENTITIES ESTRATTE ({len(entities)}) ===")
    for e in entities:
        print(f"  - {e.get('type')}: {e.get('value')} → {e.get('target_domain')}")

    # Verifica domini
    domains = analysis.get("domains_required", [])
    print(f"\n=== DOMINI RICHIESTI ({len(domains)}) ===")
    for d in domains:
        print(f"  - {d}")


if __name__ == "__main__":
    asyncio.run(test())
