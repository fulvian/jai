#!/usr/bin/env python3
"""Test Script per Cognitive Pipeline.

Testa la pipeline cognitiva unificata con Kimi K2.5 + DeepSeek v3.2.

Usage:
    uv run python scripts/test_cognitive_pipeline.py
    uv run python scripts/test_cognitive_pipeline.py "correlazione Apple e Bitcoin"
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

from me4brain.core.cognitive_pipeline import run_cognitive_pipeline
from me4brain.utils.logging import configure_logging

configure_logging()

TENANT_ID = "me4brain_core"
USER_ID = "test_user"


def display_result(result: dict) -> None:
    """Formatta e visualizza il risultato."""
    print("\n" + "=" * 60)
    print("📊 RISULTATO PIPELINE COGNITIVA")
    print("=" * 60)

    analysis = result.get("analysis", {})
    print(f"\n🎯 Intent: {analysis.get('intent', 'N/A')}")
    print(f"   Tipo Analisi: {analysis.get('analysis_type', 'simple')}")
    print(f"   Entità: {', '.join(analysis.get('entities', []))}")

    collected = result.get("collected_data", [])
    if collected:
        print(f"\n📦 Dati Raccolti ({len(collected)} fonti):")
        for i, d in enumerate(collected, 1):
            status = "✅" if d.get("success") else "❌"
            print(f"   {i}. {status} {d.get('tool_name', 'N/A')} ({d.get('type', '')})")
            if d.get("success") and d.get("result"):
                data = d["result"]
                if "price" in data:
                    print(f"      → Prezzo: ${data.get('price', 'N/A'):,.2f}")
                elif "temperature" in data:
                    print(f"      → Temp: {data.get('temperature')}°C")

    print("\n" + "-" * 60)
    print("🧠 RISPOSTA:")
    print("-" * 60)
    print(result.get("response", "Nessuna risposta"))


async def interactive_loop() -> None:
    """Loop interattivo per query multiple."""
    print("\n" + "=" * 60)
    print("🚀 ME4BRAIN COGNITIVE PIPELINE")
    print("   Kimi K2.5 (Agentic) + DeepSeek v3.2 (Thinking)")
    print("=" * 60)
    print("Inserisci query in linguaggio naturale.")
    print("Digita 'exit' per uscire.")
    print("=" * 60)

    while True:
        try:
            query = input("\n🔍 Query: ").strip()

            if not query:
                continue
            if query.lower() in ("exit", "quit", "q", "esci"):
                print("\n👋 Arrivederci!")
                break

            print("\n⏳ Elaborazione in corso...")

            result = await run_cognitive_pipeline(
                tenant_id=TENANT_ID,
                user_id=USER_ID,
                query=query,
                save_memory=True,
            )

            display_result(result)

        except KeyboardInterrupt:
            print("\n👋 Interrotto.")
            break
        except Exception as e:
            print(f"\n❌ Errore: {e}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test Cognitive Pipeline")
    parser.add_argument("query", nargs="?", help="Query opzionale")
    args = parser.parse_args()

    if args.query:
        result = await run_cognitive_pipeline(
            tenant_id=TENANT_ID,
            user_id=USER_ID,
            query=args.query,
            save_memory=True,
        )
        display_result(result)
    else:
        await interactive_loop()


if __name__ == "__main__":
    asyncio.run(main())
