#!/usr/bin/env python3
"""
Script di Test Real-World per Tools Interni Me4BrAIn.

Permette di testare i tool interni con query in linguaggio naturale.
Supporta:
- Query singole (es. "prezzo bitcoin")
- Query multi-tool (es. "meteo Roma e prezzo AAPL")
- Query complesse con cross-analysis LLM

Usage:
    # Modalità interattiva
    uv run python scripts/test_tools_realworld.py

    # Singola query
    uv run python scripts/test_tools_realworld.py "dimmi il prezzo del bitcoin"

Examples:
    - "quanto costa il bitcoin?"
    - "che tempo fa a Milano?"
    - "prezzo Apple e meteo a Cupertino"
    - "come il meteo influenza l'andamento del titolo Apple?"
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

# Aggiunge src al path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv()

import structlog

from me4brain.config import get_settings
from me4brain.core.tool_agent import search_candidate_tools
from me4brain.embeddings import get_embedding_service
from me4brain.llm import LLMRequest, Message, NanoGPTClient, get_llm_config
from me4brain.retrieval.tool_executor import ExecutionRequest, ToolExecutor
from me4brain.utils.logging import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

# Costanti
TENANT_ID = "me4brain_core"
USER_ID = "test_user"
MAX_SUB_QUERIES = 5


# ============================================================================
# Query Analyzer - Identifica tool necessari
# ============================================================================

QUERY_ANALYSIS_PROMPT = """Analizza questa query utente e identifica i dati necessari.

QUERY: {query}

Rispondi SOLO con JSON valido (senza markdown):
{{
    "is_multi_tool": true/false,
    "data_categories": ["crypto", "weather", "finance", "news", "science", ...],
    "sub_queries": ["query specifica per tool 1", "query specifica per tool 2", ...],
    "entities": {{
        "symbols": ["AAPL", "BTC", ...],
        "locations": ["Roma", "Milano", ...],
        "topics": ["inflazione", "GDP", ...]
    }},
    "analysis_needed": true/false
}}

REGOLE CRITICHE:
- is_multi_tool: TRUE se la query menziona DUE O PIÙ asset/argomenti diversi
  - Esempio: "Apple e Bitcoin" -> TRUE (azioni + crypto)
  - Esempio: "correlazione tra X e Y" -> TRUE (confronto richiede entrambi)
  - Esempio: "prezzo bitcoin" -> FALSE (solo crypto)
- analysis_needed: TRUE se la query chiede correlazioni, confronti, influenze tra dati
- sub_queries: crea una query SPECIFICA per ogni tipo di dato richiesto
  - "correlazione Apple e Bitcoin" -> ["prezzo azioni Apple", "prezzo bitcoin"]

TRIGGER MULTI-TOOL (imposta is_multi_tool=true se presenti):
- "e" / "and" tra due asset diversi
- "correlazione" / "correlation"
- "confronto" / "compare"
- "rispetto a" / "versus"
- "influenza" / "impatto"

