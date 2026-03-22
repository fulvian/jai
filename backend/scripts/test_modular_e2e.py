#!/usr/bin/env python3
"""Test E2E per architettura modulare Me4BrAIn.

Verifica:
1. Plugin Registry discovery (8 domini)
2. Domain Routing per query diverse
3. Tool execution via domain handlers
4. Domain dispatch bridge in tool_executor
"""

import asyncio
import sys
from typing import Any

# Test results
PASSED = 0
FAILED = 0


def log_result(test_name: str, success: bool, details: str = ""):
    """Log risultato test."""
    global PASSED, FAILED
    if success:
        PASSED += 1
        print(f"  ✅ {test_name}")
    else:
        FAILED += 1
        print(f"  ❌ {test_name}: {details}")


async def test_plugin_discovery():
    """Test 1: PluginRegistry scopre tutti gli 8 domini."""
    print("\n📦 TEST 1: Plugin Discovery")

    from me4brain.core.plugin_registry import PluginRegistry

    registry = await PluginRegistry.get_instance("test_e2e")
    handlers = list(registry._handlers.keys())

    expected_domains = {
        "sports_nba",
        "google_workspace",
        "finance_crypto",
        "science_research",
        "geo_weather",
        "knowledge_media",
        "utility",
        "web_search",
    }

    discovered = set(handlers)

    log_result(
        f"Discovered {len(handlers)} domains",
        discovered == expected_domains,
        f"Missing: {expected_domains - discovered}",
    )

    return registry


async def test_domain_routing(registry: Any):
    """Test 2: Routing query ai domini corretti."""
    print("\n🔍 TEST 2: Domain Routing")

    test_cases = [
        ("Prezzo Bitcoin oggi", "finance_crypto"),
        ("Meteo a Roma domani", "geo_weather"),
        ("Paper machine learning ArXiv", "science_research"),
        ("Top stories HackerNews", "knowledge_media"),
        ("Infortuni Lakers NBA", "sports_nba"),
        ("Cerca file su Google Drive", "google_workspace"),
    ]

    for query, expected_domain in test_cases:
        handler = await registry.route_query(query, {"entities": []})
        actual_domain = handler.domain_name if handler else "None"
        log_result(
            f'"{query[:25]}..." → {actual_domain}',
            actual_domain == expected_domain,
            f"Expected {expected_domain}",
        )


async def test_tool_execution():
    """Test 3: Esecuzione tool via domain handlers."""
    print("\n🔧 TEST 3: Tool Execution")

    # Finance: CoinGecko
    from me4brain.domains.finance_crypto.tools import finance_api

    result = await finance_api.coingecko_price(ids="bitcoin")
    log_result(
        "CoinGecko price",
        "prices" in result and "bitcoin" in result.get("prices", {}),
        str(result.get("error", "")),
    )

    # Science: ArXiv
    from me4brain.domains.science_research.tools import science_api

    result = await science_api.arxiv_search(query="neural network", max_results=3)
    log_result("ArXiv search", result.get("count", 0) > 0, str(result.get("error", "")))

    # Geo: Open-Meteo
    from me4brain.domains.geo_weather.tools import geo_api

    result = await geo_api.openmeteo_weather(city="Rome")
    log_result("Open-Meteo weather", "temperature" in result, str(result.get("error", "")))

    # Knowledge: HackerNews
    from me4brain.domains.knowledge_media.tools import knowledge_api

    result = await knowledge_api.hackernews_top(count=3)
    log_result("HackerNews top", result.get("count", 0) > 0, str(result.get("error", "")))


async def test_domain_dispatch_bridge():
    """Test 4: Domain dispatch bridge in tool_executor."""
    print("\n🔄 TEST 4: Domain Dispatch Bridge")

    from me4brain.retrieval.domain_dispatch import dispatch_to_domain, SERVICE_TO_DOMAIN

    log_result(
        f"Service mappings loaded ({len(SERVICE_TO_DOMAIN)} services)",
        len(SERVICE_TO_DOMAIN) >= 30,
        f"Only {len(SERVICE_TO_DOMAIN)} mappings",
    )

    # Test dispatch CoinGecko
    result = await dispatch_to_domain("CoinGeckoService", "get_price", {"ids": "ethereum"})
    log_result(
        "CoinGecko dispatch",
        result is not None and "prices" in result,
        "Dispatch failed or no prices",
    )

    # Test dispatch ArXiv
    result = await dispatch_to_domain("ArXivService", "search", {"query": "BERT"})
    log_result(
        "ArXiv dispatch", result is not None and result.get("count", 0) > 0, "Dispatch failed"
    )


async def test_handler_capabilities():
    """Test 5: Capabilities dei domain handlers."""
    print("\n📋 TEST 5: Handler Capabilities")

    from me4brain.core.plugin_registry import PluginRegistry

    registry = await PluginRegistry.get_instance("test_caps")

    for domain_name, handler in registry._handlers.items():
        caps = handler.capabilities
        log_result(f"{domain_name}: {len(caps)} capabilities", len(caps) > 0, "No capabilities")


async def main():
    """Run tutti i test E2E."""
    print("=" * 60)
    print("🧪 ME4BRAIN E2E TEST SUITE - Architettura Modulare")
    print("=" * 60)

    try:
        registry = await test_plugin_discovery()
        await test_domain_routing(registry)
        await test_tool_execution()
        await test_domain_dispatch_bridge()
        await test_handler_capabilities()

    except Exception as e:
        print(f"\n💥 FATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 60)
    print(f"📊 RISULTATI: {PASSED} passed, {FAILED} failed")
    print("=" * 60)

    if FAILED > 0:
        sys.exit(1)
    else:
        print("\n🎉 ALL TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(main())
