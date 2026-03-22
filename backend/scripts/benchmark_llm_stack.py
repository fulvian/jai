#!/usr/bin/env python3
"""Benchmark LLM Stack - Test Comparativo.

Testa 5 configurazioni LLM stack con query complessa multidominio:
1. Solo Kimi K2.5 (tutto)
2. Solo Mistral Large 3 (tutto)
3. Kimi K2.5 (routing+tool) + DeepSeek V3.2 Speciale (sintesi)
4. DeepSeek V3.2 (routing+tool) + Mistral Large 3 (sintesi)
5. Mistral Large 3 (routing+tool) + DeepSeek V3.2 Speciale (sintesi)

Usage:
    python scripts/benchmark_llm_stack.py
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# =============================================================================
# Configuration
# =============================================================================

API_BASE = "http://localhost:8089"
TIMEOUT = 180.0  # 3 minuti per query complesse

# Query complessa multidominio cross-analysis
TEST_QUERY = """
Sto pianificando un viaggio di lavoro a Milano la prossima settimana.
Ho bisogno di sapere:
1. Che tempo farà a Milano nei prossimi giorni?
2. Quanto sta il prezzo di Bitcoin e Ethereum in questo momento?
3. Ci sono paper accademici recenti su blockchain e smart contracts?
4. Cosa ho in agenda sul calendario questa settimana?

