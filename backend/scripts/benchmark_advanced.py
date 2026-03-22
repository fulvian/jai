#!/usr/bin/env python3
"""Benchmark Avanzato: 4 Stack LLM x 4 Prompt Complessi.

Stack:
- A: Kimi K2.5 (tutto)
- B: Mistral Large 3 (tutto)
- C: Mistral routing → Kimi sintesi
- D: Kimi routing → Mistral sintesi

Prompt:
1. NBA + Meteo correlazione
2. Finanza SEC
3. Medico Alzheimer
4. Google Workspace report

Output:
- Console log con risposte complete
- benchmark_advanced.json con tutti i dati
- benchmark_advanced.md con report leggibile
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any

# Disabilita legacy e forza modular
os.environ["ME4BRAIN_USE_MODULAR"] = "true"
os.environ["ME4BRAIN_LEGACY_FALLBACK"] = "false"


# ============================================================================
# CONFIGURAZIONE STACK
# ============================================================================

STACKS = [
    {
        "id": "A_kimi_only",
        "name": "Kimi K2.5 (tutto)",
        "model_agentic": "moonshotai/kimi-k2.5:thinking",
        "model_thinking": "moonshotai/kimi-k2.5:thinking",
    },
    {
        "id": "B_mistral_only",
        "name": "Mistral Large 3 (tutto)",
        "model_agentic": "mistralai/mistral-large-3-675b-instruct-2512",
        "model_thinking": "mistralai/mistral-large-3-675b-instruct-2512",
    },
    {
        "id": "C_mistral_kimi",
        "name": "Mistral → Kimi",
        "model_agentic": "mistralai/mistral-large-3-675b-instruct-2512",
        "model_thinking": "moonshotai/kimi-k2.5:thinking",
    },
    {
        "id": "D_kimi_mistral",
        "name": "Kimi → Mistral",
        "model_agentic": "moonshotai/kimi-k2.5:thinking",
        "model_thinking": "mistralai/mistral-large-3-675b-instruct-2512",
    },
]


# ============================================================================
# PROMPT DI TEST
# ============================================================================

PROMPTS = [
    {
        "id": "P1_nba_meteo",
        "name": "NBA + Meteo Correlazione",
        "domains_expected": ["sports_nba", "geo_weather"],
        "query": """Vorrei capire se c'è una correlazione tra le partite giocate in casa dai Chicago Bulls negli ultimi due mesi, e il meteo nell'ora e nel luogo di svolgimento della partita. Cerca i risultati, cerca il meteo, verifica anche le statistiche dei giocatori e capiamo se c'è una correlazione forte oppure debole.""",
    },
    {
        "id": "P2_finanza_sec",
        "name": "Finanza SEC",
        "domains_expected": ["finance_crypto"],
        "query": """Vorrei individuare i migliori titoli di azioni statunitense che hanno performato meglio negli ultimi due anni, analizzare i documenti SEC e i fondamentali di queste aziende e capire se vi sono aziende sovrapprezzate dal mercato su cui investire short.""",
    },
    {
        "id": "P3_medico_alzheimer",
        "name": "Medico Alzheimer",
        "domains_expected": ["medical"],
        "query": """Mio padre ha 83 anni, ha l'Alzheimer da diversi anni, sta prendendo la quetiapina, però non riusciamo a trovare il giusto bilanciamento tra tranquillizzarlo, ma senza sedarlo e renderlo completamente estraneo alla realtà, e invece mantenerlo più reattivo, ma senza tenerlo troppo agitato. Cerchiamo una soluzione per migliorare la terapia.""",
    },
    {
        "id": "P4_google_workspace",
        "name": "Google Workspace Report",
        "domains_expected": ["google_workspace"],
        "query": """Devo scrivere la relazione che rendiconti la mia attività come consulente del progetto Anci Piccoli per il sottoprogetto relativo al Comune di Allumiere. Individua la cartella su Google Drive che hanno riferimento al Comune di Allumiere, analizza tutti i file contenuti, soprattutto gli output. Analizza tutti gli eventi nel calendario con riferimento ad Allumiere e Tolfa. Analizza le mail dell'ultimo anno relative ai comuni di Allumiere e Tolfa, leggendo il contenuto delle mail. Analizza tutte le call su Google Meet relative ai comuni di Allumiera e Tolfa. E sulla base di tutti i dati raccolti, elabora un report dettagliato, completo e strutturato che descrivi sulla base dei dati che hai raccolto tutte le mie attività da giugno 2025 fino a dicembre 2025.""",
    },
]


# ============================================================================
# FUNZIONI TEST
# ============================================================================


