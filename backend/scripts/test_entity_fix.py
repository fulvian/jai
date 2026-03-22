#!/usr/bin/env python3
"""Test rapido per verificare fix entity extraction multi-crypto."""

import asyncio


async def test():
    from me4brain.core.plugin_registry import PluginRegistry

    registry = await PluginRegistry.get_instance("test_fix")
    handler = registry.get_handler("finance_crypto")

    query = "Dammi il prezzo di Bitcoin ed Ethereum"
    analysis = {
        "domains_required": ["finance_crypto"],
        "entities": [
            {"type": "financial_instrument", "value": "bitcoin"},
            {"type": "financial_instrument", "value": "ethereum"},
        ],
    }
    context = {"user_id": "test"}

    results = await handler.execute(query, analysis, context)

    print("=== POST-FIX RESULTS ===")
    for r in results:
        print(f"Tool: {r.tool_name}")
        print(f"Success: {r.success}")
        data = r.data
        if data and "prices" in data:
            coins = list(data["prices"].keys())
            print(f"Coins returned: {coins}")
            for coin, prices in data["prices"].items():
                usd_price = prices.get("usd", "N/A")
                print(f"  {coin}: ${usd_price}")
        print("---")


if __name__ == "__main__":
    asyncio.run(test())
