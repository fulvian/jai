#!/usr/bin/env python3
"""Benchmark A/B Test: Mistral Doppia vs Singola Chiamata.

Modalità A: analyze_query → tools → synthesize_response (2 chiamate LLM)
Modalità B: unified_call (1 chiamata con function calling)

Prompt di test:
1. NBA + Meteo Correlazione
2. Finanza SEC
3. Medico Alzheimer
4. Google Workspace Report
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

# Prompt di test
PROMPTS = [
    {
        "id": "nba_meteo",
        "name": "NBA + Meteo Correlazione",
        "query": """Vorrei capire se c'è una correlazione tra le partite giocate in casa dai Chicago Bulls negli ultimi due mesi, e il meteo nell'ora e nel luogo di svolgimento della partita. Cerca i risultati, cerca il meteo, verifica anche le statistiche dei giocatori e capiamo se c'è una correlazione forte oppure debole.""",
    },
    {
        "id": "finanza_sec",
        "name": "Finanza SEC",
        "query": """Vorrei individuare i migliori titoli di azioni statunitense che hanno performato meglio negli ultimi due anni, analizzare i documenti SEC e i fondamentali di queste aziende e capire se vi sono aziende sovrapprezzate dal mercato su cui investire short.""",
    },
    {
        "id": "medico_alzheimer",
        "name": "Medico Alzheimer",
        "query": """Mio padre ha 83 anni, ha l'Alzheimer da diversi anni, sta prendendo la quetiapina, però non riusciamo a trovare il giusto bilanciamento tra tranquillizzarlo, ma senza sedarlo e renderlo completamente estraneo alla realtà, e invece mantenerlo più reattivo, ma senza tenerlo troppo agitato. Cerchiamo una soluzione per migliorare la terapia.""",
    },
    {
        "id": "google_workspace",
        "name": "Google Workspace Report",
        "query": """Devo scrivere la relazione che rendiconti la mia attività come consulente del progetto Anci Piccoli per il sottoprogetto relativo al Comune di Allumiere. Individua la cartella su Google Drive che hanno riferimento al Comune di Allumiere, analizza tutti i file contenuti, soprattutto gli output. Analizza tutti gli eventi nel calendario con riferimento ad Allumiere e Tolfa. Analizza le mail dell'ultimo anno relative ai comuni di Allumiere e Tolfa, leggendo il contenuto delle mail. Analizza tutte le call su Google Meet relative ai comuni di Allumiera e Tolfa. E sulla base di tutti i dati raccolti, elabora un report dettagliato, completo e strutturato che descrivi sulla base dei dati che hai raccolto tutte le mie attività da giugno 2025 fino a dicembre 2025.""",
    },
]

# Configurazione
MISTRAL_MODEL = "mistralai/mistral-large-3-675b-instruct-2512"


async def test_mode_a(prompt: dict) -> dict:
    """Modalità A: 2 chiamate (routing + sintesi)."""
    from me4brain.core.cognitive_pipeline import (
        analyze_query,
        execute_semantic_tool_loop,
        synthesize_response,
    )
    from me4brain.llm.config import get_llm_config
    from me4brain.retrieval.tool_executor import ToolExecutor
    from me4brain.embeddings import get_embedding_service
    from me4brain.llm.nanogpt import get_llm_client

    tenant_id = "benchmark_ab"
    start_time = time.time()
    tools_called = []
    tools_success = []
    domains = []

    try:
        # Inizializza
        llm_client = get_llm_client()
        embedding_service = get_embedding_service()
        executor = ToolExecutor()

        # Config con modello Mistral (override runtime)
        config = get_llm_config()
        # Override modelli per usare Mistral in tutto il ciclo
        object.__setattr__(config, "model_agentic", MISTRAL_MODEL)
        object.__setattr__(config, "model_primary_thinking", MISTRAL_MODEL)
        object.__setattr__(config, "model_routing", MISTRAL_MODEL)

        # Step 1: Analyze query (chiamata 1)
        analysis = await analyze_query(
            query=prompt["query"],
            llm_client=llm_client,
            config=config,
        )
        domains = analysis.get("domains_required", [])

        # Step 2: Execute tools
        collected_data = await execute_semantic_tool_loop(
            tenant_id=tenant_id,
            user_id="benchmark",
            user_query=prompt["query"],
            executor=executor,
            embedding_service=embedding_service,
            llm_client=llm_client,
            config=config,
            analysis=analysis,
        )

        # Raccogli info tool
        for d in collected_data:
            tool_name = d.get("tool_name", "unknown")
            tools_called.append(tool_name)
            if d.get("success", False):
                tools_success.append(tool_name)

        # Step 3: Synthesize (chiamata 2)
        response = await synthesize_response(
            query=prompt["query"],
            analysis=analysis,
            collected_data=collected_data,
            memory_context="",
            llm_client=llm_client,
            config=config,
        )

        latency = time.time() - start_time

        return {
            "prompt_id": prompt["id"],
            "prompt_name": prompt["name"],
            "mode": "A (doppia)",
            "latency": latency,
            "response": response,
            "response_length": len(response),
            "tools_called": tools_called,
            "tools_success": tools_success,
            "domains": domains,
            "success": True,
            "error": None,
        }

    except Exception as e:
        import traceback

        latency = time.time() - start_time
        return {
            "prompt_id": prompt["id"],
            "prompt_name": prompt["name"],
            "mode": "A (doppia)",
            "latency": latency,
            "response": "",
            "response_length": 0,
            "tools_called": tools_called,
            "tools_success": tools_success,
            "domains": domains,
            "success": False,
            "error": f"{e}\n{traceback.format_exc()}",
        }


