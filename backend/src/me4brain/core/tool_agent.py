"""Tool Agent - LLM-Based Tool Calling.

Gestisce la ricerca, selezione ed esecuzione di tool in modo autonomo.
L'LLM decide se usare un tool e quale, basandosi sulla query e sui
tool candidati trovati in Qdrant.

Pattern ReAct-style:
1. Cerca tool candidati (Qdrant)
2. LLM decide se usare tool e quale
3. Esegue tool se necessario
4. LLM formatta risposta con risultato
"""

import json
from typing import Any

import httpx
import structlog

from me4brain.config import get_settings
from me4brain.embeddings import get_embedding_service
from me4brain.llm import LLMRequest, Message, NanoGPTClient, get_llm_config
from me4brain.memory import get_procedural_memory

logger = structlog.get_logger(__name__)


# Prompt per decidere se usare un tool
TOOL_DECISION_PROMPT = """Sei un assistente AI che usa tool esterni per rispondere a domande che richiedono dati in tempo reale.

QUANDO USARE UN TOOL:
✅ Prezzo criptovalute (Bitcoin, Ethereum, etc.) → usa tool crypto/coingecko
✅ Trading crypto perpetuals → usa tool hyperliquid
✅ Trading stocks, portfolio → usa tool alpaca
✅ Meteo e previsioni → usa tool meteo/weather
✅ Dati finanziari (azioni, FRED, SEC) → usa tool finance
✅ Ricerca web → usa tool duckduckgo/search
✅ Notizie recenti → usa tool news/hackernews
✅ Ricerca paper scientifici → usa tool arxiv/pubmed/crossref
✅ Info farmaci, interazioni → usa tool rxnorm
✅ Metriche citazioni → usa tool icite
✅ Info paesi, festività → usa tool restcountries/nagerdate
✅ Terremoti recenti → usa tool usgs
✅ NASA immagini → usa tool nasa

QUANDO NON USARE TOOL:
❌ Saluti (ciao, grazie, arrivederci)
❌ Domande su di te (chi sei, cosa fai)
❌ Calcoli matematici semplici
❌ Conoscenze generali senza dati real-time

TOOL DISPONIBILI:
{tools_json}

QUERY UTENTE: {query}

ANALIZZA: La query richiede dati in tempo reale o esterni? Se sì, quale tool usare?

Rispondi SOLO con JSON valido:
{{"use_tool": true/false, "tool_id": "id_del_tool", "tool_name": "nome_tool", "arguments": {{}}, "reason": "spiegazione"}}

IMPORTANTE: Se la query menziona prezzi, valute, criptovalute, meteo, notizie, ricerca, paper, farmaci → USA IL TOOL!
"""

# Prompt per formattare la risposta del tool
TOOL_RESPONSE_PROMPT = """L'utente ha chiesto: "{query}"

Ho eseguito il tool "{tool_name}" e ho ottenuto questo risultato:
{tool_result}

Fornisci una risposta naturale e informativa all'utente basandoti su questi dati.
Sii conciso ma completo. Se ci sono errori, spiegali chiaramente.
"""


