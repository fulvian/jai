"""Cognitive Pipeline - Pipeline Cognitiva Unificata.

Pipeline Ottimale (Benchmark Perplexity Gennaio 2026):
1. Routing + Tool Calling (Kimi K2.5) - 100 sub-agent, reasoning superiore
2. Sintesi Finale (DeepSeek V3.2 Speciale) - Reasoning = Gemini 3.0 Pro
3. Memory Learning - Salvataggio in knowledge base

Modular Architecture (v2.0):
- Se USE_MODULAR_ARCHITECTURE=True, delega a domain handlers
- Fallback automatico a logica legacy se handler non disponibile
- Circuit breaker e timeout protection per domini

Usage:
    from me4brain.core.cognitive_pipeline import run_cognitive_pipeline

    result = await run_cognitive_pipeline(
        tenant_id="my_tenant",
        user_id="user_123",
        query="correlazione tra Apple e Bitcoin"
    )
"""

import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import structlog

from me4brain.embeddings import get_embedding_service
from me4brain.llm import LLMRequest, Message, NanoGPTClient, get_llm_config
from me4brain.memory import get_episodic_memory
from me4brain.retrieval.tool_executor import ExecutionRequest, ToolExecutor

logger = structlog.get_logger(__name__)

# =============================================================================
# Architecture Configuration
# =============================================================================

# Flag per abilitare architettura modulare (Brain as a Service)
# Set via env var o default True per nuova architettura
USE_MODULAR_ARCHITECTURE = os.getenv("ME4BRAIN_USE_MODULAR", "true").lower() == "true"

# DEPRECATED: Flag per legacy fallback (default False - architettura modulare esclusiva)
# Legacy fallback path has been removed (Phase 3 cleanup).

# Costanti
MAX_TOOL_ITERATIONS = 10
MIN_TOOL_SCORE = 0.45


# =============================================================================
# Utility: Robust JSON Parsing
# =============================================================================


def _parse_json_response(content: str) -> dict | None:
    """Parse JSON da risposta LLM con fallback robusti.

    Gestisce:
    - Markdown code blocks (```json ... ```)
    - Whitespace e newlines
    - JSON parziale con regex extraction
    - Testo prima/dopo il JSON

    Returns:
        dict se parsing riuscito, None altrimenti
    """
    import re

    if not content or not content.strip():
        return None

    content = content.strip()

    # 1. Prova parsing diretto (risposta pulita)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # 2. Rimuovi markdown code blocks
    if "```json" in content:
        try:
            json_part = content.split("```json")[1].split("```")[0]
            return json.loads(json_part.strip())
        except (IndexError, json.JSONDecodeError):
            pass

    if "```" in content:
        try:
            json_part = content.split("```")[1].split("```")[0]
            return json.loads(json_part.strip())
        except (IndexError, json.JSONDecodeError):
            pass

    # 3. Estrai JSON con regex (trova primo oggetto {...})
    json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
    matches = re.findall(json_pattern, content, re.DOTALL)

    for match in matches:
        try:
            result = json.loads(match)
            if isinstance(result, dict) and "intent" in result:
                return result
        except json.JSONDecodeError:
            continue

    # 4. Nessun JSON valido trovato
    logger.debug("json_parse_failed", content_preview=content[:200])
    return None


# =============================================================================
# Prompt Templates
# =============================================================================

QUERY_ANALYSIS_PROMPT = """Analizza query utente e identifica TUTTI i domini necessari.

QUERY: {query}

RISPONDI ESCLUSIVAMENTE CON JSON VALIDO. NESSUN TESTO PRIMA O DOPO IL JSON.

{{
    "intent": "descrizione sintetica",
    "domains_required": ["geo_weather", "finance_crypto"],
    "entities": [
        {{"type": "location", "value": "Roma", "target_domain": "geo_weather"}},
        {{"type": "financial_instrument", "value": "BTC", "target_domain": "finance_crypto"}}
    ],
    "execution_strategy": "parallel",
    "requires_tools": true,
    "data_needs": [
        {{"type": "weather", "entity": "Roma", "query": "meteo Roma"}}
    ]
}}

DOMINI DISPONIBILI:
geo_weather, finance_crypto, sports_nba, medical, travel, jobs, food,
entertainment, tech_coding, google_workspace, knowledge_media,
science_research, utility, web_search

MAPPING ENTITÀ → DOMINIO:
- "location" (città, paesi) → geo_weather, travel
- "financial_instrument" (BTC, AAPL) → finance_crypto
- "organization" (Lakers, Celtics) → sports_nba
- "person" (atleti, celebrities) → sports_nba, knowledge_media
- "medical_condition" → medical
- "query_text" (ricerche) → google_workspace, web_search

REGOLE:
- domains_required: TUTTI i domini necessari per rispondere
- entities: ogni entità con target_domain corretto
- execution_strategy: "parallel" (default), "sequential" (tool chaining)
- Analisi cross-domain (confronti, correlazioni) → più domini

ESEMPI:
Query: "Confronta BTC con meteo Milano"
→ domains_required: ["finance_crypto", "geo_weather"]

Query: "Statistiche Lakers e quote scommesse"
→ domains_required: ["sports_nba"] (stesso dominio gestisce entrambi)

⚠️ OUTPUT: SOLO JSON, NIENTE ALTRO. NO markdown, NO commenti.
"""

THINKING_SYNTHESIS_PROMPT = """L'utente ha chiesto: "{query}"

PIANO DI ANALISI:
{analysis_plan}

═══════════════════════════════════════════════════════════════════
⚠️ DATI RACCOLTI - FONTE UNICA DI VERITÀ ⚠️
═══════════════════════════════════════════════════════════════════
{collected_data}

MEMORIA CONTESTUALE:
{memory_context}

═══════════════════════════════════════════════════════════════════
REGOLE OBBLIGATORIE (NESSUNA ECCEZIONE)
═══════════════════════════════════════════════════════════════════

1. **DATI NUMERICI**: Ogni numero che citi (prezzi, quote, statistiche, percentuali,
   temperature, punteggi) DEVE essere COPIATO ESATTAMENTE dal JSON sopra.
   - NON arrotondare
   - NON inventare
   - NON stimare

2. **DATI MANCANTI**: Se un dato richiesto NON è presente nel JSON sopra,
   scrivi ESPLICITAMENTE: "Questo dato non è disponibile nei dati raccolti."
   NON inventare valori per riempire lacune.

3. **CITAZIONE FONTI**: Per ogni dato numerico, indica la fonte:
   - "(fonte: [nome_tool])" o "(da [FONTE] nel JSON)"

4. **NOMI E IDENTIFICATORI**: Copia esattamente nomi di persone, squadre,
   aziende, luoghi come appaiono nel JSON. Non modificarli.

5. **STRUTTURA TABELLARE**: Quando presenti dati comparativi, usa tabelle
   con valori ESATTI dal JSON.

═══════════════════════════════════════════════════════════════════

ISTRUZIONI RISPOSTA:
1. Includi TUTTI i dati raccolti da ciascun tool
2. Analizza e sintetizza il contenuto in modo professionale
3. Se dati da più fonti, fai cross-reference
4. Rispondi in italiano, in modo completo e dettagliato

RICORDA: La tua risposta sarà verificata contro il JSON. Numeri non presenti
nel JSON verranno segnalati come errore."""


# =============================================================================
# SEMANTIC-FIRST: Argument Extraction Prompt
# =============================================================================

ARGUMENT_EXTRACTION_PROMPT = """Estrai gli argomenti per questo tool dalla query utente.

TOOL: {tool_name}
DESCRIZIONE: {tool_description}
PARAMETRI RICHIESTI:
{parameters_schema}

QUERY UTENTE: "{user_query}"

ISTRUZIONI:
1. Estrai SOLO i valori per i parametri elencati sopra
2. Se un parametro è richiesto ma non presente nella query, usa un valore ragionevole
3. Rispondi SOLO con un oggetto JSON valido, senza commenti o spiegazioni
4. NON inventare parametri che non sono nella lista

ESEMPIO:
Per un tool "google_drive_search" con parametro "query", dalla query "cerca documenti Allumiere":
{{"query": "Allumiere"}}

Rispondi SOLO con il JSON:"""

# =============================================================================
# Query Analyzer (Kimi K2.5)
# =============================================================================