async def test_mode_b(prompt: dict) -> dict:
    """Modalità B: 1 chiamata (risposta diretta senza function calling).

    In questa modalità Mistral risponde direttamente alla query senza
    eseguire tool, per confrontare la qualità della risposta.
    """
    from me4brain.llm.nanogpt import get_llm_client
    from me4brain.llm.models import LLMRequest, Message

    start_time = time.time()

    try:
        # Inizializza
        llm_client = get_llm_client()

        # Lista domini disponibili (hardcoded per semplicità)
        available_domains = [
            "sports_nba",
            "geo_weather",
            "finance_crypto",
            "medical",
            "google_workspace",
            "academic_research",
            "web_search",
        ]

        # Singola chiamata diretta (no function calling)
        system_prompt = """Sei un assistente AI esperto in molteplici domini.

Analizza la richiesta dell'utente e fornisci una risposta COMPLETA, DETTAGLIATA e STRUTTURATA.

REGOLE:
1. Rispondi in modo esaustivo utilizzando le tue conoscenze
2. Se servono dati specifici che non hai, indica chiaramente quali tool/API sarebbero necessari
3. Usa markdown per formattare la risposta con tabelle, liste, sezioni
4. Fornisci sempre raccomandazioni concrete e actionable

Domini di competenza: """ + ", ".join(available_domains)

        request = LLMRequest(
            model=MISTRAL_MODEL,
            messages=[
                Message(role="system", content=system_prompt),
                Message(role="user", content=prompt["query"]),
            ],
            max_tokens=8192,
        )

        # Singola chiamata diretta
        response = await llm_client.generate_response(request)

        # Estrai risposta
        response_text = ""
        if response.choices and response.choices[0].message.content:
            response_text = response.choices[0].message.content

        latency = time.time() - start_time

        return {
            "prompt_id": prompt["id"],
            "prompt_name": prompt["name"],
            "mode": "B (singola)",
            "latency": latency,
            "response": response_text,
            "response_length": len(response_text),
            "tools_called": [],  # Nessun tool in modalità B
            "tools_success": [],
            "domains": [],
            "success": True,
            "error": None,
        }

    except Exception as e:
        import traceback

        latency = time.time() - start_time
        return {
            "prompt_id": prompt["id"],
            "prompt_name": prompt["name"],
            "mode": "B (singola)",
            "latency": latency,
            "response": "",
            "response_length": 0,
            "tools_called": [],
            "tools_success": [],
            "domains": [],
            "success": False,
            "error": f"{str(e)}\n{traceback.format_exc()}",
        }