async def search_candidate_tools(
    tenant_id: str,
    query: str,
    query_embedding: list[float] | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Cerca tool candidati in Qdrant per la query.

    Args:
        tenant_id: ID tenant
        query: Query utente
        query_embedding: Embedding pre-calcolato (opzionale)
        limit: Numero massimo di tool

    Returns:
        Lista di tool candidati con info
    """
    if query_embedding is None:
        embedding_service = get_embedding_service()
        query_embedding = embedding_service.embed_query(query)

    procedural = get_procedural_memory()

    try:
        results = await procedural.search_tools_in_qdrant(
            tenant_id=tenant_id,
            query_embedding=query_embedding,
            limit=limit,
            min_score=0.4,  # Soglia più bassa per candidati
        )

        candidates = []
        for tool_id, payload, score in results:
            candidates.append(
                {
                    "tool_id": tool_id,
                    "name": payload.get("name", ""),
                    "description": payload.get("description", ""),
                    "endpoint": payload.get("endpoint", ""),
                    "method": payload.get("method", "POST"),
                    "score": score,
                }
            )

        logger.debug(
            "candidate_tools_found",
            query=query[:50],
            count=len(candidates),
        )

        return candidates

    except Exception as e:
        logger.error("tool_search_failed", error=str(e))
        return []


async def decide_tool_usage(
    query: str,
    candidate_tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Chiede all'LLM se usare un tool e quale.

    Args:
        query: Query utente
        candidate_tools: Lista di tool candidati

    Returns:
        Decisione LLM: {use_tool, tool_id, tool_name, arguments, reason}
    """
    if not candidate_tools:
        return {
            "use_tool": False,
            "tool_id": None,
            "tool_name": None,
            "arguments": {},
            "reason": "No relevant tools found",
        }

    config = get_llm_config()
    client = NanoGPTClient(
        api_key=config.nanogpt_api_key,
        base_url=config.nanogpt_base_url,
    )

    # Prepara tools per il prompt (solo info essenziali)
    tools_for_prompt = [
        {
            "id": t["tool_id"],
            "name": t["name"],
            "description": t["description"][:200],
            "relevance_score": round(t["score"], 2),
        }
        for t in candidate_tools[:5]
    ]

    prompt = TOOL_DECISION_PROMPT.format(
        tools_json=json.dumps(tools_for_prompt, indent=2, ensure_ascii=False),
        query=query,
    )

    request = LLMRequest(
        model=config.model_agentic,  # GLM-4.7-Thinking ottimale per tool calling
        messages=[Message(role="user", content=prompt)],
        temperature=0.1,  # Bassa per decisioni consistenti
        max_tokens=256,
    )

    try:
        response = await client.generate_response(request)
        content = response.content or "{}"

        # Log risposta grezza per debug
        logger.info(
            "llm_raw_response",
            content_preview=content[:300],
            content_length=len(content),
        )

        # Estrai JSON dalla risposta
        # Rimuovi eventuale markdown code block
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        decision = json.loads(content.strip())

        logger.info(
            "tool_decision_made",
            use_tool=decision.get("use_tool", False),
            tool_name=decision.get("tool_name"),
            reason=decision.get("reason", "")[:50],
        )

        return decision

    except json.JSONDecodeError as e:
        logger.warning("tool_decision_json_error", error=str(e), content=content[:100])
        return {
            "use_tool": False,
            "tool_id": None,
            "tool_name": None,
            "arguments": {},
            "reason": f"JSON parse error: {e}",
        }
    except Exception as e:
        logger.error("tool_decision_failed", error=str(e))
        return {
            "use_tool": False,
            "tool_id": None,
            "tool_name": None,
            "arguments": {},
            "reason": f"LLM error: {e}",
        }


async def execute_tool(
    tool_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Esegue un tool e restituisce il risultato.

    Args:
        tool_id: ID del tool
        tool_name: Nome del tool (per logging)
        arguments: Argomenti per il tool

    Returns:
        Risultato dell'esecuzione
    """
    settings = get_settings()
    base_url = f"http://localhost:{settings.port}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Corretto: POST /v1/tools/execute con tool_id nel body
            response = await client.post(
                f"{base_url}/v1/tools/execute",
                json={
                    "tool_id": tool_id,
                    "arguments": arguments,
                    "intent": "",  # Opzionale
                    "use_cache": True,
                },
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    "tool_executed_successfully",
                    tool_id=tool_id,
                    tool_name=tool_name,
                )
                return result
            else:
                error_detail = response.text[:200]
                logger.warning(
                    "tool_execution_failed",
                    tool_id=tool_id,
                    status=response.status_code,
                    error=error_detail,
                )
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {error_detail}",
                }

        except Exception as e:
            logger.error("tool_execution_error", tool_id=tool_id, error=str(e))
            return {
                "success": False,
                "error": str(e),
            }


async def format_tool_response(
    query: str,
    tool_name: str,
    tool_result: dict[str, Any],
) -> str:
    """Formatta il risultato del tool in risposta naturale.

    Args:
        query: Query originale utente
        tool_name: Nome del tool usato
        tool_result: Risultato dell'esecuzione

    Returns:
        Risposta formattata per l'utente
    """
    config = get_llm_config()
    client = NanoGPTClient(
        api_key=config.nanogpt_api_key,
        base_url=config.nanogpt_base_url,
    )

    prompt = TOOL_RESPONSE_PROMPT.format(
        query=query,
        tool_name=tool_name,
        tool_result=json.dumps(tool_result, indent=2, ensure_ascii=False)[:2000],
    )

    request = LLMRequest(
        model=config.model_agentic,  # GLM-4.7-Thinking per formattazione
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=512,
    )

    try:
        response = await client.generate_response(request)
        return response.content or "Non sono riuscito a formattare la risposta."
    except Exception as e:
        logger.error("response_formatting_failed", error=str(e))
        # Fallback: restituisci risultato grezzo
        if tool_result.get("success"):
            return f"Risultato da {tool_name}: {json.dumps(tool_result.get('result', {}), ensure_ascii=False)}"
        else:
            return f"Errore nell'esecuzione di {tool_name}: {tool_result.get('error', 'Errore sconosciuto')}"


async def run_tool_agent(
    tenant_id: str,
    query: str,
    query_embedding: list[float] | None = None,
) -> dict[str, Any]:
    """Esegue il ciclo completo del tool agent.

    Args:
        tenant_id: ID tenant
        query: Query utente
        query_embedding: Embedding pre-calcolato (opzionale)

    Returns:
        {
            "used_tool": bool,
            "tool_name": str | None,
            "tool_result": dict | None,
            "formatted_response": str | None,
        }
    """
    # Step 1: Cerca tool candidati
    candidates = await search_candidate_tools(
        tenant_id=tenant_id,
        query=query,
        query_embedding=query_embedding,
        limit=5,
    )

    if not candidates:
        return {
            "used_tool": False,
            "tool_name": None,
            "tool_result": None,
            "formatted_response": None,
        }

    # Step 2: Approccio deterministico - se score alto, usa tool direttamente
    # (L'LLM decision è troppo inaffidabile con output JSON)
    best_candidate = candidates[0]
    best_score = best_candidate["score"]

    # Se score > 0.55 e nome contiene keyword rilevanti, usa tool
    tool_keywords = [
        # Crypto
        "price",
        "crypto",
        "coin",
        "bitcoin",
        "ethereum",
        "btc",
        "eth",
        "coingecko",
        "trending",
        # Finance/Trading
        "stock",
        "forex",
        "quote",
        "market",
        "equity",
        "portfolio",
        "position",
        "trade",
        "alpaca",
        "hyperliquid",
        "finnhub",
        "polygon",
        "alphavantage",
        "twelvedata",
        "fred",
        "gdp",
        "economic",
        "inflation",
        "unemployment",
        "edgar",
        "sec",
        "filing",
        "yahoo",
        "finance",
        # Weather/Geo
        "weather",
        "meteo",
        "forecast",
        "temperatura",
        "temperature",
        "rain",
        "sun",
        "geocode",
        "coordinates",
        "latitude",
        "longitude",
        "nominatim",
        "sunrise",
        "sunset",
        "country",
        "paese",
        "paesi",
        "countries",
        "capital",
        "population",
        "currency",
        "holiday",
        "holidays",
        "festività",
        "festivo",
        "earthquake",
        "terremoto",
        "seismic",
        "usgs",
        # Search
        "search",
        "cerca",
        "ricerca",
        "find",
        "google",
        "duckduckgo",
        "web",
        # News
        "news",
        "notizie",
        "hackernews",
        "hacker",
        "article",
        "articles",
        # Encyclopedia
        "wikipedia",
        "wiki",
        "encyclopedia",
        "book",
        "books",
        "library",
        "isbn",
        "openlibrary",
        # Science/Academia
        "paper",
        "papers",
        "research",
        "citation",
        "doi",
        "arxiv",
        "pubmed",
        "crossref",
        "semantic",
        "scholar",
        "openalex",
        "europepmc",
        "abstract",
        "journal",
        # Medical
        "drug",
        "farmaco",
        "medicine",
        "medication",
        "rxnorm",
        "rxcui",
        "interaction",
        "icite",
        "nih",
        "clinical",
        "medical",
        # Utility
        "age",
        "età",
        "gender",
        "genere",
        "name",
        "nome",
        "agify",
        "genderize",
        "random",
        "user",
        "fake",
        "mock",
        "ip",
        "address",
        "ipify",
        "public",
        # NASA/Space
        "nasa",
        "apod",
        "astronomy",
        "asteroid",
        "neo",
        "space",
        "image",
        # Google Workspace
        "google",
        "gmail",
        "email",
        "mail",
        "inbox",
        "message",
        "drive",
        "folder",
        "file",
        "document",
        "spreadsheet",
        "presentation",
        "calendar",
        "event",
        "meeting",
        "appointment",
        "schedule",
        "agenda",
    ]
    name_lower = best_candidate["name"].lower()
    has_relevant_keyword = any(kw in name_lower for kw in tool_keywords)

    should_use_tool = best_score > 0.55 and has_relevant_keyword

    logger.info(
        "tool_decision_heuristic",
        best_tool=best_candidate["name"],
        best_score=round(best_score, 3),
        has_keyword=has_relevant_keyword,
        will_use=should_use_tool,
    )

    if not should_use_tool:
        return {
            "used_tool": False,
            "tool_name": None,
            "tool_result": None,
            "formatted_response": None,
            "decision_reason": f"Score {best_score:.2f} or no keyword match",
        }

    # Step 3: Esegui tool (usa best_candidate direttamente)
    tool_id = best_candidate["tool_id"]
    tool_name = best_candidate["name"]
    arguments = {}  # Gli argomenti verranno estratti dal tool executor

    tool_result = await execute_tool(tool_id, tool_name, arguments)

    # Step 4: Formatta risposta
    formatted_response = await format_tool_response(query, tool_name, tool_result)

    return {
        "used_tool": True,
        "tool_name": tool_name,
        "tool_id": tool_id,
        "tool_arguments": arguments,
        "tool_result": tool_result,
        "formatted_response": formatted_response,
    }
