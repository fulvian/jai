#!/usr/bin/env python3
"""Test esatto flusso multi-domain con analisi LLM."""

import asyncio


async def test_exact_multi_domain():
    """Riproduce esatto flusso cognitive_pipeline."""
    from me4brain.core.modular_orchestrator import try_modular_execution

    tenant_id = "test_debug"
    user_id = "test_user"

    # ESATTA query come nel test
    query = (
        "Vorrei capire se ce una correlazione tra le partite in casa dei "
        "Chicago Bulls negli ultimi due mesi, e il meteo"
    )

    # Analysis con entity person come genera LLM (questo è il problema!)
    analysis = {
        "intent": "analisi correlazione",
        "domains_required": ["sports_nba", "geo_weather"],
        "entities": [
            {"type": "organization", "value": "Chicago Bulls", "target_domain": "sports_nba"},
            {"type": "person", "value": "giocatori Chicago Bulls", "target_domain": "sports_nba"},
            {"type": "location", "value": "Chicago", "target_domain": "geo_weather"},
        ],
    }

    print("=" * 60)
    print("Testing try_modular_execution with EXACT LLM analysis")
    print("=" * 60)
    print(f"Entities count: {len(analysis['entities'])}")
    print()

    success, results = await try_modular_execution(
        tenant_id=tenant_id, user_id=user_id, query=query, analysis=analysis
    )

    print()
    print("=" * 60)
    print(f"SUCCESS: {success}")
    print(f"RESULTS COUNT: {len(results)}")
    print("=" * 60)

    for r in results:
        print(f"  Domain: {r.get('_domain')}")
        print(f"  Success: {r.get('success')}")
        print(f"  Tool: {r.get('tool_name')}")
        print(f"  Error: {r.get('error')}")
        if r.get("data"):
            print(f"  Data keys: {list(r.get('data', {}).keys())[:5]}")
        print()


if __name__ == "__main__":
    asyncio.run(test_exact_multi_domain())