async def run_benchmark():
    """Esegue il benchmark A/B."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "model": MISTRAL_MODEL,
        "mode_a_results": [],
        "mode_b_results": [],
    }

    print("=" * 70)
    print("🚀 BENCHMARK A/B: Mistral Doppia vs Singola Chiamata")
    print("=" * 70)
    print(f"Model: {MISTRAL_MODEL}")
    print(f"Prompts: {len(PROMPTS)}")
    print(f"Total tests: {len(PROMPTS) * 2}")
    print("=" * 70)

    # Modalità A: Doppia chiamata
    print("\n" + "=" * 70)
    print("📊 MODALITÀ A: Doppia Chiamata (2 LLM calls)")
    print("=" * 70)

    for i, prompt in enumerate(PROMPTS, 1):
        print(f"\n[A-{i}/4] 📝 {prompt['name']}")
        print(f"   Query: {prompt['query'][:70]}...")

        result = await test_mode_a(prompt)
        results["mode_a_results"].append(result)

        if result["success"]:
            print(f"   ✓ Latenza: {result['latency']:.1f}s")
            print(f"   ✓ Risposta: {result['response_length']} chars")
            print(f"   ✓ Domini: {result['domains']}")
            print(f"   ✓ Tool OK: {result['tools_success']}")
        else:
            print(f"   ✗ Errore: {result['error'][:200]}")

        # Stampa risposta completa
        print("\n" + "=" * 50)
        print("📄 RISPOSTA COMPLETA A:")
        print("=" * 50)
        print(result["response"][:3000] if result["response"] else "(vuota)")
        if len(result["response"]) > 3000:
            print(f"\n... [troncata, totale {result['response_length']} chars]")
        print("=" * 50)

        # Salva incrementale
        _save_results(results)
        print("   💾 Salvato JSON incrementale")

        # Pausa tra test
        await asyncio.sleep(3)

    # Modalità B: Singola chiamata
    print("\n" + "=" * 70)
    print("📊 MODALITÀ B: Singola Chiamata (function calling)")
    print("=" * 70)

    for i, prompt in enumerate(PROMPTS, 1):
        print(f"\n[B-{i}/4] 📝 {prompt['name']}")
        print(f"   Query: {prompt['query'][:70]}...")

        result = await test_mode_b(prompt)
        results["mode_b_results"].append(result)

        if result["success"]:
            print(f"   ✓ Latenza: {result['latency']:.1f}s")
            print(f"   ✓ Risposta: {result['response_length']} chars")
            print(f"   ✓ Tool chiamati: {result['tools_called']}")
            print(f"   ✓ Tool OK: {result['tools_success']}")
        else:
            print(f"   ✗ Errore: {result['error'][:200]}")

        # Stampa risposta completa
        print("\n" + "=" * 50)
        print("📄 RISPOSTA COMPLETA B:")
        print("=" * 50)
        print(result["response"][:3000] if result["response"] else "(vuota)")
        if len(result["response"]) > 3000:
            print(f"\n... [troncata, totale {result['response_length']} chars]")
        print("=" * 50)

        # Salva incrementale
        _save_results(results)
        print("   💾 Salvato JSON incrementale")

        # Pausa tra test
        await asyncio.sleep(3)

    # Report finale
    _print_comparison(results)
    _save_results(results)

    return results


def _save_results(results: dict):
    """Salva risultati in JSON."""
    output_path = Path("benchmark_mistral_ab.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)


def _print_comparison(results: dict):
    """Stampa report comparativo."""
    print("\n" + "=" * 70)
    print("📊 REPORT COMPARATIVO FINALE")
    print("=" * 70)

    print("\n| Prompt | Modalità | Latenza | Risposta | Tool OK | Success |")
    print("|--------|----------|---------|----------|---------|---------|")

    for a, b in zip(results["mode_a_results"], results["mode_b_results"]):
        print(
            f"| {a['prompt_name'][:20]} | A (2 call) | {a['latency']:.1f}s | {a['response_length']}c | {len(a['tools_success'])} | {'✓' if a['success'] else '✗'} |"
        )
        print(
            f"| {b['prompt_name'][:20]} | B (1 call) | {b['latency']:.1f}s | {b['response_length']}c | {len(b['tools_success'])} | {'✓' if b['success'] else '✗'} |"
        )

    # Totali
    a_total_latency = sum(r["latency"] for r in results["mode_a_results"])
    b_total_latency = sum(r["latency"] for r in results["mode_b_results"])
    a_total_chars = sum(r["response_length"] for r in results["mode_a_results"])
    b_total_chars = sum(r["response_length"] for r in results["mode_b_results"])
    a_success = sum(1 for r in results["mode_a_results"] if r["success"])
    b_success = sum(1 for r in results["mode_b_results"] if r["success"])

    print("\n📈 TOTALI:")
    print(
        f"   Modalità A: {a_total_latency:.1f}s totali, {a_total_chars} chars, {a_success}/4 success"
    )
    print(
        f"   Modalità B: {b_total_latency:.1f}s totali, {b_total_chars} chars, {b_success}/4 success"
    )

    if b_total_latency > 0:
        speedup = a_total_latency / b_total_latency
        print(f"\n   Speedup B vs A: {speedup:.2f}x")


async def main():
    """Main entry point."""
    # Inizializza embedding service
    from me4brain.embeddings import get_embedding_service

    print("Inizializzando embedding service...")
    get_embedding_service()

    # Esegui benchmark
    await run_benchmark()

    print("\n✅ Benchmark completato!")
    print("📁 Risultati salvati in: benchmark_mistral_ab.json")


if __name__ == "__main__":
    asyncio.run(main())
