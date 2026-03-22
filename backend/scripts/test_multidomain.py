#!/usr/bin/env python
"""Interactive Multi-Domain Test Script for Tool Calling Engine.

Questo script permette di testare query complesse che richiedono:
- Multi-tool execution (es. Bitcoin + Weather)
- Cross-domain analysis (es. Finance + News)
- Sequential reasoning (es. cerca info → analizza)

Usage:
    python scripts/test_multidomain.py

Esempio query da testare:
    - "Qual è il prezzo del Bitcoin e che tempo fa a Roma?"
    - "Dammi il prezzo di Apple, cerca notizie su tech su Hacker News"
    - "Confronta il meteo di oggi a Milano e Parigi"
    - "Cerca informazioni su Einstein su Wikipedia e libri correlati"
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


async def create_engine():
    """Create and initialize the engine."""
    from me4brain.engine import ToolCallingEngine

    print("\n🔧 Inizializzando Tool Calling Engine...")
    engine = await ToolCallingEngine.create()
    tools = engine.catalog.get_all_tools()

    print(f"✅ Engine pronto con {len(tools)} tools disponibili\n")

    # Group tools by domain
    domains: dict[str, list[str]] = {}
    for tool in tools:
        domain = tool.domain or "general"
        domains.setdefault(domain, []).append(tool.name)

    print("📋 Tools disponibili per dominio:")
    for domain, tool_names in sorted(domains.items()):
        print(f"   {domain}: {', '.join(tool_names)}")
    print()

    return engine


async def run_query(engine, query: str, verbose: bool = True):
    """Run a single query through the engine."""
    print(f"\n{'=' * 70}")
    print(f"📝 QUERY: {query}")
    print(f"{'=' * 70}")

    start_time = time.time()

    try:
        response = await engine.run(query)
        elapsed = (time.time() - start_time) * 1000

        if verbose:
            print(f"\n🔍 Routing Decision:")
            for task in response.tool_results:
                status = "✅" if task.success else "❌"
                print(f"   {status} {task.tool_name} → {task.latency_ms:.0f}ms")
                if verbose and task.data:
                    # Truncate long data
                    data_str = json.dumps(task.data, indent=2, ensure_ascii=False)
                    if len(data_str) > 500:
                        data_str = data_str[:500] + "...[truncated]"
                    print(f"      Data: {data_str}")
                if task.error:
                    print(f"      Error: {task.error}")

        print(f"\n💬 RISPOSTA:")
        print(f"{'─' * 70}")
        print(response.answer)
        print(f"{'─' * 70}")

        print(f"\n📊 Metriche:")
        print(f"   - Tools chiamati: {response.tools_called}")
        print(f"   - Latenza totale: {response.total_latency_ms:.0f}ms")
        print(f"   - Tempo reale: {elapsed:.0f}ms")

        return response

    except Exception as e:
        print(f"\n❌ ERRORE: {e}")
        import traceback

        traceback.print_exc()
        return None


async def run_benchmark(engine):
    """Run predefined benchmark queries."""
    benchmark_queries = [
        # Single domain, simple
        ("🏷️ Single Tool Simple", "Qual è il prezzo del Bitcoin?"),
        # Single domain, multi-entity
        ("🏷️ Single Tool Multi-Entity", "Dammi il prezzo di Apple, Tesla e Microsoft"),
        # Multi-domain parallel
        ("🌐 Multi-Domain Parallel", "Qual è il prezzo del Bitcoin e che tempo fa a Roma?"),
        # Multi-domain with complexity
        (
            "🌐 Multi-Domain Complex",
            "Cerca le top 5 notizie su Hacker News e dammi il meteo a San Francisco",
        ),
        # Cross-analysis
        ("🔬 Cross Analysis", "Dammi informazioni su Bitcoin da Wikipedia e il suo prezzo attuale"),
        # No-tool query (direct answer)
        ("💬 Direct Answer", "Ciao, come stai?"),
    ]

    print("\n" + "=" * 70)
    print("🏃 BENCHMARK MODE - Query predefinite")
    print("=" * 70)

    results = []
    for label, query in benchmark_queries:
        print(f"\n\n{'#' * 70}")
        print(f"# {label}")
        print(f"{'#' * 70}")

        response = await run_query(engine, query, verbose=False)

        if response:
            results.append(
                {
                    "label": label,
                    "query": query,
                    "tools": response.tools_called,
                    "latency_ms": response.total_latency_ms,
                    "success": all(r.success for r in response.tool_results)
                    if response.tool_results
                    else True,
                }
            )
        else:
            results.append(
                {
                    "label": label,
                    "query": query,
                    "tools": [],
                    "latency_ms": 0,
                    "success": False,
                }
            )

        # Small delay between queries
        await asyncio.sleep(0.5)

    # Summary
    print("\n\n" + "=" * 70)
    print("📊 BENCHMARK SUMMARY")
    print("=" * 70)
    print(f"{'Query':<30} {'Tools':<25} {'Latency':<10} {'Status'}")
    print("-" * 70)
    for r in results:
        tools_str = ", ".join(r["tools"][:3]) if r["tools"] else "direct"
        if len(r["tools"]) > 3:
            tools_str += f" (+{len(r['tools']) - 3})"
        status = "✅" if r["success"] else "❌"
        print(f"{r['label']:<30} {tools_str:<25} {r['latency_ms']:.0f}ms{'':<5} {status}")

    passed = sum(1 for r in results if r["success"])
    print("-" * 70)
    print(f"Totale: {passed}/{len(results)} successi")


async def interactive_mode(engine):
    """Run interactive query loop."""
    print("\n" + "=" * 70)
    print("🎮 INTERACTIVE MODE")
    print("=" * 70)
    print("Inserisci le tue query. Comandi speciali:")
    print("  /benchmark  - Esegui query di benchmark predefinite")
    print("  /tools      - Mostra tools disponibili")
    print("  /verbose    - Toggle output verboso")
    print("  /quit       - Esci")
    print()

    verbose = True

    while True:
        try:
            query = input("\n🎤 Query > ").strip()

            if not query:
                continue

            # Special commands
            if query.lower() == "/quit" or query.lower() == "/exit":
                print("👋 Arrivederci!")
                break

            if query.lower() == "/benchmark":
                await run_benchmark(engine)
                continue

            if query.lower() == "/tools":
                tools = engine.get_available_tools()
                print(f"\n📋 {len(tools)} tools disponibili:")
                for tool in sorted(tools, key=lambda t: (t.domain or "", t.name)):
                    print(f"   [{tool.domain}] {tool.name}: {tool.description[:60]}...")
                continue

            if query.lower() == "/verbose":
                verbose = not verbose
                print(f"Verbose mode: {'ON' if verbose else 'OFF'}")
                continue

            # Run query
            await run_query(engine, query, verbose=verbose)

        except KeyboardInterrupt:
            print("\n\n👋 Arrivederci!")
            break
        except EOFError:
            print("\n\n👋 Arrivederci!")
            break


async def main():
    """Main entry point."""
    print("\n" + "=" * 70)
    print("🧠 ME4BRAIN TOOL CALLING ENGINE - Interactive Tester")
    print("=" * 70)

    # Create engine
    engine = await create_engine()

    # Check args
    if len(sys.argv) > 1:
        if sys.argv[1] == "--benchmark":
            await run_benchmark(engine)
        else:
            # Single query from args
            query = " ".join(sys.argv[1:])
            await run_query(engine, query)
    else:
        # Interactive mode
        await interactive_mode(engine)


if __name__ == "__main__":
    asyncio.run(main())