async def analyze_query(
    query: str,
    llm_client: NanoGPTClient,
    config: Any,
) -> dict[str, Any]:
    """Analizza la query con LLM per creare piano di ricerca.

    Implementa:
    - Exponential backoff per retry
    - max_tokens aumentato (reasoning models consumano 3-5x)
    - temperature 0.0 per output deterministico
    - Logging diagnostico per debug
    """
    import asyncio

    prompt = QUERY_ANALYSIS_PROMPT.format(
        query=query,
        max_iterations=MAX_TOOL_ITERATIONS,
    )

    # Pipeline Ottimale: Kimi K2.5 per routing + tool calling
    # Kimi K2.5: 100 sub-agent, reasoning superiore per intent classification
    request = LLMRequest(
        model=config.model_agentic,  # Kimi K2.5 per routing
        messages=[Message(role="user", content=prompt)],
        temperature=0.0,  # Deterministico per JSON parsing
        max_tokens=4096,  # Alto per risposte complete
    )

    max_retries = 3
    base_delay = 1.0
    last_error = None

    for attempt in range(max_retries):
        try:
            # Exponential backoff
            if attempt > 0:
                delay = min(base_delay * (2 ** (attempt - 1)), 10.0)
                logger.debug("llm_retry_backoff", attempt=attempt + 1, delay_seconds=delay)
                await asyncio.sleep(delay)

            response = await llm_client.generate_response(request)
            content = response.content or ""

            # Logging diagnostico per debug empty responses
            logger.debug(
                "llm_response_diagnostic",
                attempt=attempt + 1,
                content_length=len(content),
                has_content=bool(content.strip()),
                finish_reason=getattr(response, "finish_reason", "unknown"),
                model=config.model_agentic,  # Kimi per routing
            )

            if not content.strip():
                logger.debug("llm_empty_response", attempt=attempt + 1)
                continue  # Retry con backoff

            # Parsing JSON robusto
            analysis = _parse_json_response(content)

            if analysis:
                # POST-PROCESSING: Applica euristiche per completare output
                analysis = _apply_heuristic_fallback(query, analysis)

                logger.info(
                    "query_analyzed",
                    intent=analysis.get("intent", "")[:50],
                    requires_tools=analysis.get("requires_tools"),
                    data_needs_count=len(analysis.get("data_needs", [])),
                )
                return analysis
            else:
                # JSON parsing fallito ma content non vuoto
                logger.debug(
                    "json_parse_failed_retry", attempt=attempt + 1, content_preview=content[:100]
                )

        except Exception as e:
            last_error = e
            logger.debug("query_analysis_attempt_failed", attempt=attempt + 1, error=str(e))

    # Tutti i tentativi falliti - usa fallback con warning (non error, è gestito)
    logger.warning(
        "query_analysis_fallback_used",
        error=str(last_error) if last_error else "empty_response",
        total_attempts=max_retries,
    )
    return _apply_heuristic_fallback(query, {})


def _apply_heuristic_fallback(query: str, analysis: dict) -> dict:
    """Applica euristiche per correggere o completare l'analisi LLM."""
    query_lower = query.lower()

    # Keywords per tipo di dato
    crypto_kw = ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana"]
    finance_kw = [
        "apple",
        "aapl",
        "google",
        "googl",
        "microsoft",
        "msft",
        "tesla",
        "tsla",
        "azioni",
        "stock",
    ]
    weather_kw = ["meteo", "tempo", "weather", "temperatura"]
    macro_kw = ["gdp", "inflazione", "inflation", "disoccupazione", "unemployment"]

    # Trigger per multi-tool
    correlation_kw = [
        "correlazione",
        "correlation",
        "confronto",
        "compare",
        "relazione",
        "vs",
        "versus",
    ]

    # Trigger per query STORICHE/TEMPORALI
    historical_kw = [
        "storico",
        "storica",
        "storia",
        "historical",
        "ultimo anno",
        "ultimi anni",
        "ultimi mesi",
        "ultimi 2 anni",
        "1 anno",
        "2 anni",
        "5 anni",
        "andamento",
        "trend",
        "nel tempo",
        "over time",
        "past year",
        "last year",
    ]

    has_crypto = any(kw in query_lower for kw in crypto_kw)
    has_finance = any(kw in query_lower for kw in finance_kw)
    has_weather = any(kw in query_lower for kw in weather_kw)
    has_macro = any(kw in query_lower for kw in macro_kw)
    has_correlation = any(kw in query_lower for kw in correlation_kw)
    has_historical = any(kw in query_lower for kw in historical_kw)

    # Se analysis è vuota o incompleta, ricostruiscila
    if not analysis.get("data_needs") or not analysis.get("requires_tools"):
        data_needs = []
        entities = []

        if has_crypto:
            coin = "bitcoin" if "bitcoin" in query_lower or "btc" in query_lower else "ethereum"
            if has_historical:
                # Usa tool storico
                data_needs.append(
                    {
                        "type": "crypto_history",
                        "entity": coin,
                        "query": f"storico prezzi {coin} ultimi 2 anni",
                    }
                )
            else:
                data_needs.append({"type": "crypto", "entity": coin, "query": f"prezzo {coin}"})
            entities.append(coin.capitalize())

        if has_finance:
            stock = "Apple" if "apple" in query_lower else "Google"
            if "microsoft" in query_lower:
                stock = "Microsoft"
            elif "tesla" in query_lower:
                stock = "Tesla"
            if has_historical:
                # Usa tool storico
                data_needs.append(
                    {
                        "type": "finance_history",
                        "entity": stock,
                        "query": f"storico prezzi azioni {stock} ultimi 2 anni",
                    }
                )
            else:
                data_needs.append(
                    {"type": "finance", "entity": stock, "query": f"prezzo azioni {stock}"}
                )
            entities.append(stock)

        if has_weather:
            data_needs.append({"type": "weather", "entity": "default", "query": "meteo attuale"})

        if has_macro:
            series = "GDP" if "gdp" in query_lower else "inflation"
            data_needs.append({"type": "macro", "entity": series, "query": f"dati {series}"})

        # Fallback generico se nessun match
        if not data_needs:
            data_needs = [{"type": "general", "entity": "", "query": query}]

        analysis["data_needs"] = data_needs
        analysis["entities"] = entities if entities else analysis.get("entities", [])
        analysis["requires_tools"] = True

    # Imposta analysis_type
    if has_correlation or (has_crypto and has_finance):
        analysis["analysis_type"] = "correlation"
    elif not analysis.get("analysis_type"):
        analysis["analysis_type"] = "simple"

    # Imposta intent se mancante
    if not analysis.get("intent"):
        analysis["intent"] = query[:100]

    # Imposta requires_memory se non presente
    if analysis.get("requires_memory") is None:
        analysis["requires_memory"] = False

    return analysis


# =============================================================================
# SEMANTIC-FIRST: Tool Selection + Argument Extraction
# =============================================================================


async def extract_arguments_with_llm(
    user_query: str,
    tool_name: str,
    tool_description: str,
    tool_parameters: dict[str, Any],
    llm_client: NanoGPTClient,
    config: Any,
) -> dict[str, Any]:
    """Estrae argomenti dalla query utente usando LLM.

    Approccio semantic-first: l'LLM vede il tool specifico e i suoi parametri,
    ed estrae i valori corretti dalla query senza classificazioni error-prone.
    """
    # Costruisci schema parametri leggibile
    params_schema = []
    for param_name, param_info in tool_parameters.items():
        if isinstance(param_info, dict):
            param_type = param_info.get("type", "string")
            required = param_info.get("required", False)
            desc = param_info.get("description", "")
            default = param_info.get("default")

            line = f"- {param_name} ({param_type})"
            if required:
                line += " [RICHIESTO]"
            if desc:
                line += f": {desc}"
            if default is not None:
                line += f" (default: {default})"
            params_schema.append(line)

    prompt = ARGUMENT_EXTRACTION_PROMPT.format(
        tool_name=tool_name,
        tool_description=tool_description,
        parameters_schema="\n".join(params_schema) if params_schema else "(nessun parametro)",
        user_query=user_query,
    )

    from me4brain.llm.provider_factory import get_tool_calling_client

    tc_client = get_tool_calling_client()
    model = config.ollama_model if config.use_local_tool_calling else config.model_agentic

    request = LLMRequest(
        model=model,  # Usa modello locale per estrazione argomenti se abilitato
        messages=[Message(role="user", content=prompt)],
        temperature=0.0,  # Deterministic
        max_tokens=256,
    )

    try:
        response = await tc_client.generate_response(request)
        content = response.content or "{}"

        # Pulisci markdown se presente
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        arguments = json.loads(content)
        logger.info("llm_arguments_extracted", tool=tool_name, arguments=arguments)
        return arguments

    except json.JSONDecodeError as e:
        logger.warning("llm_arguments_parse_failed", tool=tool_name, error=str(e))
        return {}
    except Exception as e:
        logger.error("llm_arguments_failed", tool=tool_name, error=str(e))
        return {}


# =============================================================================
# ReAct Agent Loop (Reason + Act + Observe Pattern)
# =============================================================================