async def test_single_query(
    stack: dict,
    prompt: dict,
) -> dict[str, Any]:
    """Esegue un singolo test query con stack specifico."""
    from me4brain.core.cognitive_pipeline import (
        analyze_query,
        execute_semantic_tool_loop,
        synthesize_response,
    )
    from me4brain.embeddings import get_embedding_service
    from me4brain.llm.config import get_llm_config
    from me4brain.llm.nanogpt import get_llm_client
    from me4brain.retrieval.tool_executor import ToolExecutor

    result = {
        "stack_id": stack["id"],
        "stack_name": stack["name"],
        "prompt_id": prompt["id"],
        "prompt_name": prompt["name"],
        "query": prompt["query"],
        "timestamp": datetime.now().isoformat(),
    }

    try:
        # Override config per questo stack
        config = get_llm_config()
        config.model_agentic = stack["model_agentic"]
        config.model_primary_thinking = stack["model_thinking"]

        llm_client = get_llm_client()
        embedding_service = get_embedding_service()
        executor = ToolExecutor()

        start_time = datetime.now()

        # Step 1: Analyze
        print(f"   ⏳ Analyzing query...")
        analysis = await analyze_query(prompt["query"], llm_client, config)
        result["domains_detected"] = analysis.get("domains_required", [])
        result["entities_count"] = len(analysis.get("entities", []))

        print(f"   ✓ Domains: {result['domains_detected']}")

        # Step 2: Execute tools
        print(f"   ⏳ Executing tools...")
        collected_data = await execute_semantic_tool_loop(
            tenant_id="benchmark_adv",
            user_id="benchmark",
            user_query=prompt["query"],
            executor=executor,
            embedding_service=embedding_service,
            llm_client=llm_client,
            config=config,
            analysis=analysis,
        )

        result["tools_called"] = [d.get("tool_name", "unknown") for d in collected_data]
        result["tools_success"] = sum(1 for d in collected_data if d.get("success"))
        result["tools_total"] = len(collected_data)

        for d in collected_data:
            status = "✓" if d.get("success") else "✗"
            tool = d.get("tool_name", "unknown")
            print(f"   {status} Tool: {tool}")

        # Step 3: Synthesize
        print(f"   ⏳ Synthesizing response...")
        response = await synthesize_response(
            query=prompt["query"],
            analysis=analysis,
            collected_data=collected_data,
            memory_context="",
            llm_client=llm_client,
            config=config,
        )

        end_time = datetime.now()

        result["response_full"] = response  # RISPOSTA COMPLETA!
        result["response_length"] = len(response)
        result["latency_ms"] = (end_time - start_time).total_seconds() * 1000
        result["success"] = True
        result["error"] = None

        print(f"   ✓ Response: {len(response)} chars")
        print(f"   ⏱️ Latency: {result['latency_ms'] / 1000:.1f}s")

        # STAMPA RISPOSTA COMPLETA A CONSOLE
        print("\n" + "=" * 50)
        print("📄 RISPOSTA COMPLETA:")
        print("=" * 50)
        print(response)
        print("=" * 50 + "\n")

    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        result["response_full"] = f"ERRORE: {e}"
        result["response_length"] = 0
        result["latency_ms"] = 0
        print(f"   ✗ Error: {e}")

    return result


async def run_benchmark() -> dict[str, Any]:
    """Esegue benchmark completo: 4 stack x 4 prompt = 16 test."""
    print("=" * 70)
    print("🚀 BENCHMARK AVANZATO: 4 Stack x 4 Prompt")
    print("=" * 70)
    print(f"Stacks: {[s['name'] for s in STACKS]}")
    print(f"Prompts: {[p['name'] for p in PROMPTS]}")
    print(f"Total tests: {len(STACKS) * len(PROMPTS)}")
    print("=" * 70)

    results = []
    test_num = 0
    total_tests = len(STACKS) * len(PROMPTS)

    for stack in STACKS:
        print(f"\n{'=' * 70}")
        print(f"📊 STACK: {stack['name']}")
        print(f"   Routing/Tool: {stack['model_agentic']}")
        print(f"   Synthesis: {stack['model_thinking']}")
        print("=" * 70)

        for prompt in PROMPTS:
            test_num += 1
            print(f"\n[{test_num}/{total_tests}] 📝 {prompt['name']}")
            print(f"   Query: {prompt['query'][:80]}...")

            result = await test_single_query(stack, prompt)
            results.append(result)

            # SALVA JSON INCREMENTALE dopo ogni test
            partial_data = {
                "benchmark_type": "advanced_4x4",
                "timestamp": datetime.now().isoformat(),
                "test_completed": test_num,
                "total_tests": total_tests,
                "stacks": [s["name"] for s in STACKS],
                "prompts": [p["name"] for p in PROMPTS],
                "results": results,
            }
            with open("benchmark_advanced.json", "w") as f:
                json.dump(partial_data, f, indent=2, ensure_ascii=False)
            print(f"   💾 Salvato JSON incrementale ({test_num}/{total_tests})")

            # Pausa tra test per non sovraccaricare API
            if test_num < total_tests:
                print("   ⏳ Pausa 5s...")
                await asyncio.sleep(5)

    return {
        "benchmark_type": "advanced_4x4",
        "timestamp": datetime.now().isoformat(),
        "stacks": [s["name"] for s in STACKS],
        "prompts": [p["name"] for p in PROMPTS],
        "results": results,
    }


