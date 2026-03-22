#!/usr/bin/env python3
"""Test 4 Prompt Complessi ORIGINALI - Solo Mistral Large 3."""

import asyncio
import os

# Forza Mistral Large 3 per tutto
os.environ["ME4BRAIN_USE_MODULAR"] = "true"
os.environ["ME4BRAIN_LEGACY_FALLBACK"] = "false"

# Invalida cache LRU config PRIMA di importare
from me4brain.llm.config import get_llm_config

get_llm_config.cache_clear()
config = get_llm_config()
print(f"✅ Config Model Agentic: {config.model_agentic}")
print(f"✅ Config Model Thinking: {config.model_primary_thinking}")

# I 4 PROMPT ORIGINALI dal benchmark
PROMPTS = [
    {
        "id": "P1_nba_meteo",
        "name": "NBA + Meteo Correlazione",
        "query": """Vorrei capire se c'è una correlazione tra le partite giocate in casa dai Chicago Bulls negli ultimi due mesi, e il meteo nell'ora e nel luogo di svolgimento della partita. Cerca i risultati, cerca il meteo, verifica anche le statistiche dei giocatori e capiamo se c'è una correlazione forte oppure debole.""",
    },
    {
        "id": "P2_finanza_sec",
        "name": "Finanza SEC",
        "query": """Vorrei individuare i migliori titoli di azioni statunitense che hanno performato meglio negli ultimi due anni, analizzare i documenti SEC e i fondamentali di queste aziende e capire se vi sono aziende sovrapprezzate dal mercato su cui investire short.""",
    },
    {
        "id": "P3_medico_alzheimer",
        "name": "Medico Alzheimer",
        "query": """Mio padre ha 83 anni, ha l'Alzheimer da diversi anni, sta prendendo la quetiapina, però non riusciamo a trovare il giusto bilanciamento tra tranquillizzarlo, ma senza sedarlo e renderlo completamente estraneo alla realtà, e invece mantenerlo più reattivo, ma senza tenerlo troppo agitato. Cerchiamo una soluzione per migliorare la terapia.""",
    },
    {
        "id": "P4_google_workspace",
        "name": "Google Workspace Report",
        "query": """Devo scrivere la relazione che rendiconti la mia attività come consulente del progetto Anci Piccoli per il sottoprogetto relativo al Comune di Allumiere. Individua la cartella su Google Drive che hanno riferimento al Comune di Allumiere, analizza tutti i file contenuti, soprattutto gli output. Analizza tutti gli eventi nel calendario con riferimento ad Allumiere e Tolfa. Analizza le mail dell'ultimo anno relative ai comuni di Allumiere e Tolfa, leggendo il contenuto delle mail. Analizza tutte le call su Google Meet relative ai comuni di Allumiera e Tolfa. E sulla base di tutti i dati raccolti, elabora un report dettagliato, completo e strutturato che descrivi sulla base dei dati che hai raccolto tutte le mie attività da giugno 2025 fino a dicembre 2025.""",
    },
]


async def test_prompt(prompt: dict) -> dict:
    """Testa singolo prompt con Mistral Large 3."""
    from me4brain.core.cognitive_pipeline import run_cognitive_pipeline

    print(f"\n{'=' * 70}")
    print(f"📝 {prompt['name']}")
    print(f"   Query: {prompt['query'][:80]}...")
    print("-" * 70)

    try:
        result = await run_cognitive_pipeline(
            tenant_id="test_mistral_orig",
            user_id="test",
            query=prompt["query"],
        )

        response = result.get("response", "") if result else ""
        tools_used = result.get("tools_used", []) if result else []

        if response:
            print(f"   ✅ Response ({len(response)} chars):")
            print("=" * 70)
            print(response)
            print("=" * 70)
            print(f"   🔧 Tools: {tools_used}")
            return {
                "prompt": prompt["id"],
                "success": True,
                "tools": tools_used,
                "response_len": len(response),
            }
        else:
            print(f"   ⚠️ Empty response")
            return {"prompt": prompt["id"], "success": False, "error": "Empty response"}

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return {"prompt": prompt["id"], "success": False, "error": str(e)}


async def main():
    print("=" * 70)
    print("🚀 TEST 4 PROMPT ORIGINALI - MISTRAL LARGE 3")
    print("=" * 70)

    results = []
    for i, prompt in enumerate(PROMPTS, 1):
        print(f"\n[{i}/{len(PROMPTS)}]", end="")
        result = await test_prompt(prompt)
        results.append(result)

    print("\n" + "=" * 70)
    print("📊 RISULTATI FINALI")
    print("=" * 70)

    success = sum(1 for r in results if r.get("success"))
    print(f"✅ Success: {success}/{len(PROMPTS)}")

    for r in results:
        status = "✅" if r.get("success") else "❌"
        info = (
            f"Tools: {r.get('tools', [])}"
            if r.get("success")
            else f"Error: {r.get('error', 'N/A')}"
        )
        print(f"  {status} {r['prompt']}: {info}")


if __name__ == "__main__":
    asyncio.run(main())