async def react_agent_loop(
    tenant_id: str,
    user_id: str,
    query: str,
    analysis: dict[str, Any],
    llm_client: NanoGPTClient,
    config: Any,
    max_iterations: int = 3,
) -> list[dict[str, Any]]:
    """ReAct Agent Loop - Iterazione intelligente con retry e failure handling.

    Implementa il paradigma ReAct (Reason + Act + Observe):
    1. REASON: Analizza stato corrente e decidi prossima azione
    2. ACT: Esegui tool/domini necessari
    3. OBSERVE: Valuta risultati e aggiorna stato
    4. REPEAT: Se non soddisfatto, itera

    Features:
    - Retry automatico su tool failures
    - Circuit breaker integration per fail-fast
    - Robust entity validation
    - Graceful degradation se alcuni domini falliscono

    Args:
        tenant_id: ID tenant
        user_id: ID utente
        query: Query originale
        analysis: Risultato di analyze_query()
        llm_client: Client LLM per reasoning
        config: LLM config
        max_iterations: Max iterazioni (default 3)

    Returns:
        Lista dati raccolti dai tool
    """
    from me4brain.core.circuit_breaker import get_circuit_breaker
    from me4brain.core.modular_orchestrator import try_modular_execution
    from me4brain.core.nlp_utils import robust_entity_extraction

    collected_data: list[dict[str, Any]] = []
    domains_completed: set[str] = set()
    domains_failed: dict[str, int] = {}  # domain -> failure count

    # Valida e pulisci entities
    original_entities = analysis.get("entities", [])
    validated_entities = robust_entity_extraction(query, original_entities)
    analysis["entities"] = validated_entities

    domains_required = set(analysis.get("domains_required", []))

    if not domains_required:
        logger.debug("react_no_domains_required", query_preview=query[:50])
        return collected_data

    logger.info(
        "react_loop_started",
        domains_required=list(domains_required),
        max_iterations=max_iterations,
        validated_entities=len(validated_entities),
    )

    for iteration in range(max_iterations):
        # =====================================================================
        # STEP 1: REASON - Quali domini devo ancora eseguire?
        # =====================================================================
        pending_domains = domains_required - domains_completed

        if not pending_domains:
            logger.info(
                "react_all_domains_completed",
                iteration=iteration,
                total_collected=len(collected_data),
            )
            break

        # Filtra domini con circuit breaker aperto
        executable_domains = []
        for domain in pending_domains:
            breaker = get_circuit_breaker(domain)
            if breaker.is_open():
                logger.warning(
                    "react_circuit_breaker_open",
                    domain=domain,
                    skipping=True,
                )
                domains_completed.add(domain)  # Skip, non ritentare
            else:
                executable_domains.append(domain)

        if not executable_domains:
            logger.warning(
                "react_no_executable_domains",
                iteration=iteration,
                all_breakers_open=True,
            )
            break

        logger.info(
            "react_iteration_start",
            iteration=iteration + 1,
            pending_domains=executable_domains,
        )

        # =====================================================================
        # STEP 2: ACT - Esegui domini pending
        # =====================================================================
        try:
            # Crea analysis filtrata solo per domini pending
            filtered_analysis = {
                **analysis,
                "domains_required": executable_domains,
                "entities": [
                    e for e in validated_entities if e.get("target_domain") in executable_domains
                ],
            }

            modular_success, modular_results = await try_modular_execution(
                tenant_id=tenant_id,
                user_id=user_id,
                query=query,
                analysis=filtered_analysis,
            )

            # =====================================================================
            # STEP 3: OBSERVE - Analizza risultati
            # =====================================================================
            if modular_success and modular_results:
                for result in modular_results:
                    domain = result.get("_domain", "unknown")
                    success = result.get("success", False)

                    breaker = get_circuit_breaker(domain)

                    if success:
                        # Successo: aggiungi ai dati, reset circuit breaker
                        collected_data.append(result)
                        domains_completed.add(domain)
                        breaker.record_success()

                        logger.debug(
                            "react_domain_success",
                            domain=domain,
                            iteration=iteration + 1,
                        )
                    else:
                        # Failure: conta e potenzialmente ritenta
                        breaker.record_failure()
                        domains_failed[domain] = domains_failed.get(domain, 0) + 1

                        # Max 2 retry per dominio
                        if domains_failed[domain] >= 2:
                            domains_completed.add(domain)  # Stop retrying
                            logger.warning(
                                "react_domain_max_retries",
                                domain=domain,
                                failures=domains_failed[domain],
                            )
                        else:
                            logger.info(
                                "react_domain_will_retry",
                                domain=domain,
                                attempt=domains_failed[domain],
                            )
            else:
                # Modular execution totalmente fallita
                logger.warning(
                    "react_modular_execution_failed",
                    iteration=iteration + 1,
                )

        except Exception as e:
            logger.error(
                "react_iteration_error",
                iteration=iteration + 1,
                error=str(e),
            )

        # =====================================================================
        # STEP 4: Check se abbiamo abbastanza dati (early exit)
        # =====================================================================
        success_rate = len(collected_data) / len(domains_required) if domains_required else 0

        if success_rate >= 0.5:
            # Almeno 50% dei domini hanno dati, possiamo sintetizzare
            logger.info(
                "react_sufficient_data",
                success_rate=success_rate,
                collected=len(collected_data),
                required=len(domains_required),
            )
            # Non fare break qui, lascia completare se ci sono altri pending

    logger.info(
        "react_loop_completed",
        iterations_used=min(iteration + 1, max_iterations),
        domains_completed=list(domains_completed),
        domains_failed=list(domains_failed.keys()),
        total_collected=len(collected_data),
    )

    return collected_data


async def execute_semantic_tool_loop(
    tenant_id: str,
    user_id: str,
    user_query: str,
    executor: ToolExecutor,
    embedding_service: Any,
    llm_client: NanoGPTClient,
    config: Any,
    max_tools: int = 5,
    analysis: dict[str, Any] | None = None,  # Riuso analysis esistente
) -> list[dict[str, Any]]:
    """Esegue tool in loop usando approccio SEMANTIC-FIRST con supporto MULTI-TOOL.

    Architettura v2.0 (Brain as a Service):
    1. Se USE_MODULAR_ARCHITECTURE=True, tenta prima i domain handlers
    2. Se nessun handler matched, usa logica legacy
    3. Circuit breaker e timeout protection per domini

    Supporta query che richiedono più tool simultaneamente (cross-analysis):
    1. Rileva se query richiede multi-tool (es. "Drive, Gmail e Calendar")
    2. Cerca tool multipli nel vector store
    3. Estrai argomenti per ciascun tool
    4. Esegui tutti i tool in parallelo con asyncio.gather

    Args:
        analysis: Opzionale. Se fornito, evita doppia chiamata LLM.

    Returns:
        Lista di risultati raccolti (massimo max_tools)
    """
    # ==========================================================================
    # STEP 0: Try Modular Architecture (Brain as a Service)
    # ==========================================================================
    if USE_MODULAR_ARCHITECTURE:
        from me4brain.core.modular_orchestrator import try_modular_execution

        # ANALISI LLM COMPLETA: ottiene domains_required[], entities con target_domain
        # Riusa analysis se già fornita per evitare doppia chiamata LLM
        if analysis is None:
            try:
                analysis = await analyze_query(user_query, llm_client, config)
                logger.debug(
                    "multi_domain_analysis",
                    domains_required=analysis.get("domains_required", []),
                    entities_count=len(analysis.get("entities", [])),
                )
            except Exception as e:
                # Fallback a analisi minimale se LLM fallisce
                logger.warning("analyze_query_failed_fallback", error=str(e))
                analysis = {
                    "entities": _extract_entities_for_routing(user_query),
                    "requires_tools": True,
                }
        else:
            logger.debug(
                "reusing_existing_analysis",
                domains_required=analysis.get("domains_required", []),
            )

        modular_success, modular_results = await try_modular_execution(
            tenant_id=tenant_id,
            user_id=user_id,
            query=user_query,
            analysis=analysis,
        )

        if modular_success and modular_results:
            logger.info(
                "modular_architecture_used",
                results_count=len(modular_results),
                domains=[r.get("_domain") for r in modular_results],
                multi_domain=len(analysis.get("domains_required", [])) > 1,
            )
            return modular_results

        # Fallback: nessun handler modulare, usa logica legacy
        logger.debug(
            "modular_fallback_to_legacy",
            query_preview=user_query[:50],
        )

    # ==========================================================================
    # DEPRECATED LEGACY PATH
    # ==========================================================================
    # Questo blocco implementa il vecchio flusso via Qdrant semantic search
    # e handler inline in tool_executor.py. Mantenuto per:
    # - Backward compatibility (abilitare con ME4BRAIN_LEGACY_FALLBACK=true)
    # - Riferimento ai pattern ottimizzati (Google Workspace, NBA chained)
    # - Debugging in caso di problemi con architettura modulare
    # ==========================================================================
    # Legacy fallback path has been removed (Phase 3 cleanup)
    # No domain handler matched this query
    # ==========================================================================
    logger.warning(
        "no_domain_handler_found",
        query_preview=user_query[:50],
    )
    return [
        {
            "success": False,
            "error": "No domain handler found for this query",
            "query": user_query[:100],
        }
    ]


# =============================================================================
# DEPRECATED: Legacy Helper Functions
# =============================================================================
# Le seguenti funzioni sono usate solo dal legacy path.
# Mantenute per riferimento ai pattern ottimizzati (Google, NBA).
# =============================================================================