def generate_report(data: dict) -> str:
    """Genera report Markdown con risposte complete."""
    lines = [
        "# 📊 Benchmark Avanzato LLM - Report Completo",
        "",
        f"**Data:** {data['timestamp'][:16]}",
        f"**Stacks testati:** {len(data['stacks'])}",
        f"**Prompt testati:** {len(data['prompts'])}",
        f"**Test totali:** {len(data['results'])}",
        "",
        "---",
        "",
    ]

    # Tabella riassuntiva
    lines.append("## 📈 Tabella Riassuntiva")
    lines.append("")
    lines.append("| Stack | Prompt | Latenza | Tools | Risposta | Success |")
    lines.append("|-------|--------|---------|-------|----------|---------|")

    for r in data["results"]:
        success = "✅" if r.get("success") else "❌"
        latency = f"{r.get('latency_ms', 0) / 1000:.1f}s"
        tools = f"{r.get('tools_success', 0)}/{r.get('tools_total', 0)}"
        resp_len = f"{r.get('response_length', 0)}c"
        lines.append(
            f"| {r['stack_name']} | {r['prompt_name']} | {latency} | {tools} | {resp_len} | {success} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("")

    # Dettaglio per stack
    for stack in data["stacks"]:
        lines.append(f"## 🔧 {stack}")
        lines.append("")

        stack_results = [r for r in data["results"] if r["stack_name"] == stack]

        for r in stack_results:
            lines.append(f"### 📝 {r['prompt_name']}")
            lines.append("")
            lines.append(f"**Query:** {r['query'][:200]}...")
            lines.append("")
            lines.append(f"- **Latenza:** {r.get('latency_ms', 0) / 1000:.1f}s")
            lines.append(f"- **Domini rilevati:** {r.get('domains_detected', [])}")
            lines.append(
                f"- **Tools:** {r.get('tools_success', 0)}/{r.get('tools_total', 0)} - {r.get('tools_called', [])}"
            )
            lines.append(f"- **Risposta:** {r.get('response_length', 0)} chars")
            lines.append("")
            lines.append("**RISPOSTA COMPLETA:**")
            lines.append("")
            lines.append("```")
            lines.append(r.get("response_full", "N/A")[:5000])  # Max 5000 chars per risposta
            if len(r.get("response_full", "")) > 5000:
                lines.append("... [TRONCATA]")
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")

    # Analisi comparativa
    lines.append("## 🏆 Analisi Comparativa")
    lines.append("")

    # Calcola medie per stack
    stack_stats = {}
    for stack in data["stacks"]:
        stack_results = [r for r in data["results"] if r["stack_name"] == stack]
        stack_stats[stack] = {
            "avg_latency": sum(r.get("latency_ms", 0) for r in stack_results)
            / max(len(stack_results), 1),
            "total_tools_success": sum(r.get("tools_success", 0) for r in stack_results),
            "total_tools": sum(r.get("tools_total", 0) for r in stack_results),
            "avg_response_len": sum(r.get("response_length", 0) for r in stack_results)
            / max(len(stack_results), 1),
            "success_rate": sum(1 for r in stack_results if r.get("success"))
            / max(len(stack_results), 1)
            * 100,
        }

    lines.append("| Stack | Latenza Media | Tool Success | Risposta Media | Success Rate |")
    lines.append("|-------|---------------|--------------|----------------|--------------|")

    for stack, stats in stack_stats.items():
        lines.append(
            f"| {stack} | {stats['avg_latency'] / 1000:.1f}s | "
            f"{stats['total_tools_success']}/{stats['total_tools']} | "
            f"{stats['avg_response_len']:.0f}c | {stats['success_rate']:.0f}% |"
        )

    lines.append("")

    # Ranking
    ranked = sorted(stack_stats.items(), key=lambda x: (-x[1]["success_rate"], x[1]["avg_latency"]))
    lines.append("### 🥇 Ranking Finale")
    lines.append("")
    for i, (stack, stats) in enumerate(ranked, 1):
        medal = ["🥇", "🥈", "🥉", "4."][i - 1]
        lines.append(
            f"{medal} **{stack}** - Success: {stats['success_rate']:.0f}%, Latency: {stats['avg_latency'] / 1000:.1f}s"
        )

    return "\n".join(lines)


async def main():
    """Entry point."""
    # Inizializza embedding service
    from me4brain.embeddings import get_embedding_service

    print("Inizializzando embedding service...")
    get_embedding_service()

    # Esegui benchmark
    data = await run_benchmark()

    # Salva JSON
    json_path = "benchmark_advanced.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n📄 JSON salvato: {json_path}")

    # Genera e salva report
    report = generate_report(data)
    md_path = "benchmark_advanced.md"
    with open(md_path, "w") as f:
        f.write(report)
    print(f"📄 Report MD salvato: {md_path}")

    # Stampa report a console
    print("\n" + "=" * 70)
    print(report)


if __name__ == "__main__":
    asyncio.run(main())