CATEGORIE:
- crypto: prezzi criptovalute (bitcoin, ethereum, etc.)
- finance: azioni, forex, SEC filings (Apple, AAPL, etc.)
- weather: meteo, previsioni
- macro: dati economici FRED (GDP, inflazione)
- news: notizie, HackerNews
- science: paper arXiv, PubMed
"""


async def analyze_query(query: str, llm_client: NanoGPTClient, config: Any) -> dict:
    """Analizza la query e identifica i tool necessari."""
    prompt = QUERY_ANALYSIS_PROMPT.format(query=query)

    request = LLMRequest(
        model=config.model_agentic,
        messages=[Message(role="user", content=prompt)],
        temperature=0.1,
        max_tokens=512,
    )

    try:
        response = await llm_client.generate_response(request)
        content = response.content or "{}"

        # Pulisci eventuale markdown
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        analysis = json.loads(content.strip())

        # Post-processing euristico: correggi classificazioni errate
        analysis = _apply_multi_tool_heuristics(query, analysis)

        logger.info(
            "query_analyzed",
            is_multi_tool=analysis.get("is_multi_tool"),
            categories=analysis.get("data_categories"),
        )
        return analysis

    except json.JSONDecodeError as e:
        logger.warning("query_analysis_json_error", error=str(e))
        # Fallback: usa euristiche
        return _fallback_query_analysis(query)
    except Exception as e:
        logger.error("query_analysis_failed", error=str(e))
        return _fallback_query_analysis(query)


def _apply_multi_tool_heuristics(query: str, analysis: dict) -> dict:
    """Applica euristiche per correggere classificazioni LLM errate."""
    query_lower = query.lower()

    # Trigger keywords che indicano multi-tool
    multi_tool_triggers = [
        "correlazione",
        "correlation",
        "confronto",
        "compare",
        "rispetto a",
        "versus",
        "vs",
        "influenza",
        "impatto",
        "relazione tra",
        "differenza tra",
    ]

    # Asset keywords
    crypto_keywords = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana"]
    stock_keywords = [
        "apple",
        "aapl",
        "google",
        "googl",
        "microsoft",
        "msft",
        "tesla",
        "tsla",
        "amazon",
        "amzn",
        "azioni",
        "stock",
    ]

    has_crypto = any(kw in query_lower for kw in crypto_keywords)
    has_stock = any(kw in query_lower for kw in stock_keywords)
    has_trigger = any(trigger in query_lower for trigger in multi_tool_triggers)

    # Se ha sia crypto che stock, o ha trigger + asset multipli -> multi-tool
    if (has_crypto and has_stock) or (has_trigger and (has_crypto or has_stock)):
        analysis["is_multi_tool"] = True
        analysis["analysis_needed"] = True

        # Genera sub_queries se mancanti o insufficienti
        if len(analysis.get("sub_queries", [])) < 2:
            sub_queries = []
            if has_crypto:
                coin = "bitcoin" if "bitcoin" in query_lower or "btc" in query_lower else "ethereum"
                sub_queries.append(f"prezzo {coin}")
            if has_stock:
                symbol = "Apple" if "apple" in query_lower else "AAPL"
                if "google" in query_lower:
                    symbol = "Google"
                elif "microsoft" in query_lower:
                    symbol = "Microsoft"
                elif "tesla" in query_lower:
                    symbol = "Tesla"
                sub_queries.append(f"prezzo azioni {symbol}")
            analysis["sub_queries"] = sub_queries if sub_queries else [query]

    return analysis


def _fallback_query_analysis(query: str) -> dict:
    """Fallback: analisi euristica quando LLM fallisce."""
    query_lower = query.lower()

    # Determina se è multi-tool basandosi su keywords
    has_crypto = any(kw in query_lower for kw in ["bitcoin", "btc", "ethereum", "crypto"])
    has_stock = any(kw in query_lower for kw in ["apple", "aapl", "google", "tesla", "azioni"])
    has_weather = any(kw in query_lower for kw in ["meteo", "tempo", "weather"])

    categories = []
    sub_queries = []

    if has_crypto:
        categories.append("crypto")
        coin = "bitcoin" if "bitcoin" in query_lower else "ethereum"
        sub_queries.append(f"prezzo {coin}")
    if has_stock:
        categories.append("finance")
        symbol = "Apple" if "apple" in query_lower else "stock"
        sub_queries.append(f"prezzo azioni {symbol}")
    if has_weather:
        categories.append("weather")
        sub_queries.append("meteo attuale")

    if not categories:
        categories = ["general"]
        sub_queries = [query]

    is_multi = len(categories) > 1 or ("correlazione" in query_lower or "confronto" in query_lower)

    return {
        "is_multi_tool": is_multi,
        "data_categories": categories,
        "sub_queries": sub_queries if sub_queries else [query],
        "entities": {},
        "analysis_needed": is_multi,
    }


# ============================================================================
# Tool Execution
# ============================================================================


async def search_and_execute_tool(
    query: str,
    executor: ToolExecutor,
    embedding_service: Any,
) -> dict[str, Any]:
    """Cerca il tool migliore ed eseguilo."""
    # Genera embedding
    query_embedding = embedding_service.embed_query(query)

    # Cerca tool candidati
    candidates = await search_candidate_tools(
        tenant_id=TENANT_ID,
        query=query,
        query_embedding=query_embedding,
        limit=3,
    )

    if not candidates:
        return {"success": False, "error": "Nessun tool trovato", "query": query}

    best = candidates[0]
    logger.info(
        "tool_selected",
        name=best["name"],
        score=round(best["score"], 3),
    )

    # Estrai argomenti dalla query
    arguments = extract_arguments(query, best["name"])

    # Esegui tool
    request = ExecutionRequest(
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        intent=query,
        tool_id=best["tool_id"],
        arguments=arguments,
    )

    try:
        result = await executor.execute(request, use_muscle_memory=True)
        return {
            "success": result.success,
            "tool_name": result.tool_name,
            "tool_id": result.tool_id,
            "result": result.result,
            "error": result.error,
            "latency_ms": result.latency_ms,
            "from_cache": result.from_muscle_memory,
            "query": query,
        }
    except Exception as e:
        logger.error("tool_execution_error", error=str(e))
        return {"success": False, "error": str(e), "query": query}


def extract_arguments(query: str, tool_name: str) -> dict[str, Any]:
    """Estrae argomenti dalla query in base al tool."""
    query_lower = query.lower()
    args: dict[str, Any] = {}

    # Crypto
    if "bitcoin" in query_lower or "btc" in query_lower:
        args["coin_id"] = "bitcoin"
        args["vs_currency"] = "usd"
    elif "ethereum" in query_lower or "eth" in query_lower:
        args["coin_id"] = "ethereum"
        args["vs_currency"] = "usd"
    elif "solana" in query_lower or "sol" in query_lower:
        args["coin_id"] = "solana"
        args["vs_currency"] = "usd"

    # Stock symbols
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN", "META", "NVDA"]
    for sym in symbols:
        if sym.lower() in query_lower or sym in query:
            args["symbol"] = sym
            break
    if "apple" in query_lower:
        args["symbol"] = "AAPL"
    elif "google" in query_lower:
        args["symbol"] = "GOOGL"
    elif "microsoft" in query_lower:
        args["symbol"] = "MSFT"
    elif "tesla" in query_lower:
        args["symbol"] = "TSLA"

    # Locations -> coordinates
    locations = {
        "roma": (41.9028, 12.4964),
        "rome": (41.9028, 12.4964),
        "milano": (45.4642, 9.1900),
        "milan": (45.4642, 9.1900),
        "napoli": (40.8518, 14.2681),
        "naples": (40.8518, 14.2681),
        "firenze": (43.7696, 11.2558),
        "florence": (43.7696, 11.2558),
        "torino": (45.0703, 7.6869),
        "turin": (45.0703, 7.6869),
        "venezia": (45.4408, 12.3155),
        "venice": (45.4408, 12.3155),
        "cupertino": (37.3229, -122.0322),
        "new york": (40.7128, -74.0060),
        "san francisco": (37.7749, -122.4194),
        "london": (51.5074, -0.1278),
        "paris": (48.8566, 2.3522),
    }
    for loc, coords in locations.items():
        if loc in query_lower:
            args["latitude"] = coords[0]
            args["longitude"] = coords[1]
            break

    # FRED series
    if "gdp" in query_lower:
        args["series_id"] = "GDP"
    elif "inflazione" in query_lower or "inflation" in query_lower:
        args["series_id"] = "CPIAUCSL"
    elif "disoccupazione" in query_lower or "unemployment" in query_lower:
        args["series_id"] = "UNRATE"

    # Search queries
    if "search" in tool_name.lower() or "duck" in tool_name.lower():
        args["query"] = query

    return args


# ============================================================================
# Cross-Analysis Synthesizer
# ============================================================================

SYNTHESIS_PROMPT = """L'utente ha chiesto: "{original_query}"