def _detect_multi_tool_services(query: str) -> list[str]:
    """DEPRECATED: Rileva se la query richiede più servizi/tool.

    Usata solo dal legacy path (USE_LEGACY_FALLBACK=true).
    Pattern ottimizzati per Google Workspace e NBA mantenuti per riferimento.

    Returns:
        Lista di keyword per i servizi rilevati, vuota se singolo tool.
    """
    query_lower = query.lower()

    # Mappa servizi → keyword per ricerca semantica
    service_patterns = {
        # Google Workspace
        "drive": ["google drive", "drive", "gdrive", "documenti drive", "file drive"],
        "gmail": ["gmail", "email", "mail", "posta", "messaggi email"],
        "calendar": ["calendar", "calendario", "eventi", "appuntamenti", "meeting"],
        "meet": ["meet", "call", "videochiamate", "riunioni video"],
        "docs": ["docs", "documenti google", "google docs"],
        "sheets": ["sheets", "fogli", "spreadsheet", "excel google"],
        # NBA / Sports
        "nba_games": [
            "partita nba",
            "partite nba",
            "prossima partita",
            "match nba",
            "nba game",
            "calendario nba",
            "programma nba",
        ],
        "nba_stats": [
            "statistiche nba",
            "stats nba",
            "statistiche giocatore",
            "punti rimbalzi",
            "statistiche squadra",
            "ultimi 5 incontri",
        ],
        "nba_injuries": [
            "infortuni",
            "injuries",
            "roster",
            "infortunati",
            "out",
            "doubtful",
            "questionable",
        ],
        "nba_odds": [
            "quote",
            "scommesse",
            "odds",
            "betting",
            "bookmaker",
            "bet365",
            "snai",
            "probabile vincita",
            "quota",
        ],
        "nba_news": ["notizie nba", "news nba", "rumors", "trades", "ultime nba"],
        # Finance
        "crypto": ["bitcoin", "ethereum", "crypto", "criptovalute", "btc", "eth"],
        "stocks": ["azioni", "stock", "borsa", "mercato azionario", "titoli"],
        "forex": ["forex", "valute", "cambio", "eur/usd"],
    }

    detected = []
    for service, keywords in service_patterns.items():
        for kw in keywords:
            if kw in query_lower:
                detected.append(service)
                break

    # SPECIAL CASE: Trigger per "analisi completa" in qualsiasi dominio sportivo
    # Pattern generico: [analisi/pronostico] + [sport_keyword] + [vs/contro/partita]
    complete_analysis_triggers = [
        "analisi partita",
        "analisi completa",
        "analisi dettagliata",
        "pronostico",
        "preview",
        "formazioni",
        "consigli scommesse",
    ]

    # Se query contiene trigger analisi completa E almeno un servizio sport rilevato
    has_complete_trigger = any(trigger in query_lower for trigger in complete_analysis_triggers)
    has_sports_service = any(svc.startswith("nba_") for svc in detected)

    # Se è analisi completa sport, aggiungi tutti i tool correlati dello stesso dominio
    if has_complete_trigger and has_sports_service:
        sports_tools = ["nba_games", "nba_stats", "nba_injuries", "nba_odds"]
        for tool in sports_tools:
            if tool not in detected:
                detected.append(tool)

    # Pattern generico per statistiche: forza nba_stats quando si chiedono stats
    stats_keywords = ["statistiche", "stats", "punti", "rimbalzi", "assist", "media", "average"]
    if any(kw in query_lower for kw in stats_keywords) and has_sports_service:
        if "nba_stats" not in detected:
            detected.append("nba_stats")

    # Ritorna solo se > 1 servizio rilevato (altrimenti usa flusso singolo)
    return detected if len(detected) > 1 else []


