#!/usr/bin/env python3
"""Benchmark comparativo per Stack LLM - Me4BrAIn.

Valuta 5 configurazioni diverse di modelli LLM usando override config a runtime.

Stack testati:
- A: Kimi K2.5 (tutto)
- B: Mistral Large 3 (tutto)
- C: Kimi K2.5 → DeepSeek V3.2 Speciale
- D: DeepSeek V3.2 → Mistral Large 3
- E: Mistral Large 3 → DeepSeek V3.2 Speciale

Usage:
    cd /Users/fulvioventura/me4brain
    uv run python scripts/benchmark_llm_stacks.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# =============================================================================
# Configuration
# =============================================================================

# Model IDs NanoGPT
KIMI_K25 = "moonshotai/kimi-k2.5:thinking"
MISTRAL_L3 = "mistralai/mistral-large-3-675b-instruct-2512"
DEEPSEEK_V32 = "deepseek/deepseek-v3.2-speciale"

# Stack definitions: (model_agentic, model_primary_thinking)
STACKS = {
    "A_kimi_only": {
        "name": "Kimi K2.5 (tutto)",
        "model_agentic": KIMI_K25,
        "model_primary_thinking": KIMI_K25,
    },
    "B_mistral_only": {
        "name": "Mistral Large 3 (tutto)",
        "model_agentic": MISTRAL_L3,
        "model_primary_thinking": MISTRAL_L3,
    },
    "C_kimi_deepseek": {
        "name": "Kimi K2.5 → DeepSeek V3.2",
        "model_agentic": KIMI_K25,
        "model_primary_thinking": DEEPSEEK_V32,
    },
    "D_deepseek_mistral": {
        "name": "DeepSeek V3.2 → Mistral L3",
        "model_agentic": DEEPSEEK_V32,
        "model_primary_thinking": MISTRAL_L3,
    },
    "E_mistral_deepseek": {
        "name": "Mistral L3 → DeepSeek V3.2",
        "model_agentic": MISTRAL_L3,
        "model_primary_thinking": DEEPSEEK_V32,
    },
}

# Query di test L3 cross-analysis (3+ domini)
TEST_QUERY = """Dammi il prezzo attuale di Bitcoin ed Ethereum, le previsioni meteo per Roma e Milano per domani, e cerca su HackerNews le notizie più recenti su crypto. Fai una sintesi correlando tutti i dati."""

EXPECTED_TOOLS = ["coingecko_price", "openmeteo_weather", "hackernews_top"]


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class StackResult:
    """Risultato benchmark per uno stack."""

    stack_id: str
    stack_name: str
    latency_ms: float = 0.0
    tools_called: list[str] = field(default_factory=list)
    tools_success: int = 0
    analysis_domains: list[str] = field(default_factory=list)
    response_preview: str = ""
    response_length: int = 0
    error: str | None = None
    model_agentic: str = ""
    model_thinking: str = ""

    # Scores
    latency_score: float = 0.0
    tool_score: float = 0.0
    synthesis_score: float = 0.0
    total_score: float = 0.0


# =============================================================================
# Benchmark Execution
# =============================================================================


async def run_benchmark_for_stack(stack_id: str, stack_config: dict) -> StackResult:
    """Esegue benchmark per un singolo stack usando import diretti."""

    result = StackResult(
        stack_id=stack_id,
        stack_name=stack_config["name"],
        model_agentic=stack_config["model_agentic"],
        model_thinking=stack_config["model_primary_thinking"],
    )

    print(f"\n{'=' * 60}")
    print(f"📊 Testing Stack: {stack_config['name']}")
    print(f"   Routing/Tool: {stack_config['model_agentic'].split('/')[-1]}")
    print(f"   Synthesis: {stack_config['model_primary_thinking'].split('/')[-1]}")
    print(f"{'=' * 60}")

    start_time = time.time()

    try:
        # Import e override config
        from me4brain.llm.config import get_llm_config
        from me4brain.llm.nanogpt import get_llm_client
        from me4brain.embeddings import get_embedding_service
        from me4brain.core.cognitive_pipeline import (
            analyze_query,
            execute_semantic_tool_loop,
            synthesize_response,
        )
        from me4brain.retrieval.tool_executor import ToolExecutor

        # Override config in memory
        config = get_llm_config()
        original_agentic = config.model_agentic
        original_thinking = config.model_primary_thinking

        # Patch temporaneo
        object.__setattr__(config, "model_agentic", stack_config["model_agentic"])
        object.__setattr__(config, "model_primary_thinking", stack_config["model_primary_thinking"])

        try:
            # Setup - usa factory per ottenere client con credenziali
            llm_client = get_llm_client()
            embedding_service = get_embedding_service()
            executor = ToolExecutor()

            tenant_id = "benchmark"
            user_id = "benchmark-test"

            # Step 1: Analyze query
            print("   ⏳ Analyzing query...")
            analysis = await analyze_query(TEST_QUERY, llm_client, config)
            result.analysis_domains = analysis.get("domains_required", [])
            print(f"   ✓ Domains: {result.analysis_domains}")

            # Step 2: Execute tools
            print("   ⏳ Executing tools...")
            tool_results = await execute_semantic_tool_loop(
                tenant_id=tenant_id,
                user_id=user_id,
                user_query=TEST_QUERY,
                executor=executor,
                embedding_service=embedding_service,
                llm_client=llm_client,
                config=config,
                analysis=analysis,
            )

            for tr in tool_results:
                tool_name = tr.get("tool_name", tr.get("_domain", "unknown"))
                success = tr.get("success", False)
                result.tools_called.append(tool_name)
                if success:
                    result.tools_success += 1
                    print(f"   ✓ Tool: {tool_name}")
                else:
                    print(f"   ✗ Tool: {tool_name} - {tr.get('error', 'failed')}")

            # Step 3: Synthesize response
            print("   ⏳ Synthesizing response...")
            response = await synthesize_response(
                query=TEST_QUERY,
                analysis=analysis,
                collected_data=tool_results,
                memory_context="",
                llm_client=llm_client,
                config=config,
            )

            result.response_preview = response[:500] if response else ""
            result.response_length = len(response) if response else 0
            print(f"   ✓ Response: {result.response_length} chars")

        finally:
            # Restore config
            object.__setattr__(config, "model_agentic", original_agentic)
            object.__setattr__(config, "model_primary_thinking", original_thinking)

        result.latency_ms = (time.time() - start_time) * 1000
        print(f"\n   ⏱️ Latenza totale: {result.latency_ms / 1000:.1f}s")

    except Exception as e:
        result.error = str(e)
        result.latency_ms = (time.time() - start_time) * 1000
        print(f"   ❌ Error: {e}")
        import traceback

        traceback.print_exc()

    # Calcola scores
    result = calculate_scores(result)

    return result


def calculate_scores(result: StackResult) -> StackResult:
    """Calcola scores per ogni metrica."""

    # 1. Latency Score (25%)
    latency_s = result.latency_ms / 1000
    if latency_s < 15:
        result.latency_score = 10.0
    elif latency_s < 25:
        result.latency_score = 8.0
    elif latency_s < 40:
        result.latency_score = 6.0
    elif latency_s < 60:
        result.latency_score = 4.0
    else:
        result.latency_score = 2.0

    # 2. Tool Score (30%)
    if result.tools_success >= 3:
        result.tool_score = 10.0
    elif result.tools_success >= 2:
        result.tool_score = 7.0
    elif result.tools_success >= 1:
        result.tool_score = 4.0
    else:
        result.tool_score = 1.0

    # 3. Synthesis Score (45%)
    if result.error:
        result.synthesis_score = 0.0
    elif result.response_length > 1500:
        result.synthesis_score = 10.0
    elif result.response_length > 800:
        result.synthesis_score = 8.0
    elif result.response_length > 400:
        result.synthesis_score = 6.0
    elif result.response_length > 200:
        result.synthesis_score = 4.0
    else:
        result.synthesis_score = 2.0

    # 4. Total Score (weighted)
    result.total_score = (
        result.latency_score * 0.25 + result.tool_score * 0.30 + result.synthesis_score * 0.45
    )

    return result


# =============================================================================
# Report Generation
# =============================================================================


def generate_report(results: list[StackResult]) -> str:
    """Genera report Markdown comparativo."""

    sorted_results = sorted(results, key=lambda r: r.total_score, reverse=True)

    report = []
    report.append("# 📊 Benchmark Stack LLM - Report Comparativo")
    report.append("")
    report.append(f"**Data:** {time.strftime('%Y-%m-%d %H:%M')}")
    report.append(f"**Query test:** {TEST_QUERY[:80]}...")
    report.append("")

    # Ranking table
    report.append("## 🏆 Ranking Finale")
    report.append("")
    report.append("| Rank | Stack | Latenza | Tools OK | Risposta | **SCORE** |")
    report.append("|------|-------|---------|----------|----------|-----------|")

    for i, r in enumerate(sorted_results, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        latency_s = r.latency_ms / 1000
        error_mark = " ⚠️" if r.error else ""
        report.append(
            f"| {medal} | {r.stack_name} | {latency_s:.1f}s | "
            f"{r.tools_success}/3 | {r.response_length}c | **{r.total_score:.1f}**{error_mark} |"
        )

    report.append("")
    report.append("## 📋 Dettaglio Stack")
    report.append("")

    for r in sorted_results:
        report.append(f"### {r.stack_name}")
        report.append(f"- **Modello Routing/Tool:** `{r.model_agentic}`")
        report.append(f"- **Modello Sintesi:** `{r.model_thinking}`")
        report.append(f"- **Latenza:** {r.latency_ms / 1000:.1f}s (score: {r.latency_score:.0f})")
        report.append(f"- **Tool success:** {r.tools_success}/3 (score: {r.tool_score:.0f})")
        report.append(f"- **Risposta:** {r.response_length} chars (score: {r.synthesis_score:.0f})")
        report.append(f"- **Domini rilevati:** {', '.join(r.analysis_domains) or 'N/A'}")
        if r.error:
            report.append(f"- **❌ Errore:** {r.error}")
        if r.response_preview:
            report.append(f"\n**Preview risposta:**\n> {r.response_preview[:300]}...")
        report.append("")

    # Recommendation
    if sorted_results and sorted_results[0].total_score > 0:
        winner = sorted_results[0]
        report.append("## ✅ Stack Consigliato")
        report.append("")
        report.append(f"**{winner.stack_name}** con score **{winner.total_score:.1f}/10**")
        report.append("")
        report.append("Configurazione:")
        report.append(f"- `model_agentic`: `{winner.model_agentic}`")
        report.append(f"- `model_primary_thinking`: `{winner.model_thinking}`")

    return "\n".join(report)


def save_json_report(results: list[StackResult], filepath: str) -> None:
    """Salva report JSON."""
    data = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "query": TEST_QUERY,
        "expected_tools": EXPECTED_TOOLS,
        "results": [
            {
                "stack_id": r.stack_id,
                "stack_name": r.stack_name,
                "model_agentic": r.model_agentic,
                "model_thinking": r.model_thinking,
                "latency_ms": r.latency_ms,
                "tools_called": r.tools_called,
                "tools_success": r.tools_success,
                "analysis_domains": r.analysis_domains,
                "response_length": r.response_length,
                "error": r.error,
                "scores": {
                    "latency": r.latency_score,
                    "tool": r.tool_score,
                    "synthesis": r.synthesis_score,
                    "total": r.total_score,
                },
            }
            for r in results
        ],
    }

    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n📄 Report JSON: {filepath}")


# =============================================================================
# Main
# =============================================================================


async def main():
    print("=" * 60)
    print("🧪 ME4BRAIN LLM STACK BENCHMARK")
    print("=" * 60)
    print(f"\nQuery: {TEST_QUERY[:80]}...")
    print(f"Stack da testare: {len(STACKS)}")
    print(f"Tempo stimato: ~5-10 minuti")
    print()

    results = []

    for stack_id, stack_config in STACKS.items():
        # Pausa tra stack
        if results:
            print("\n⏳ Pausa 3s tra stack...")
            await asyncio.sleep(3)

        result = await run_benchmark_for_stack(stack_id, stack_config)
        results.append(result)

    # Genera report
    print("\n" + "=" * 60)
    print("📊 REPORT FINALE")
    print("=" * 60)

    report_md = generate_report(results)
    print("\n" + report_md)

    # Salva report
    save_json_report(results, "benchmark_llm_stacks.json")

    with open("benchmark_llm_stacks.md", "w") as f:
        f.write(report_md)
    print("📄 Report MD: benchmark_llm_stacks.md")


if __name__ == "__main__":
    asyncio.run(main())