Ho raccolto dati da diverse fonti:

{results_json}

ISTRUZIONI:
1. Sintetizza una risposta completa e coerente
2. Integra tutti i dati raccolti in modo naturale
3. Se richiesto, identifica correlazioni o pattern tra i dati
4. Sii conciso ma informativo
5. Se alcuni dati non sono disponibili, menzionalo brevemente

Rispondi in italiano, in modo professionale ma accessibile.
"""


async def synthesize_cross_analysis(
    original_query: str,
    tool_results: list[dict],
    llm_client: NanoGPTClient,
    config: Any,
) -> str:
    """Sintetizza i risultati multi-tool in una risposta coerente."""
    # Prepara risultati per il prompt
    results_formatted = []
    for r in tool_results:
        if r.get("success"):
            results_formatted.append(
                {
                    "fonte": r.get("tool_name", "unknown"),
                    "query": r.get("query", ""),
                    "dati": r.get("result", {}),
                }
            )
        else:
            results_formatted.append(
                {
                    "fonte": r.get("tool_name", "unknown"),
                    "query": r.get("query", ""),
                    "errore": r.get("error", "Dati non disponibili"),
                }
            )

    prompt = SYNTHESIS_PROMPT.format(
        original_query=original_query,
        results_json=json.dumps(results_formatted, indent=2, ensure_ascii=False)[:3000],
    )

    request = LLMRequest(
        model=config.model_primary_thinking,
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=1024,
    )

    try:
        response = await llm_client.generate_response(request)
        return response.content or "Errore nella sintesi dei risultati."
    except Exception as e:
        logger.error("synthesis_failed", error=str(e))
        return f"Errore nella sintesi: {e}"


# ============================================================================
# Display Functions
# ============================================================================


def display_single_result(result: dict) -> None:
    """Formatta e visualizza un singolo risultato."""
    if not result.get("success"):
        print(f"  ❌ Errore: {result.get('error', 'Sconosciuto')}")
        return

    data = result.get("result", {})
    tool_name = result.get("tool_name", "unknown")

    print(f"  📦 Fonte: {tool_name}")
    print(f"  ⏱️  Latenza: {result.get('latency_ms', 0):.0f}ms")

    if result.get("from_cache"):
        print("  💾 (Cache hit)")

    print()

    # Formattazione specifica per tipo di dati
    if "price" in data and "coin" in data:
        # Crypto
        print(f"  💰 {data.get('coin', 'Crypto').upper()}")
        price = data.get("price", 0)
        if isinstance(price, (int, float)):
            print(f"     Prezzo: ${price:,.2f} {data.get('currency', 'USD').upper()}")
        else:
            print(f"     Prezzo: {price}")

    elif "temperature" in data:
        # Weather
        print(f"  🌡️  Temperatura: {data.get('temperature')}°C")
        if "humidity" in data:
            print(f"  💧 Umidità: {data.get('humidity')}%")
        if "windspeed" in data or "wind_speed" in data:
            wind = data.get("windspeed") or data.get("wind_speed")
            print(f"  💨 Vento: {wind} km/h")

    elif "symbol" in data and "price" in data:
        # Stock
        print(f"  📈 {data.get('symbol', 'STOCK')}")
        price = data.get("price")
        if price:
            print(f"     Prezzo: ${float(price):,.2f}")
        if data.get("previous_close"):
            print(f"     Close precedente: ${float(data['previous_close']):,.2f}")

    elif "observations" in data:
        # FRED
        print(f"  📊 Serie FRED: {data.get('series_id', 'N/A')}")
        for obs in data.get("observations", [])[:3]:
            print(f"     {obs.get('date')}: {obs.get('value')}")

    elif "stories" in data:
        # HackerNews
        print("  📰 Top Stories:")
        for story in data.get("stories", [])[:3]:
            print(f"     • {story.get('title', 'N/A')[:60]}...")

    elif "results" in data and isinstance(data["results"], list):
        # Search results
        print("  🔍 Risultati:")
        for r in data.get("results", [])[:3]:
            print(f"     • {r.get('title', 'N/A')[:60]}")

    else:
        # Generic JSON
        print(f"  📄 Dati: {json.dumps(data, ensure_ascii=False)[:300]}...")


def display_multi_results(results: list[dict], synthesis: str) -> None:
    """Visualizza risultati multi-tool con sintesi."""
    print("\n" + "=" * 60)
    print("📊 RISULTATI MULTI-FONTE")
    print("=" * 60)

    for i, r in enumerate(results, 1):
        print(f"\n--- Fonte {i} ---")
        print(f"  🔍 Query: {r.get('query', 'N/A')[:50]}")
        display_single_result(r)

    print("\n" + "=" * 60)
    print("🧠 CROSS-ANALYSIS")
    print("=" * 60)
    print(f"\n{synthesis}")


# ============================================================================
# Main Process Query
# ============================================================================


async def process_query(query: str, verbose: bool = True) -> dict[str, Any]:
    """Processa una query completa."""
    config = get_llm_config()
    llm_client = NanoGPTClient(
        api_key=config.nanogpt_api_key,
        base_url=config.nanogpt_base_url,
    )
    embedding_service = get_embedding_service()
    executor = ToolExecutor()

    if verbose:
        print(f'\n🔍 Query: "{query}"')
        print("=" * 60)

    # Step 1: Analizza query
    if verbose:
        print("🧠 Analizzando query...")

    analysis = await analyze_query(query, llm_client, config)

    if verbose:
        print(f"   Multi-tool: {analysis.get('is_multi_tool', False)}")
        print(f"   Categorie: {analysis.get('data_categories', [])}")
        if analysis.get("analysis_needed"):
            print("   📊 Cross-analysis richiesta")

    # Step 2: Esegui tool
    if analysis.get("is_multi_tool") and len(analysis.get("sub_queries", [])) > 1:
        # Multi-tool execution
        sub_queries = analysis.get("sub_queries", [query])[:MAX_SUB_QUERIES]

        if verbose:
            print(f"\n⚡ Eseguendo {len(sub_queries)} tool in parallelo...")

        tasks = [search_and_execute_tool(sq, executor, embedding_service) for sq in sub_queries]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Gestisci eccezioni
        tool_results = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                tool_results.append({"success": False, "error": str(r), "query": sub_queries[i]})
            else:
                tool_results.append(r)

        # Step 3: Sintesi cross-analysis se richiesta
        if analysis.get("analysis_needed") or len(tool_results) > 1:
            if verbose:
                print("\n🧠 Generando cross-analysis...")
            synthesis = await synthesize_cross_analysis(query, tool_results, llm_client, config)
        else:
            synthesis = "Risultati raccolti da fonti multiple."

        if verbose:
            display_multi_results(tool_results, synthesis)

        return {
            "type": "multi_tool",
            "results": tool_results,
            "synthesis": synthesis,
            "analysis": analysis,
        }

    else:
        # Single tool execution
        if verbose:
            print("\n⚡ Eseguendo tool...")

        result = await search_and_execute_tool(query, executor, embedding_service)

        if verbose:
            print("\n✅ RISULTATO:")
            print("-" * 40)
            display_single_result(result)

        return {"type": "single_tool", "result": result}


# ============================================================================
# Interactive Loop
# ============================================================================


async def interactive_loop() -> None:
    """Loop interattivo per query multiple."""
    print("\n" + "=" * 60)
    print("🚀 ME4BRAIN TOOLS - Test Real-World")
    print("=" * 60)
    print("Inserisci query in linguaggio naturale.")
    print("Digita 'exit', 'quit' o 'q' per uscire.")
    print("=" * 60)

    while True:
        try:
            query = input("\n🔍 Query: ").strip()

            if not query:
                continue

            if query.lower() in ("exit", "quit", "q", "esci"):
                print("\n👋 Arrivederci!")
                break

            await process_query(query, verbose=True)

        except KeyboardInterrupt:
            print("\n\n👋 Interrotto. Arrivederci!")
            break
        except Exception as e:
            print(f"\n❌ Errore: {e}")
            logger.exception("interactive_error")


# ============================================================================
# Main
# ============================================================================


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test real-world dei tool interni Me4BrAIn",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  # Modalità interattiva
  uv run python scripts/test_tools_realworld.py

  # Query singola
  uv run python scripts/test_tools_realworld.py "prezzo bitcoin"
  uv run python scripts/test_tools_realworld.py "che tempo fa a Roma?"

  # Query multi-tool
  uv run python scripts/test_tools_realworld.py "prezzo Apple e meteo Cupertino"

  # Query con cross-analysis
  uv run python scripts/test_tools_realworld.py "come il meteo influenza il titolo Apple?"
        """,
    )
    parser.add_argument("query", nargs="?", help="Query in linguaggio naturale (opzionale)")
    parser.add_argument("-q", "--quiet", action="store_true", help="Output JSON minimale")

    args = parser.parse_args()

    if args.query:
        # Singola query
        result = await process_query(args.query, verbose=not args.quiet)
        if args.quiet:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Modalità interattiva
        await interactive_loop()


if __name__ == "__main__":
    asyncio.run(main())