async def _execute_multi_tool_parallel(
    tenant_id: str,
    user_id: str,
    user_query: str,
    service_keywords: list[str],
    executor: ToolExecutor,
    embedding_service: Any,
    llm_client: NanoGPTClient,
    config: Any,
    procedural: Any,
    max_tools: int,
) -> list[dict[str, Any]]:
    """Esegue più tool in parallelo per cross-analysis."""
    import asyncio

    # Costruisci query specifiche per ogni servizio (per ricerca semantica in Qdrant)
    service_queries = {
        # Google Workspace
        "drive": "Google Drive cerca file documenti",
        "gmail": "Gmail cerca email messaggi",
        "calendar": "Google Calendar cerca eventi testo query ricerca",
        "meet": "Google Meet videochiamate riunioni",
        "docs": "Google Docs documenti testo",
        "sheets": "Google Sheets fogli calcolo spreadsheet",
        # NBA / Sports
        "nba_games": "NBA prossime partite programmate schedule BallDontLie",
        "nba_stats": "NBA live scoreboard partite oggi statistiche squadre nba_api",
        "nba_injuries": "NBA infortuni giocatori injuries ESPN roster",
        "nba_odds": "NBA quote scommesse betting odds bookmaker The Odds API",
        "nba_news": "NBA notizie news DuckDuckGo web search",
        # Finance
        "crypto": "Bitcoin Ethereum crypto prezzo CoinGecko",
        "stocks": "azioni stock borsa Yahoo Finance prezzo",
        "forex": "forex valute cambio tasso",
    }

    # Estrai l'entità/termine di ricerca dalla query originale
    search_term = _extract_search_term_from_query(user_query)

    async def find_and_execute_tool(service: str) -> dict[str, Any]:
        """Trova ed esegue un singolo tool per il servizio."""
        search_query = service_queries.get(service, f"Google {service}")
        query_embedding = embedding_service.embed_query(search_query)

        try:
            results = await procedural.search_tools_in_qdrant(
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                limit=1,
                min_score=MIN_TOOL_SCORE,
            )
        except Exception as e:
            logger.warning("multi_tool_search_failed", service=service, error=str(e))
            return {"service": service, "success": False, "error": str(e)}

        if not results:
            return {"service": service, "success": False, "error": f"No tool found for {service}"}

        tool_id, tool_payload, tool_score = results[0]
        tool_name = tool_payload.get("name", "unknown")

        logger.info(
            "multi_tool_found",
            service=service,
            tool_name=tool_name,
            score=round(tool_score, 3),
        )

        # Costruisci query con termine di ricerca per l'estrazione argomenti
        query_for_args = f"cerca {search_term} su {service}" if search_term else user_query

        return await _execute_single_tool(
            tenant_id=tenant_id,
            user_id=user_id,
            user_query=query_for_args,
            tool_id=tool_id,
            tool_payload=tool_payload,
            tool_score=tool_score,
            executor=executor,
            llm_client=llm_client,
            config=config,
            fallback_query_arg=search_term,  # Passa termine per fallback
        )

    # Esegui tutti i tool in parallelo
    tasks = [find_and_execute_tool(svc) for svc in service_keywords[:max_tools]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    collected_data = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            collected_data.append(
                {
                    "service": service_keywords[i],
                    "success": False,
                    "error": str(result),
                }
            )
        else:
            collected_data.append(result)

    logger.info(
        "multi_tool_execution_complete",
        total=len(collected_data),
        successful=sum(1 for r in collected_data if r.get("success", False)),
    )

    return collected_data


def _extract_entities_for_routing(query: str) -> list[str]:
    """Estrae entità dalla query per routing a domain handlers.

    Usato per creare analisi minimale quando si tenta esecuzione modulare.
    Non richiede LLM, usa pattern matching veloce.

    Returns:
        Lista di entità rilevate (nomi squadre, giocatori, servizi, etc.)
    """

    entities = []
    query_lower = query.lower()

    # Pattern per NBA
    nba_teams = [
        "lakers",
        "celtics",
        "warriors",
        "bulls",
        "heat",
        "knicks",
        "nets",
        "suns",
        "bucks",
        "76ers",
        "sixers",
        "mavs",
        "mavericks",
        "nuggets",
        "clippers",
        "spurs",
        "rockets",
        "thunder",
        "jazz",
        "blazers",
        "grizzlies",
        "hawks",
        "pistons",
        "pacers",
        "cavaliers",
        "cavs",
        "magic",
        "hornets",
        "wizards",
        "kings",
        "pelicans",
        "timberwolves",
    ]
    nba_players = [
        "lebron",
        "curry",
        "doncic",
        "giannis",
        "jokic",
        "durant",
        "tatum",
        "morant",
        "embiid",
        "lillard",
        "booker",
        "edwards",
        "brunson",
    ]

    for team in nba_teams:
        if team in query_lower:
            entities.append(team.capitalize())

    for player in nba_players:
        if player in query_lower:
            entities.append(player.capitalize())

    # Pattern per servizi Google
    google_services = ["drive", "gmail", "calendar", "docs", "sheets", "meet"]
    for service in google_services:
        if service in query_lower:
            entities.append(f"Google {service.capitalize()}")

    # Pattern per crypto/finance
    crypto_tokens = ["bitcoin", "btc", "ethereum", "eth", "solana"]
    for token in crypto_tokens:
        if token in query_lower:
            entities.append(token.upper() if len(token) <= 4 else token.capitalize())

    # Domain keywords generici
    if "nba" in query_lower or "basket" in query_lower:
        entities.append("NBA")
    if "crypto" in query_lower:
        entities.append("Crypto")
    if "meteo" in query_lower or "weather" in query_lower:
        entities.append("Weather")

    return list(set(entities))  # Deduplica


def _extract_search_term_from_query(query: str) -> str:
    """Estrae il termine di ricerca principale dalla query."""
    import re

    # Pattern per estrarre termini di ricerca (ordine importante - più specifici prima)
    patterns = [
        # "ad Allumiere", "a Allumiere" - priorità massima
        r"\s+(?:ad?)\s+([A-Za-zÀ-ÿ]+)(?:\s|$|\.)",
        # "riguarda Allumiere", "relativo ad Allumiere"
        r"(?:riguarda(?:no)?|relativ[oia]?\s+(?:a|ad)?)\s+([A-Za-zÀ-ÿ]+)(?:\s|$)",
        # "ciò che riguarda Allumiere"
        r"(?:ciò\s+che\s+riguarda)\s+([A-Za-zÀ-ÿ]+)",
        # "tutto su Allumiere", "per Allumiere"
        r"(?:tutto\s+)?(?:su|per)\s+([A-Za-zÀ-ÿ]+)(?:\s|$)",
        # "comune di Allumiere"
        r"comune\s+di\s+([A-Za-zÀ-ÿ]+)",
    ]

    # Parole da escludere (servizi Google, stop words, e parole comuni)
    excluded = {
        "google",
        "drive",
        "gmail",
        "calendar",
        "meet",
        "docs",
        "sheets",
        "tutto",
        "ciò",
        "che",
        "cerca",
        "trovami",
        "mostrami",
        "relative",
        "relativo",
        "relativa",
        "relativi",  # stop words italiane
        "email",
        "mail",
        "file",
        "documenti",
        "documento",
        "le",
        "il",
        "la",
        "lo",
        "gli",
        "un",
        "una",
    }

    for pattern in patterns:
        match = re.search(pattern, query, re.IGNORECASE)
        if match:
            term = match.group(1)
            if term.lower() not in excluded and len(term) > 2:
                logger.info("search_term_extracted", term=term, pattern=pattern[:30])
                return term

    # Fallback: ultima parola significativa (> 4 caratteri, non esclusa)
    words = query.split()
    for word in reversed(words):
        clean = re.sub(r"[^\w]", "", word)
        if len(clean) > 4 and clean.lower() not in excluded:
            logger.info("search_term_fallback", term=clean)
            return clean

    logger.warning("search_term_not_found", query=query[:50])
    return ""


async def _execute_single_tool(
    tenant_id: str,
    user_id: str,
    user_query: str,
    tool_id: str,
    tool_payload: dict,
    tool_score: float,
    executor: ToolExecutor,
    llm_client: NanoGPTClient,
    config: Any,
    fallback_query_arg: str = "",
) -> dict[str, Any]:
    """Esegue un singolo tool con estrazione argomenti LLM."""
    tool_name = tool_payload.get("name", "unknown")
    tool_desc = tool_payload.get("description", "")
    tool_params = tool_payload.get("parameters", {})

    logger.info(
        "tool_selected_semantic",
        tool_name=tool_name,
        score=round(tool_score, 3),
    )

    # Estrai argomenti con LLM
    arguments = await extract_arguments_with_llm(
        user_query=user_query,
        tool_name=tool_name,
        tool_description=tool_desc,
        tool_parameters=tool_params,
        llm_client=llm_client,
        config=config,
    )

    # FALLBACK: se LLM restituisce vuoto e abbiamo un termine di ricerca,
    # imposta "query" come argomento di default (usato da Drive, Gmail, etc.)
    if not arguments and fallback_query_arg:
        arguments = {"query": fallback_query_arg}
        logger.info("arguments_fallback_used", query=fallback_query_arg, tool=tool_name)

    # Esegui tool
    request = ExecutionRequest(
        tenant_id=tenant_id,
        user_id=user_id,
        intent=user_query,
        tool_id=tool_id,
        arguments=arguments,
    )

    try:
        result = await executor.execute(request, use_muscle_memory=False)

        logger.info(
            "semantic_tool_executed",
            tool_name=result.tool_name,
            success=result.success,
            latency_ms=result.latency_ms,
        )

        return {
            "query": user_query,
            "tool_name": result.tool_name,
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "latency_ms": result.latency_ms,
            "score": tool_score,
        }

    except Exception as e:
        logger.error("semantic_tool_execution_failed", tool=tool_name, error=str(e))
        return {
            "query": user_query,
            "tool_name": tool_name,
            "success": False,
            "error": str(e),
        }


# =============================================================================
# NBA CHAINED ANALYSIS - Tool Chain per analisi complete
# =============================================================================


async def _execute_nba_chained_analysis(
    tenant_id: str,
    user_id: str,
    user_query: str,
    executor: ToolExecutor,
    embedding_service: Any,
    llm_client: NanoGPTClient,
    config: Any,
    procedural: Any,
) -> list[dict[str, Any]]:
    """Esegue analisi NBA completa con tool chain.

    Flusso:
    1. nba_upcoming_games → prima partita
    2. nba_teams → team_id
    3. nba_team_roster → player_id (top giocatori)
    4. nba_player_career_stats → statistiche REALI
    5. Parallelo: odds + injuries
    """
    import asyncio

    collected_data = []

    logger.info("nba_chained_analysis_start", query=user_query[:50])

    # =========================================================================
    # STEP 1: Trova prima partita in programma
    # =========================================================================
    games_result = await _execute_tool_by_name(
        "nba_upcoming_games", {}, tenant_id, user_id, executor, embedding_service, procedural
    )
    collected_data.append(games_result)

    if not games_result.get("success") or not games_result.get("result", {}).get("games"):
        logger.warning("nba_chain_no_games_found")
        return collected_data

    # Estrai prima partita
    first_game = games_result["result"]["games"][0]
    home_team_name = first_game.get("home_team", "")
    away_team_name = first_game.get("away_team", "")

    logger.info(
        "nba_chain_first_game",
        home=home_team_name,
        away=away_team_name,
        date=first_game.get("date"),
    )

    # =========================================================================
    # STEP 2: Trova team_id per entrambe le squadre
    # =========================================================================
    teams_result = await _execute_tool_by_name(
        "nba_teams", {}, tenant_id, user_id, executor, embedding_service, procedural
    )

    if not teams_result.get("success"):
        # Fallback: continua senza statistiche giocatori
        collected_data.append(teams_result)
        logger.warning("nba_chain_teams_failed")
    else:
        all_teams = teams_result.get("result", {}).get("teams", [])

        # Trova team_id per home e away
        home_team_id = _find_team_id(all_teams, home_team_name)
        away_team_id = _find_team_id(all_teams, away_team_name)

        logger.info(
            "nba_chain_team_ids",
            home_id=home_team_id,
            away_id=away_team_id,
        )

        # =====================================================================
        # STEP 3: Ottieni roster per entrambe le squadre
        # =====================================================================
        home_roster = None
        away_roster = None

        if home_team_id:
            home_roster_result = await _execute_tool_by_name(
                "nba_team_roster",
                {"team_id": home_team_id, "season": "2024-25"},
                tenant_id,
                user_id,
                executor,
                embedding_service,
                procedural,
            )
            if home_roster_result.get("success"):
                home_roster = home_roster_result.get("result", {}).get("roster", [])
                collected_data.append(home_roster_result)

        if away_team_id:
            away_roster_result = await _execute_tool_by_name(
                "nba_team_roster",
                {"team_id": away_team_id, "season": "2024-25"},
                tenant_id,
                user_id,
                executor,
                embedding_service,
                procedural,
            )
            if away_roster_result.get("success"):
                away_roster = away_roster_result.get("result", {}).get("roster", [])
                collected_data.append(away_roster_result)

        # =====================================================================
        # STEP 4: Statistiche top giocatori (3 per squadra)
        # =====================================================================
        player_stats_tasks = []

        if home_roster:
            for player in home_roster[:3]:  # Top 3
                player_id = player.get("PLAYER_ID") or player.get("player_id")
                if player_id:
                    player_stats_tasks.append(
                        _execute_tool_by_name(
                            "nba_player_career_stats",
                            {"player_id": player_id},
                            tenant_id,
                            user_id,
                            executor,
                            embedding_service,
                            procedural,
                        )
                    )

        if away_roster:
            for player in away_roster[:3]:  # Top 3
                player_id = player.get("PLAYER_ID") or player.get("player_id")
                if player_id:
                    player_stats_tasks.append(
                        _execute_tool_by_name(
                            "nba_player_career_stats",
                            {"player_id": player_id},
                            tenant_id,
                            user_id,
                            executor,
                            embedding_service,
                            procedural,
                        )
                    )

        if player_stats_tasks:
            player_stats_results = await asyncio.gather(*player_stats_tasks, return_exceptions=True)
            for result in player_stats_results:
                if isinstance(result, dict) and result.get("success"):
                    collected_data.append(result)

    # =========================================================================
    # STEP 5: Parallelo - odds + injuries + live scoreboard
    # =========================================================================
    parallel_tasks = [
        _execute_tool_by_name(
            "nba_betting_odds", {}, tenant_id, user_id, executor, embedding_service, procedural
        ),
        _execute_tool_by_name(
            "espn_nba_injuries", {}, tenant_id, user_id, executor, embedding_service, procedural
        ),
        _execute_tool_by_name(
            "nba_live_scoreboard", {}, tenant_id, user_id, executor, embedding_service, procedural
        ),
    ]

    parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
    for result in parallel_results:
        if isinstance(result, dict):
            collected_data.append(result)

    logger.info(
        "nba_chained_analysis_complete",
        total_tools=len(collected_data),
        successful=sum(1 for d in collected_data if d.get("success", False)),
    )

    return collected_data


def _find_team_id(teams: list[dict], team_name: str) -> int | None:
    """Trova team_id dal nome squadra."""
    team_name_lower = team_name.lower()

    for team in teams:
        # Prova match esatto
        full_name = team.get("full_name", "").lower()
        if full_name == team_name_lower:
            return team.get("id")

        # Prova match parziale
        if team_name_lower in full_name or full_name in team_name_lower:
            return team.get("id")

        # Prova con nickname
        nickname = team.get("nickname", "").lower()
        if nickname and nickname in team_name_lower:
            return team.get("id")

    return None


async def _execute_tool_by_name(
    tool_name: str,
    arguments: dict,
    tenant_id: str,
    user_id: str,
    executor: ToolExecutor,
    embedding_service: Any,
    procedural: Any,
) -> dict[str, Any]:
    """Esegue un tool per nome, trovandolo prima in Qdrant."""
    from me4brain.retrieval.tool_executor import ExecutionRequest

    # Mappa query specifiche per tool con nomi simili
    tool_search_queries = {
        "nba_teams": "NBA teams lista squadre all teams nba_api static",
        "nba_team_roster": "NBA roster giocatori formazione squadra players nba_api",
        "nba_player_career_stats": "NBA player career statistics carriera giocatore nba_api",
        "nba_upcoming_games": "NBA prossime partite schedule games BallDontLie",
        "nba_betting_odds": "NBA betting odds quote scommesse The Odds API",
        "espn_nba_injuries": "NBA injuries infortuni ESPN",
        "nba_live_scoreboard": "NBA live scoreboard partite oggi nba_api",
    }

    # Usa query specifica se disponibile, altrimenti nome tool
    search_query = tool_search_queries.get(tool_name, tool_name)
    query_embedding = embedding_service.embed_query(search_query)

    try:
        results = await procedural.search_tools_in_qdrant(
            tenant_id=tenant_id,
            query_embedding=query_embedding,
            limit=1,
            min_score=0.4,
        )
    except Exception as e:
        return {"tool_name": tool_name, "success": False, "error": str(e)}

    if not results:
        return {"tool_name": tool_name, "success": False, "error": f"Tool {tool_name} not found"}

    tool_id, tool_payload, tool_score = results[0]

    # Esegui
    request = ExecutionRequest(
        tenant_id=tenant_id,
        user_id=user_id,
        intent=tool_name,
        tool_id=tool_id,
        arguments=arguments,
    )

    try:
        result = await executor.execute(request, use_muscle_memory=False)
        return {
            "tool_name": result.tool_name,
            "tool_id": tool_id,
            "success": result.success,
            "result": result.result,
            "error": result.error,
            "latency_ms": result.latency_ms,
        }
    except Exception as e:
        return {"tool_name": tool_name, "success": False, "error": str(e)}


# =============================================================================
# LEGACY TOOL LOOP - Funzione obsoleta, mantenuta per compatibilità
# =============================================================================

MAX_TOOL_ITERATIONS = 5


async def _legacy_tool_loop(
    tenant_id: str,
    user_id: str,
    original_query: str,
    data_needs: list[dict],
    executor: ToolExecutor,
    embedding_service: Any,
    procedural: Any,
) -> list[dict[str, Any]]:
    """Legacy tool loop - mantenuto per compatibilità."""
    collected_data = []

    for i, need in enumerate(data_needs[:MAX_TOOL_ITERATIONS]):
        search_query = need.get("query", "")
        entity = need.get("entity", "")
        data_type = need.get("type", "general")

        logger.info(
            "tool_loop_iteration",
            iteration=i + 1,
            total=len(data_needs),
            type=data_type,
            entity=entity,
        )

        # ==========================================================================
        # Override entity per Google Workspace: se LLM ha estratto "Google" come entity,
        # estrai il vero termine di ricerca dalla query originale dell'utente
        # ==========================================================================
        user_query_lower = original_query.lower()
        if "drive" in user_query_lower or "gdrive" in user_query_lower:
            if entity.lower() == "google":
                # Estrai il termine di ricerca reale dalla query originale
                import re

                patterns = [
                    r"comune\s+(?:di\s+)?([A-Za-zÀ-ÿ]+)",  # "comune di Allumiere"
                    r"con\s+([A-Za-zÀ-ÿ]+)$",  # termina con "con X"
                    r"(?:documenti?|file)\s+(?:che\s+)?(?:parlano?|riguardano?|hanno)\s+.*?([A-Za-zÀ-ÿ]+)$",
                ]
                for pattern in patterns:
                    match = re.search(pattern, original_query, re.IGNORECASE)
                    if match:
                        entity = match.group(1)
                        logger.info("entity_overridden", old="Google", new=entity)
                        break
                else:
                    # Fallback: ultima parola significativa della query
                    words = [
                        w
                        for w in original_query.split()
                        if len(w) > 4
                        and w.lower()
                        not in (
                            "drive",
                            "google",
                            "documenti",
                            "tutti",
                            "file",
                            "mio",
                            "hanno",
                            "fare",
                            "cerca",
                        )
                    ]
                    if words:
                        entity = words[-1]
                        logger.info("entity_overridden_fallback", old="Google", new=entity)

            # CRITICO: Forza data_type='general' per Google Workspace
            # Altrimenti 'finance' fa entrare in ramo sbagliato che imposta args["symbol"]
            # invece di args["query"] - Fix suggerito da Perplexity
            data_type = "general"
            logger.info("data_type_overridden_for_google_workspace", old="finance", new="general")

        # Override search query per tipi specifici per trovare tool corretti
        if data_type == "crypto_history":
            # Match descrizione: "STORICO PREZZI CRYPTO: dati storici giornalieri/settimanali..."
            search_query = f"STORICO PREZZI CRYPTO dati storici giornalieri correlazione storica andamento ultimi anni {entity}"
        elif data_type == "finance_history":
            # Match descrizione: "STORICO PREZZI AZIONI: dati storici giornalieri/settimanali..."
            search_query = f"STORICO PREZZI AZIONI dati storici giornalieri correlazione storica andamento ultimi anni {entity}"

        # Override per Google Workspace: usa la query ORIGINALE utente (non dal LLM)
        user_query_lower = original_query.lower()
        if "drive" in user_query_lower or "gdrive" in user_query_lower:
            search_query = f"Google Drive cerca file documenti search {entity}"
        elif (
            "gmail" in user_query_lower or "email" in user_query_lower or "mail" in user_query_lower
        ):
            search_query = f"Gmail cerca email messaggi inbox {entity}"
        elif (
            "calendar" in user_query_lower
            or "evento" in user_query_lower
            or "appuntamento" in user_query_lower
        ):
            search_query = f"Google Calendar cerca eventi appuntamenti {entity}"
        elif (
            "forms" in user_query_lower
            or "form" in user_query_lower
            or "modulo" in user_query_lower
        ):
            search_query = f"Google Forms cerca moduli questionari {entity}"
        elif "classroom" in user_query_lower or "classe" in user_query_lower:
            search_query = f"Google Classroom cerca corsi compiti {entity}"
        elif "docs" in user_query_lower or "documento" in user_query_lower:
            search_query = f"Google Docs cerca documenti {entity}"
        elif (
            "sheets" in user_query_lower
            or "foglio" in user_query_lower
            or "spreadsheet" in user_query_lower
        ):
            search_query = f"Google Sheets cerca fogli calcolo {entity}"
        elif "slides" in user_query_lower or "presentazione" in user_query_lower:
            search_query = f"Google Slides cerca presentazioni {entity}"

        # Genera embedding per la ricerca
        query_embedding = embedding_service.embed_query(search_query)

        # Cerca tool migliore
        try:
            results = await procedural.search_tools_in_qdrant(
                tenant_id=tenant_id,
                query_embedding=query_embedding,
                limit=3,
                min_score=MIN_TOOL_SCORE,
            )
        except Exception as e:
            logger.warning("tool_search_failed", error=str(e))
            collected_data.append(
                {
                    "query": search_query,
                    "success": False,
                    "error": f"Search failed: {e}",
                }
            )
            continue

        if not results:
            logger.warning("no_tool_found", query=search_query[:50])
            collected_data.append(
                {
                    "query": search_query,
                    "success": False,
                    "error": "No suitable tool found",
                }
            )
            continue

        # Prendi il migliore
        tool_id, payload, score = results[0]
        tool_name = payload.get("name", "unknown")

        logger.info(
            "tool_selected",
            tool_name=tool_name,
            score=round(score, 3),
        )

        # Estrai argomenti
        arguments = _extract_arguments(search_query, entity, data_type)

        # Esegui tool
        request = ExecutionRequest(
            tenant_id=tenant_id,
            user_id=user_id,
            intent=search_query,
            tool_id=tool_id,
            arguments=arguments,
        )

        try:
            result = await executor.execute(
                request, use_muscle_memory=False
            )  # Disabilitato temporaneamente

            collected_data.append(
                {
                    "query": search_query,
                    "type": data_type,
                    "entity": entity,
                    "tool_name": result.tool_name,
                    "success": result.success,
                    "result": result.result,
                    "error": result.error,
                    "latency_ms": result.latency_ms,
                }
            )

        except Exception as e:
            logger.error("tool_execution_failed", error=str(e))
            collected_data.append(
                {
                    "query": search_query,
                    "success": False,
                    "error": str(e),
                }
            )

    return collected_data


def _extract_arguments(query: str, entity: str, data_type: str) -> dict[str, Any]:
    """Estrae argomenti DINAMICI per il tool basandosi su query ed entità.

    NON usa mappe hardcodate - estrae simboli e periodi direttamente dalla query.
    """
    import re

    args: dict[str, Any] = {}
    query_lower = query.lower()
    entity_lower = entity.lower()

    # ==========================================================================
    # ESTRAZIONE DINAMICA DEL PERIODO
    # ==========================================================================
    def extract_years_from_query(q: str) -> int:
        """Estrae il numero di anni dalla query."""
        patterns = [
            r"(\d+)\s*ann[io]",  # "4 anni", "2 anno"
            r"ultim[io]\s*(\d+)\s*ann",  # "ultimi 4 anni"
            r"(\d+)\s*year",  # "4 years"
            r"last\s*(\d+)\s*year",  # "last 4 years"
        ]
        for pattern in patterns:
            match = re.search(pattern, q.lower())
            if match:
                return int(match.group(1))
        # Default: 2 anni se non specificato
        return 2

    years = extract_years_from_query(query)
    weeks = years * 52  # Conversione in settimane

    # ==========================================================================
    # CRYPTO (corrente e storico)
    # ==========================================================================
    if data_type in ("crypto", "crypto_history"):
        # Prova a estrarre il simbolo dall'entity o query
        # Formato Binance: BTCUSDT, ETHUSDT etc
        symbol = entity_lower.upper()

        # Se è un nome comune, converti in simbolo Binance
        common_crypto = {
            "bitcoin": "BTC",
            "ethereum": "ETH",
            "solana": "SOL",
            "cardano": "ADA",
            "polkadot": "DOT",
            "avalanche": "AVAX",
            "chainlink": "LINK",
            "ripple": "XRP",
            "dogecoin": "DOGE",
            "litecoin": "LTC",
            "polygon": "MATIC",
            "uniswap": "UNI",
        }

        for name, sym in common_crypto.items():
            if name in entity_lower or name in query_lower:
                symbol = sym
                break

        # Assicurati che sia formato XXXUSDT
        if not symbol.endswith("USDT"):
            symbol = symbol.upper() + "USDT"

        args["symbol"] = symbol

        if data_type == "crypto_history":
            args["interval"] = "1w"  # Settimanale
            args["limit"] = min(weeks, 1000)  # Max 1000 da Binance

    # ==========================================================================
    # FINANCE (corrente e storico)
    # ==========================================================================
    elif data_type in ("finance", "finance_history"):
        # Prova a estrarre il simbolo dall'entity
        symbol = entity_lower.upper()

        # Se è un nome comune, converti in ticker
        common_stocks = {
            "apple": "AAPL",
            "google": "GOOGL",
            "alphabet": "GOOGL",
            "microsoft": "MSFT",
            "tesla": "TSLA",
            "amazon": "AMZN",
            "nvidia": "NVDA",
            "meta": "META",
            "facebook": "META",
            "netflix": "NFLX",
            "intel": "INTC",
            "amd": "AMD",
            "salesforce": "CRM",
            "oracle": "ORCL",
            "ibm": "IBM",
            "disney": "DIS",
            "coca-cola": "KO",
            "pepsi": "PEP",
            "jpmorgan": "JPM",
            "goldman": "GS",
            "visa": "V",
            "mastercard": "MA",
            "paypal": "PYPL",
            "uber": "UBER",
        }

        for name, ticker in common_stocks.items():
            if name in entity_lower or name in query_lower:
                symbol = ticker
                break

        # Se sembra già un ticker (tutto maiuscolo, 1-5 lettere), usalo
        if re.match(r"^[A-Z]{1,5}$", symbol):
            pass
        elif re.match(r"^[a-z]{1,5}$", entity_lower):
            symbol = entity_lower.upper()

        args["symbol"] = symbol

        if data_type == "finance_history":
            # Yahoo Finance accetta: 1y, 2y, 5y, 10y, max
            if years >= 10:
                args["period"] = "max"
            elif years >= 5:
                args["period"] = "5y"
            else:
                args["period"] = f"{years}y"
            args["interval"] = "1wk"

    # ==========================================================================
    # WEATHER - Usa geocoding dinamico (passa la città come query)
    # ==========================================================================
    elif data_type == "weather":
        # Passa direttamente l'entity come location - il tool farà geocoding
        args["location"] = entity if entity != "default" else "Roma, Italia"

    # ==========================================================================
    # MACRO - FRED series
    # ==========================================================================
    elif data_type == "macro":
        # Estrai il tipo di dato macro dalla query
        if "gdp" in query_lower or "pil" in query_lower:
            args["series_id"] = "GDP"
        elif "inflazione" in query_lower or "inflation" in query_lower:
            args["series_id"] = "CPIAUCSL"
        elif "disoccupazione" in query_lower or "unemployment" in query_lower:
            args["series_id"] = "UNRATE"
        elif "tassi" in query_lower or "interest" in query_lower or "fed" in query_lower:
            args["series_id"] = "FEDFUNDS"
        else:
            # Usa l'entity come series_id direttamente
            args["series_id"] = entity.upper()

    # ==========================================================================
    # GOOGLE WORKSPACE (Drive, Gmail, Calendar, etc.) - type="general"
    # ==========================================================================
    elif data_type in ("general", "finance"):
        # Per Google Workspace, passa la query originale come parametro di ricerca
        # L'entity contiene il termine di ricerca (es. "Allumiere")
        if entity and entity.lower() != "google":
            args["query"] = entity
        else:
            # Se entity è "Google", estrai il termine di ricerca dalla query
            # Es: "cerca documenti Allumiere" -> "Allumiere"
            import re

            # Pattern per estrarre termine dopo "documenti", "file", etc.
            patterns = [
                r"documenti?\s+(?:che\s+)?(?:hanno\s+)?(?:a\s+che\s+fare\s+)?(?:con\s+)?(?:il\s+)?(?:comune\s+di\s+)?([A-Za-zÀ-ÿ]+)",
                r"file\s+(?:su\s+)?([A-Za-zÀ-ÿ]+)",
                r"cerca(?:re)?\s+([A-Za-zÀ-ÿ]+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, query, re.IGNORECASE)
                if match:
                    args["query"] = match.group(1)
                    break
            else:
                # Fallback: usa l'ultima parola significativa della query
                words = [
                    w
                    for w in query.split()
                    if len(w) > 4
                    and w.lower() not in ("drive", "google", "documenti", "tutti", "mio")
                ]
                if words:
                    args["query"] = words[-1]

    return args


# =============================================================================
# Memory Retrieval
# =============================================================================


async def retrieve_memory_context(
    tenant_id: str,
    user_id: str,
    entities: list[str],
    embedding_service: Any,
) -> str:
    """Recupera contesto dalla memoria per le entità rilevanti."""
    episodic = get_episodic_memory()
    context_parts = []

    # Cerca memorie episodiche recenti
    for entity in entities[:3]:  # Max 3 entità
        query_embedding = embedding_service.embed_query(entity)

        try:
            memories = await episodic.search(
                tenant_id=tenant_id,
                user_id=user_id,
                query_embedding=query_embedding,
                limit=2,
            )

            for mem in memories:
                if mem.get("content"):
                    context_parts.append(f"[{entity}]: {mem['content'][:200]}")

        except Exception as e:
            logger.debug("memory_search_failed", entity=entity, error=str(e))

    return "\n".join(context_parts) if context_parts else "Nessun contesto precedente."


# =============================================================================
# Thinking Synthesis (DeepSeek v3.2 Speciale)
# =============================================================================


async def synthesize_response(
    query: str,
    analysis: dict,
    collected_data: list[dict],
    memory_context: str,
    llm_client: NanoGPTClient,
    config: Any,
) -> str:
    """Genera risposta finale con DeepSeek v3.2 Speciale."""
    # Formatta dati raccolti con separazione per tool
    data_formatted = []
    for d in collected_data:
        if d.get("success"):
            tool_name = d.get("tool_name", "unknown")
            # FIX: I dati sono sotto "data" (modular) o "result" (legacy)
            result = d.get("data", d.get("result", {}))

            # Formattazione specifica per tool Google
            if "gmail" in tool_name.lower():
                emails = result.get("emails", [])
                data_formatted.append(
                    {
                        "FONTE": "Gmail",
                        "query_usata": result.get("query", ""),
                        "email_trovate": len(emails),
                        "dettagli_email": emails,
                    }
                )
            elif "drive" in tool_name.lower():
                files = result.get("files", [])
                data_formatted.append(
                    {
                        "FONTE": "Google Drive",
                        "query_usata": result.get("query", ""),
                        "file_trovati": len(files),
                        "dettagli_file": files,
                    }
                )
            elif "calendar" in tool_name.lower():
                events = result.get("events", [])
                data_formatted.append(
                    {
                        "FONTE": "Google Calendar",
                        "eventi_trovati": len(events) if events else 0,
                        "dettagli_eventi": events,
                    }
                )
            else:
                # Tool generico
                data_formatted.append(
                    {
                        "FONTE": tool_name,
                        "dati": result,
                    }
                )
        else:
            data_formatted.append(
                {
                    "FONTE": d.get("tool_name", d.get("query", "unknown")),
                    "ERRORE": d.get("error", "Dati non disponibili"),
                }
            )

    prompt = THINKING_SYNTHESIS_PROMPT.format(
        query=query,
        analysis_plan=json.dumps(analysis, indent=2, ensure_ascii=False)[:500],
        collected_data=json.dumps(data_formatted, indent=2, ensure_ascii=False)[
            :12000  # Aumentato per contenere snippet email e description file
        ],  # Aumentato da 3000
        memory_context=memory_context[:500],
    )

    request = LLMRequest(
        model=config.model_primary_thinking,  # DeepSeek v3.2 Speciale
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=16000,  # NanoGPT non ha limiti hard documentati
    )

    try:
        response = await llm_client.generate_response(request)
        return response.content or "Errore nella generazione della risposta."
    except Exception as e:
        logger.error("synthesis_failed", error=str(e))
        return f"Errore nella sintesi: {e}"


async def synthesize_response_stream(
    query: str,
    analysis: dict,
    collected_data: list[dict],
    memory_context: str,
    llm_client: NanoGPTClient,
    config: Any,
) -> AsyncGenerator[str, None]:
    """Genera risposta finale con streaming SSE reale.

    Usa NanoGPTClient.stream_response() per true streaming token-by-token,
    riducendo Time to First Byte da 5-15s a <500ms.
    """
    from me4brain.llm.models import Message  # noqa: avoid circular import

    # Formatta dati raccolti (stessa logica di synthesize_response)
    data_formatted = []
    for d in collected_data:
        if d.get("success"):
            tool_name = d.get("tool_name", "unknown")
            result = d.get("data", d.get("result", {}))

            if "gmail" in tool_name.lower():
                emails = result.get("emails", [])
                data_formatted.append(
                    {
                        "FONTE": "Gmail",
                        "query_usata": result.get("query", ""),
                        "email_trovate": len(emails),
                        "dettagli_email": emails,
                    }
                )
            elif "drive" in tool_name.lower():
                files = result.get("files", [])
                data_formatted.append(
                    {
                        "FONTE": "Google Drive",
                        "query_usata": result.get("query", ""),
                        "file_trovati": len(files),
                        "dettagli_file": files,
                    }
                )
            elif "calendar" in tool_name.lower():
                events = result.get("events", [])
                data_formatted.append(
                    {
                        "FONTE": "Google Calendar",
                        "eventi_trovati": len(events) if events else 0,
                        "dettagli_eventi": events,
                    }
                )
            else:
                data_formatted.append(
                    {
                        "FONTE": tool_name,
                        "dati": result,
                    }
                )
        else:
            data_formatted.append(
                {
                    "FONTE": d.get("tool_name", d.get("query", "unknown")),
                    "ERRORE": d.get("error", "Dati non disponibili"),
                }
            )

    prompt = THINKING_SYNTHESIS_PROMPT.format(
        query=query,
        analysis_plan=json.dumps(analysis, indent=2, ensure_ascii=False)[:500],
        collected_data=json.dumps(data_formatted, indent=2, ensure_ascii=False)[:12000],
        memory_context=memory_context[:500],
    )

    request = LLMRequest(
        model=config.model_primary_thinking,  # DeepSeek v3.2
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=16000,  # NanoGPT non ha limiti hard documentati
        stream=True,  # STREAMING REALE
    )

    try:
        async for chunk in llm_client.stream_response(request):
            # Estrai contenuto dal chunk SSE
            if chunk.choices and chunk.choices[0].delta:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
    except Exception as e:
        logger.error("synthesis_stream_failed", error=str(e))
        yield f"\n\nErrore nella sintesi: {e}"


# =============================================================================
# Memory Learning
# =============================================================================


async def save_to_memory(
    tenant_id: str,
    user_id: str,
    query: str,
    response: str,
    analysis: dict,
    collected_data: list[dict],
) -> None:
    """Salva l'interazione nella memoria episodica per learning futuro."""
    episodic = get_episodic_memory()
    embedding_service = get_embedding_service()

    # Crea nota per memoria episodica
    note_content = f"Q: {query}\nA: {response[:500]}"
    note_embedding = embedding_service.embed_query(note_content)

    try:
        from me4brain.memory.episodic import Episode

        episode = Episode(
            tenant_id=tenant_id,
            user_id=user_id,
            content=note_content,
            source="cognitive_pipeline",
            importance=0.7,
            tags=["qa_interaction", analysis.get("analysis_type", "simple")]
            + [
                d.get("tool_name")
                for d in collected_data
                if d.get("success") and d.get("tool_name")
            ],
        )

        await episodic.add_episode(episode, note_embedding)
        logger.info("memory_saved", query=query[:50])
    except Exception as e:
        logger.warning("memory_save_failed", error=str(e))


# =============================================================================
# Main Pipeline
# =============================================================================


async def run_cognitive_pipeline(
    tenant_id: str,
    user_id: str,
    query: str,
    save_memory: bool = True,
) -> dict[str, Any]:
    """Esegue la pipeline cognitiva completa.

    Args:
        tenant_id: ID tenant
        user_id: ID utente
        query: Query in linguaggio naturale
        save_memory: Se salvare l'interazione per learning

    Returns:
        dict con response, analysis, collected_data, etc.
    """
    config = get_llm_config()
    llm_client = NanoGPTClient(
        api_key=config.nanogpt_api_key,
        base_url=config.nanogpt_base_url,
    )
    embedding_service = get_embedding_service()
    ToolExecutor()

    logger.info("cognitive_pipeline_start", query=query[:50])

    # Step 1: Analizza query (Kimi K2.5)
    analysis = await analyze_query(query, llm_client, config)

    # Step 2: Recupera contesto memoria
    memory_context = ""
    if analysis.get("requires_memory"):
        memory_context = await retrieve_memory_context(
            tenant_id, user_id, analysis.get("entities", []), embedding_service
        )

    # Step 3: ReAct Agent Loop (Reason + Act + Observe)
    # NEW: Sostituisce execute_semantic_tool_loop con pattern iterativo
    # - Retry automatico su tool failures
    # - Circuit breaker per fail-fast
    # - Robust entity validation
    collected_data = []
    if analysis.get("requires_tools"):
        collected_data = await react_agent_loop(
            tenant_id=tenant_id,
            user_id=user_id,
            query=query,
            analysis=analysis,
            llm_client=llm_client,
            config=config,
            max_iterations=3,  # Max 3 iterazioni per query
        )

    # Step 4: Thinking synthesis (DeepSeek v3.2 Speciale)
    response = await synthesize_response(
        query, analysis, collected_data, memory_context, llm_client, config
    )

    # Step 5: Memory learning
    if save_memory and collected_data:
        await save_to_memory(tenant_id, user_id, query, response, analysis, collected_data)

    logger.info(
        "cognitive_pipeline_complete",
        query=query[:50],
        tools_used=len([d for d in collected_data if d.get("success")]),
    )

    return {
        "response": response,
        "analysis": analysis,
        "collected_data": collected_data,
        "memory_context": memory_context,
        "success": True,
    }