Fammi un'analisi incrociata: se il meteo è brutto, potrei stare in hotel 
a lavorare su research blockchain. Se il tempo è bello, posso fare meeting 
outdoor ma devo monitorare i mercati crypto. Dammi una raccomandazione.
"""

# Stack configurations
STACKS = [
    {
        "name": "1. Solo Kimi K2.5",
        "model_routing": "moonshotai/kimi-k2.5:thinking",
        "model_extraction": "moonshotai/kimi-k2.5:thinking",
        "model_synthesis": "moonshotai/kimi-k2.5:thinking",
    },
    {
        "name": "2. Solo Mistral Large 3",
        "model_routing": "mistralai/mistral-large-3-675b-instruct-2512",
        "model_extraction": "mistralai/mistral-large-3-675b-instruct-2512",
        "model_synthesis": "mistralai/mistral-large-3-675b-instruct-2512",
    },
    {
        "name": "3. Kimi (routing+tool) + DeepSeek (sintesi)",
        "model_routing": "moonshotai/kimi-k2.5:thinking",
        "model_extraction": "moonshotai/kimi-k2.5:thinking",
        "model_synthesis": "deepseek/deepseek-v3.2-speciale",
    },
    {
        "name": "4. DeepSeek (routing+tool) + Mistral (sintesi)",
        "model_routing": "deepseek/deepseek-v3.2-speciale",
        "model_extraction": "deepseek/deepseek-v3.2-speciale",
        "model_synthesis": "mistralai/mistral-large-3-675b-instruct-2512",
    },
    {
        "name": "5. Mistral (routing+tool) + DeepSeek (sintesi)",
        "model_routing": "mistralai/mistral-large-3-675b-instruct-2512",
        "model_extraction": "mistralai/mistral-large-3-675b-instruct-2512",
        "model_synthesis": "deepseek/deepseek-v3.2-speciale",
    },
]


@dataclass
class BenchmarkResult:
    """Risultato singolo benchmark."""

    stack_name: str
    total_time_s: float = 0.0
    routing_time_s: float = 0.0
    tools_called: list[str] = field(default_factory=list)
    domains_detected: list[str] = field(default_factory=list)
    response_length: int = 0
    response_preview: str = ""
    error: str | None = None
    success: bool = False


async def run_benchmark(stack: dict[str, str]) -> BenchmarkResult:
    """Esegue benchmark con una specifica configurazione stack."""
    result = BenchmarkResult(stack_name=stack["name"])

    # Prima dobbiamo aggiornare la configurazione del server
    # Per questo test, usiamo direttamente l'endpoint e misuriamo i tempi

    print(f"\n🔬 Testing: {stack['name']}")
    print("-" * 50)

    tools_called = []
    domains_detected = []
    response_content = ""
    analysis_time = 0.0

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{API_BASE}/v1/memory/query/stream",
                json={"query": TEST_QUERY},
                headers={"X-Tenant-ID": "benchmark", "X-User-ID": "benchmark-test"},
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            chunk_type = data.get("chunk_type", "")

                            if chunk_type == "analysis":
                                analysis = data.get("analysis", {})
                                domains_detected = analysis.get("domains_required", [])
                                analysis_time = time.time() - start_time
                                print(f"   📊 Domains: {domains_detected} ({analysis_time:.1f}s)")

                            elif chunk_type == "tool":
                                tool_call = data.get("tool_call", {})
                                tool_name = tool_call.get("tool", "")
                                success = tool_call.get("success", False)
                                if tool_name:
                                    tools_called.append(tool_name)
                                    status = "✅" if success else "❌"
                                    print(f"   🔧 Tool: {tool_name} {status}")

                            elif chunk_type == "content":
                                response_content += data.get("content", "")

                        except json.JSONDecodeError:
                            pass

        total_time = time.time() - start_time

        result.total_time_s = total_time
        result.routing_time_s = analysis_time
        result.tools_called = tools_called
        result.domains_detected = domains_detected
        result.response_length = len(response_content)
        result.response_preview = (
            response_content[:500] + "..." if len(response_content) > 500 else response_content
        )
        result.success = len(tools_called) > 0

        print(
            f"   ⏱️ Total: {total_time:.1f}s | Tools: {len(tools_called)} | Response: {len(response_content)} chars"
        )

    except Exception as e:
        result.error = str(e)
        result.total_time_s = time.time() - start_time
        print(f"   ❌ Error: {e}")

    return result


def print_report(results: list[BenchmarkResult]) -> None:
    """Stampa report comparativo."""
    print("\n")
    print("=" * 80)
    print("📊 BENCHMARK REPORT - LLM Stack Comparison")
    print("=" * 80)

    print(f"\n🔍 Query Test (multidominio cross-analysis):")
    print(f'   "{TEST_QUERY[:100]}..."')

    print("\n" + "-" * 80)
    print(f"{'Stack':<45} {'Time':<10} {'Tools':<8} {'Domains':<12} {'Resp Len'}")
    print("-" * 80)

    for r in results:
        status = "✅" if r.success else "❌"
        time_str = f"{r.total_time_s:.1f}s"
        tools_str = str(len(r.tools_called))
        domains_str = str(len(r.domains_detected))
        resp_str = str(r.response_length)

        print(
            f"{status} {r.stack_name:<43} {time_str:<10} {tools_str:<8} {domains_str:<12} {resp_str}"
        )

    print("-" * 80)

    # Ranking
    print("\n🏆 RANKING (per numero tool e velocità):")
    sorted_results = sorted(results, key=lambda x: (-len(x.tools_called), x.total_time_s))
    for i, r in enumerate(sorted_results, 1):
        if r.success:
            print(f"   {i}. {r.stack_name} - {len(r.tools_called)} tools in {r.total_time_s:.1f}s")

    # Migliore
    best = sorted_results[0] if sorted_results else None
    if best and best.success:
        print(f"\n✨ MIGLIORE: {best.stack_name}")
        print(f"   Tools: {best.tools_called}")
        print(f"   Domains: {best.domains_detected}")
        print(f"\n   Response preview:")
        print(f"   {best.response_preview[:300]}...")


async def main():
    """Esegue benchmark completo."""
    print("=" * 80)
    print("🚀 LLM STACK BENCHMARK")
    print("=" * 80)
    print(f"\n📝 Query complessa multidominio:")
    print(f"   {TEST_QUERY[:150]}...")
    print(f"\n⚠️ NOTA: Questo test usa la configurazione ATTUALE del server.")
    print(f"   Per testare stack diversi, modifica config.py e riavvia il server.")
    print(f"   Questo script misura le performance della configurazione corrente.")

    # Per ora eseguiamo solo con la config corrente
    print("\n" + "=" * 80)
    print("🔬 Testing configurazione CORRENTE del server...")
    print("=" * 80)

    result = await run_benchmark({"name": "Configurazione Attuale"})

    print_report([result])

    print("\n" + "=" * 80)
    print("📋 Per benchmark completo di TUTTI gli stack:")
    print("   1. Modifica manualmente: src/me4brain/llm/config.py")
    print("   2. Riavvia il server")
    print("   3. Riesegui questo script")
    print("   4. Ripeti per ogni stack")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
