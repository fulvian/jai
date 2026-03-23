"""Tool Calling Engine API Routes.

Espone il Tool Calling Engine tramite API REST:
- POST /query - Query NL → tool selection → parallel execution → synthesis
- POST /call - Direct tool call by name
- GET /tools - Lista tools dal catalog con filtri
- GET /tools/{name} - Dettagli singolo tool

Questo modulo è separato da tools.py che gestisce il Procedural Memory (Qdrant).
L'Engine usa il ToolCatalog con auto-discovery dai domini.
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from me4brain.api.middleware.api_key import get_optional_api_key

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/engine", tags=["Engine"])


# =============================================================================
# Request/Response Models
# =============================================================================


class EngineQueryRequest(BaseModel):
    """Richiesta query al Tool Calling Engine."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Query in linguaggio naturale",
        examples=["Qual è il prezzo del Bitcoin?", "Che tempo fa a Roma?"],
    )
    session_id: str | None = Field(
        default=None,
        max_length=200,
        description="Session ID per continuità conversazione. Se presente, attiva integrazione memoria completa (Working + Episodic Memory).",
    )
    conversation_context: str | None = Field(
        default=None,
        max_length=50000,
        description="Contesto conversazione manuale (fallback se session_id non presente)",
    )
    stream: bool = Field(
        default=False,
        description="Se True, restituisce la risposta in streaming SSE",
    )
    include_raw_results: bool = Field(
        default=False,
        description="Se True, include i risultati raw dei tool nella risposta",
    )
    timeout_seconds: float = Field(
        default=120.0,
        ge=5.0,
        le=1800.0,  # 30 minutes for complex iterative queries
        description="Timeout totale per query",
    )


class ToolCallInfo(BaseModel):
    """Informazioni su una chiamata tool eseguita."""

    tool_name: str
    arguments: dict[str, Any]
    success: bool
    latency_ms: float
    error: str | None = None


class EngineQueryResponse(BaseModel):
    """Risposta query dal Tool Calling Engine."""

    query: str
    answer: str
    tools_called: list[ToolCallInfo]
    total_latency_ms: float
    raw_results: list[dict[str, Any]] | None = None


class EngineCallRequest(BaseModel):
    """Richiesta chiamata diretta tool."""

    tool_name: str = Field(
        ...,
        min_length=1,
        description="Nome del tool da chiamare",
        examples=["coingecko_price", "openmeteo_weather"],
    )
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Argomenti per il tool",
        examples=[{"ids": "bitcoin", "vs_currencies": "usd"}],
    )


class EngineCallResponse(BaseModel):
    """Risposta chiamata diretta tool."""

    tool_name: str
    success: bool
    result: Any | None = None
    error: str | None = None
    latency_ms: float


class ToolInfo(BaseModel):
    """Informazioni su un tool nel catalog."""

    name: str
    description: str
    domain: str | None = None
    category: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    """Lista tool dal catalog."""

    tools: list[ToolInfo]
    total: int
    domains: list[str]


class DomainStats(BaseModel):
    """Statistiche per dominio."""

    domain: str
    tool_count: int
    tools: list[str]


class CatalogStatsResponse(BaseModel):
    """Statistiche complete del catalog."""

    total_tools: int
    domains: list[DomainStats]


# =============================================================================
# Engine Instance (Singleton)
# =============================================================================

_engine_instance = None
_engine_lock = None
_engine_lock_init = False


def _get_engine_lock():
    """Get or create the engine lock (thread-safe initialization)."""
    global _engine_lock, _engine_lock_init
    if not _engine_lock_init:
        import asyncio

        _engine_lock = asyncio.Lock()
        _engine_lock_init = True
    return _engine_lock


async def get_engine():
    """Get or create the ToolCallingEngine singleton (uses Hybrid Routing + Skill Learning)."""
    global _engine_instance

    lock = _get_engine_lock()
    async with lock:
        if _engine_instance is None:
            from me4brain.core.skills import Crystallizer, get_skill_approval_manager
            from me4brain.core.skills.persistence import persist_skill_to_disk
            from me4brain.core.skills.security import get_skill_security_validator
            from me4brain.engine import ToolCallingEngine

            _engine_instance = await ToolCallingEngine.create()  # Uses hybrid routing by default

            # Enable skill learning (Voyager pattern)
            try:
                crystallizer = Crystallizer()

                # Setup approval callback per persistere skills approvate
                approval_manager = get_skill_approval_manager()

                async def on_skill_approved(pending):
                    """Callback: salva skill su disco quando approvata."""
                    try:
                        security = get_skill_security_validator()
                        validation = security.validate_skill(
                            pending.skill.code or "",
                            pending.tool_chain,
                        )
                        if validation.is_safe:
                            persist_skill_to_disk(
                                skill=pending.skill,
                                tool_chain=pending.tool_chain,
                                input_query=pending.skill.description,
                                risk_level=pending.risk_level,
                            )
                            logger.info(
                                "skill_persisted_after_approval",
                                skill_name=pending.skill.name,
                            )
                    except Exception as e:
                        logger.error("skill_persistence_failed", error=str(e))

                approval_manager.set_callbacks(on_approved=on_skill_approved)

                # Abilita learning nell'engine
                _engine_instance.enable_skill_learning(crystallizer)

                logger.info(
                    "engine_initialized_with_skill_learning",
                    tools_count=len(_engine_instance.catalog),
                    routing="hybrid_semantic",
                    skill_learning="enabled",
                )
            except Exception as e:
                logger.warning(
                    "skill_learning_init_failed",
                    error=str(e),
                )
                logger.info(
                    "engine_initialized_hybrid",
                    tools_count=len(_engine_instance.catalog),
                    routing="hybrid_semantic",
                )

        return _engine_instance


# =============================================================================
# Memory Integration (Layer I + II)
# =============================================================================


async def _build_memory_context(
    session_id: str,
    query: str,
    tenant_id: str = "default",
    user_id: str = "default",
) -> str | None:
    """Costruisce contesto arricchito da Working Memory (Layer I) + Episodic Memory (Layer II).

    - Layer I: ultimi turni conversazione dalla sessione corrente
    - Layer II: episodi passati semanticamente simili (cross-session recall)

    Ogni layer è indipendente: se uno fallisce, l'altro continua.
    Se entrambi falliscono, ritorna None (la query procede senza contesto).
    """
    context_parts: list[str] = []

    # ── Layer I: Working Memory (Redis Streams) ──────────────────────────
    try:
        from me4brain.memory import get_working_memory

        wm = get_working_memory()
        messages = await wm.get_messages(tenant_id, user_id, session_id, count=10)
        if messages:
            turns = "\n".join(
                f"{'Utente' if m['role'] == 'human' else 'Assistente'}: {m['content'][:1500]}"
                for m in messages
            )
            context_parts.append(f"## Conversazione precedente\n{turns}")
            logger.info(
                "memory_working_loaded",
                session_id=session_id,
                turns_count=len(messages),
            )
    except Exception as e:
        logger.warning("memory_working_read_failed", session_id=session_id, error=str(e))

    # ── Layer II: Episodic Memory (Qdrant) ───────────────────────────────
    try:
        from me4brain.embeddings import get_embedding_service
        from me4brain.memory import get_episodic_memory

        em = get_episodic_memory()
        embed_svc = get_embedding_service()
        query_embedding = await embed_svc.embed_query_async(query)

        episodes = await em.search_similar(
            tenant_id=tenant_id,
            user_id=user_id,
            query_embedding=query_embedding,
            limit=3,
            min_score=0.7,
            time_decay=True,
        )
        if episodes:
            recalls = "\n".join(f"- [{ep.source}] {ep.content[:300]}" for ep, _score in episodes)
            context_parts.append(f"## Ricordi rilevanti da sessioni precedenti\n{recalls}")
            logger.info(
                "memory_episodic_loaded",
                session_id=session_id,
                episodes_count=len(episodes),
                best_score=round(episodes[0][1], 3),
            )
    except Exception as e:
        logger.warning("memory_episodic_read_failed", session_id=session_id, error=str(e))

    # ── Layer III: Semantic Memory (Neo4j Knowledge Graph) ────────────────
    try:
        from me4brain.memory import get_semantic_memory

        sm = get_semantic_memory()

        # Text search per entità menzionate nella query
        kg_entities = await sm.search(tenant_id, query, limit=5)

        if kg_entities:
            # PPR: usa entità trovate come seed per spreading activation
            seed_ids = [e["id"] for e in kg_entities[:3]]
            ppr_results = await sm.personalized_pagerank(
                tenant_id,
                seed_ids,
                top_k=5,
            )

            # Costruisci context section
            kg_context = "\n".join(f"- {e['name']} ({e['type']})" for e in kg_entities)
            if ppr_results:
                related: list[str] = []
                for eid, score in ppr_results:
                    entity = await sm.get_entity(tenant_id, eid)
                    if entity:
                        related.append(f"- {entity.name} ({entity.type}, relevance: {score:.2f})")
                if related:
                    kg_context += "\n\nEntità correlate:\n" + "\n".join(related)

            context_parts.append(f"## Knowledge Graph\n{kg_context}")
            logger.info(
                "memory_semantic_loaded",
                session_id=session_id,
                entities=len(kg_entities),
                ppr_related=len(ppr_results),
            )
    except Exception as e:
        logger.warning("memory_semantic_read_failed", session_id=session_id, error=str(e))

    if not context_parts:
        return None

    # Limita a 8000 caratteri per non sovraccaricare il prompt del synthesizer
    combined = "\n\n".join(context_parts)
    return combined[:8000] if len(combined) > 8000 else combined


async def _rewrite_query_with_context(
    session_id: str,
    query: str,
    llm_client: NanoGPTClient | None = None,
    tenant_id: str = "default",
    user_id: str = "default",
) -> str:
    """Riscrive la query integrando il contesto conversazionale.

    Recupera la cronologia dalla Working Memory e usa il ContextAwareRewriter
    per produrre una query self-contained che include tutto il contesto
    necessario per il routing e la decomposizione.

    Se il rewriting non è necessario (prima domanda, query già esplicita),
    ritorna la query originale.

    Args:
        session_id: ID della sessione corrente
        query: Query originale dell'utente
        llm_client: NanoGPT client (required, no fallback to async function)
        tenant_id: ID tenant
        user_id: ID utente

    Returns:
        Query riscritta (self-contained) o originale se rewriting non necessario
    """
    from me4brain.engine.context_rewriter import get_context_rewriter
    from me4brain.memory import get_working_memory

    if llm_client is None:
        raise ValueError("llm_client is required for query rewriting")

    # 1. Recupera cronologia dalla Working Memory
    wm = get_working_memory()
    messages = await wm.get_messages(tenant_id, user_id, session_id, count=8)

    if not messages:
        return query  # Nessuna cronologia → usa query originale

    # 2. Recupera entità dal grafo di sessione (se disponibili)
    session_entities: list[str] = []
    try:
        graph = wm.get_session_graph(tenant_id, user_id, session_id)
        if graph and graph.number_of_nodes() > 0:
            # Prendi le entità con più connessioni (più rilevanti)
            entity_degrees = sorted(graph.degree(), key=lambda x: x[1], reverse=True)
            session_entities = [name for name, _deg in entity_degrees[:10]]
    except Exception:
        pass  # Grafo non disponibile → procedi senza entità

    # 3. Riscrivi con contesto
    rewriter = get_context_rewriter(llm_client=llm_client)
    result = await rewriter.rewrite(
        query=query,
        conversation_history=messages,
        session_entities=session_entities if session_entities else None,
    )

    if result.was_rewritten:
        logger.info(
            "query_rewritten_for_routing",
            session_id=session_id,
            original=query[:80],
            rewritten=result.rewritten_query[:80],
            reason=result.reason,
            entities=result.session_entities[:5],
        )
    else:
        logger.debug(
            "query_rewrite_not_needed",
            session_id=session_id,
            reason=result.reason,
        )

    return result.rewritten_query


async def _extract_entities_llm(
    query: str,
    answer: str,
) -> dict[str, Any] | None:
    """Estrae entità e relazioni dalla risposta usando LLM (Layer III helper).

    Usa un modello leggero per entity extraction strutturata.
    Ritorna None se l'estrazione fallisce o non produce risultati.
    """
    import json as _json

    from me4brain.llm.models import LLMRequest, Message, MessageRole
    from me4brain.llm.provider_factory import get_reasoning_client

    extraction_prompt = (
        "Analizza questa conversazione ed estrai le entità chiave e le relazioni.\n\n"
        f"DOMANDA: {query}\n"
        f"RISPOSTA: {answer[:3000]}\n\n"
        "Rispondi SOLO in JSON valido, senza markdown o commenti:\n"
        "{\n"
        '  "entities": [\n'
        '    {"id": "entity_id_slug", "type": "Company|Person|Concept|Metric|Location|Product", '
        '"name": "Nome Leggibile", "properties": {}}\n'
        "  ],\n"
        '  "relations": [\n'
        '    {"source_id": "entity_a", "target_id": "entity_b", '
        '"type": "HAS_METRIC|OPERATES_IN|RELATES_TO|IS_PART_OF|COMPETES_WITH", "weight": 0.8}\n'
        "  ]\n"
        "}\n\n"
        "Regole:\n"
        "- Massimo 10 entità e 10 relazioni\n"
        "- id deve essere lowercase slug senza spazi (es: oracle_corp, bitcoin_price)\n"
        "- Estrai solo informazioni fattuali, non opinioni\n"
        '- Se non ci sono entità significative, rispondi {"entities": [], "relations": []}'
    )

    llm = await get_reasoning_client()
    from me4brain.llm.config import get_llm_config

    config = get_llm_config()
    request = LLMRequest(
        model=config.model_extraction,
        messages=[
            Message(role=MessageRole.USER, content=extraction_prompt),
        ],
        temperature=0.0,
        max_tokens=1500,
    )

    response = await llm.generate_response(request)
    raw_content = response.content
    if not raw_content:
        return None

    # Pulisci eventuale markdown wrapping (```json ... ```)
    cleaned = raw_content.strip()
    if cleaned.startswith("```"):
        # Rimuovi prima e ultima riga di markdown
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    try:
        extracted = _json.loads(cleaned)
        # Validazione struttura base
        if not isinstance(extracted, dict):
            return None
        if "entities" not in extracted and "relations" not in extracted:
            return None
        return extracted
    except _json.JSONDecodeError:
        logger.warning("entity_extraction_json_parse_failed", raw=raw_content[:200])
        return None


async def _store_extracted_entities(
    extracted: dict[str, Any],
    session_id: str,
    tenant_id: str = "default",
) -> None:
    """Salva entità e relazioni estratte nel Knowledge Graph Neo4j (Layer III helper)."""
    from me4brain.memory import Entity, Relation, get_semantic_memory

    sm = get_semantic_memory()

    for ent in extracted.get("entities", []):
        if not ent.get("id") or not ent.get("name"):
            continue
        entity = Entity(
            id=ent["id"],
            type=ent.get("type", "Concept"),
            name=ent["name"],
            tenant_id=tenant_id,
            properties={**ent.get("properties", {}), "source_session": session_id},
        )
        await sm.add_entity(entity)

    for rel in extracted.get("relations", []):
        if not rel.get("source_id") or not rel.get("target_id"):
            continue
        relation = Relation(
            source_id=rel["source_id"],
            target_id=rel["target_id"],
            type=rel.get("type", "RELATES_TO"),
            tenant_id=tenant_id,
            weight=rel.get("weight", 1.0),
        )
        await sm.add_relation(relation)

    logger.debug(
        "entities_stored",
        entities=len(extracted.get("entities", [])),
        relations=len(extracted.get("relations", [])),
    )


async def _persist_interaction(
    session_id: str,
    query: str,
    answer: str,
    tenant_id: str = "default",
    user_id: str = "default",
) -> None:
    """Salva l'interazione nei 3 layer di memoria (I, II, III).

    - Layer I (Working Memory): turni user+assistant → contesto per follow-up immediati
    - Layer II (Episodic Memory): Q&A come episodio → recall semantico cross-session
    - Layer III (Semantic Memory): entity extraction LLM → Knowledge Graph Neo4j

    Eseguito in background (fire-and-forget), non blocca la risposta.
    """
    # ── Layer I: Working Memory ──────────────────────────────────────────
    try:
        from me4brain.memory import get_working_memory

        wm = get_working_memory()

        # NOTE: User query might have been persisted earlier to avoid data loss on reload.
        # Still, we ensure the assistant answer is saved here.
        if query:
            await wm.add_message(tenant_id, user_id, session_id, "human", query)

        if answer:
            await wm.add_message(tenant_id, user_id, session_id, "ai", answer[:5000])

        logger.info(
            "memory_working_persisted",
            session_id=session_id,
            has_query=bool(query),
            has_answer=bool(answer),
        )
    except Exception as e:
        logger.warning("memory_working_write_failed", session_id=session_id, error=str(e))

    # ── Layer II: Episodic Memory ────────────────────────────────────────
    try:
        from me4brain.embeddings import get_embedding_service
        from me4brain.memory import get_episodic_memory
        from me4brain.memory.episodic import Episode

        em = get_episodic_memory()
        embed_svc = get_embedding_service()

        episode_content = f"Q: {query}\nA: {answer[:2000]}"
        embedding = await embed_svc.embed_query_async(episode_content)

        episode = Episode(
            tenant_id=tenant_id,
            user_id=user_id,
            content=episode_content,
            source="persan_chat",
            importance=0.6,
            tags=["chat", f"session:{session_id}"],
        )
        await em.add_episode(episode, embedding)
        logger.info(
            "memory_episodic_persisted",
            session_id=session_id,
            episode_id=episode.id,
        )
    except Exception as e:
        logger.warning("memory_episodic_write_failed", session_id=session_id, error=str(e))

    # ── Layer III: Semantic Memory (Knowledge Graph) ──────────────────────
    try:
        extracted = await _extract_entities_llm(query, answer)
        if extracted and (extracted.get("entities") or extracted.get("relations")):
            await _store_extracted_entities(extracted, session_id, tenant_id)
            logger.info(
                "memory_semantic_persisted",
                session_id=session_id,
                entities=len(extracted.get("entities", [])),
                relations=len(extracted.get("relations", [])),
            )
    except Exception as e:
        logger.warning("memory_semantic_write_failed", session_id=session_id, error=str(e))


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/query",
    response_model=EngineQueryResponse,
    summary="Query with Natural Language",
    description="""
Esegue una query in linguaggio naturale attraverso il Tool Calling Engine.

**Flow:**
1. LLM analizza la query e seleziona tool appropriati
2. Tool vengono eseguiti in parallelo
3. Risultati vengono sintetizzati in una risposta coerente

**Esempio:**
```json
{
    "query": "Qual è il prezzo del Bitcoin e che tempo fa a Roma?"
}
```
""",
    responses={
        200: {"description": "Query completata con successo"},
        400: {"description": "Query non valida"},
        500: {"description": "Errore interno"},
    },
)
async def query(
    request: EngineQueryRequest,
    api_key: str | None = Depends(get_optional_api_key),
) -> EngineQueryResponse | StreamingResponse:
    """Esegue query NL → tools → synthesis con integrazione memoria."""
    try:
        engine = await get_engine()

        # ── PRE-QUERY: Build memory context ──────────────────────────────
        # Se session_id presente → arricchisce da Working + Episodic Memory
        # Altrimenti → usa conversation_context manuale (fallback)
        effective_context = request.conversation_context
        routing_query = request.query  # Query usata per routing (potenzialmente riscritta)

        if request.session_id:
            try:
                memory_context = await _build_memory_context(
                    session_id=request.session_id,
                    query=request.query,
                )
                if memory_context:
                    # Merge: memory context + eventuale context manuale
                    if effective_context:
                        effective_context = f"{memory_context}\n\n{effective_context}"
                    else:
                        effective_context = memory_context
                    logger.info(
                        "memory_context_built",
                        session_id=request.session_id,
                        context_length=len(effective_context),
                    )
            except Exception as e:
                logger.warning("memory_context_build_failed", error=str(e))

            # ── PRE-QUERY: Context-Aware Query Rewriting ─────────────────
            # Riscrive la query dell'utente integrando il contesto conversazionale
            # PRIMA del routing, in modo che il router veda la query completa.
            try:
                routing_query = await _rewrite_query_with_context(
                    session_id=request.session_id,
                    query=request.query,
                    llm_client=engine.llm_client,
                )
            except Exception as e:
                logger.warning("query_rewrite_skipped", error=str(e))

        # Streaming mode: SSE con progress events in tempo reale
        if request.stream:
            _session_id = request.session_id
            _original_query = request.query
            _manual_context = request.conversation_context

            async def _event_generator():
                import json as _json
                from contextlib import nullcontext

                # FIX Issue #6: Propagate session_id through contextvars using context manager
                # This ensures session_id is available to ALL async tasks created by engine.run_iterative_stream()
                from me4brain.engine.session_context import session_context

                # Use session_context() context manager to propagate session_id through the entire call stack
                async with session_context(_session_id) if _session_id else nullcontext():
                    full_response_chunks: list[str] = []
                    effective_ctx = _manual_context
                    routing_q = _original_query

                    try:
                        # 1. Feedback immediato: Handshake completato
                        yield f"data: {_json.dumps({'type': 'thinking', 'message': 'Inizializzazione sessione...'})}\n\n"
                        await asyncio.sleep(0.01)  # Yield control

                        # 2. Arricchimento contesto (Memory Layer I + II + III)
                        if _session_id:
                            yield f"data: {_json.dumps({'type': 'thinking', 'message': 'Recupero ricordi e contesto semantico...'})}\n\n"
                            try:
                                memory_context = await _build_memory_context(
                                    session_id=_session_id,
                                    query=_original_query,
                                )
                                if memory_context:
                                    if effective_ctx:
                                        effective_ctx = f"{memory_context}\n\n{effective_ctx}"
                                    else:
                                        effective_ctx = memory_context
                            except Exception as e:
                                logger.warning(
                                    "memory_context_build_failed_in_stream", error=str(e)
                                )

                            # 3. Riscrittura query contestuale
                            yield f"data: {_json.dumps({'type': 'thinking', 'message': 'Analisi intenzione query...'})}\n\n"
                            try:
                                routing_q = await _rewrite_query_with_context(
                                    session_id=_session_id,
                                    query=_original_query,
                                    llm_client=engine.llm_client,
                                )
                            except Exception as e:
                                logger.warning("query_rewrite_failed_in_stream", error=str(e))

                            # 3.5 IMMEDIATE PERSISTENCE: Save user query now to prevent data loss on reload
                            if _session_id:
                                try:
                                    from me4brain.memory import get_working_memory

                                    wm = get_working_memory()
                                    # Save immediately (Layer I only for now, the rest remains post-synthesis)
                                    await wm.add_message(
                                        "default", "default", _session_id, "human", _original_query
                                    )
                                    logger.info(
                                        "early_persistence_user_query", session_id=_session_id
                                    )
                                except Exception as e:
                                    logger.warning("early_persistence_failed", error=str(e))

                        # 4. Esecuzione Engine
                        # FIX Issue #4: Track client disconnection to stop wasting resources
                        _client_disconnected = False

                        async for event in engine.run_iterative_stream(
                            routing_q,
                            context=effective_ctx,
                            session_id=_session_id,
                        ):
                            # FIX Issue #4: Break early if client disconnected
                            if _client_disconnected:
                                logger.info(
                                    "engine_stream_cancelled",
                                    session_id=_session_id,
                                    reason="client_disconnected",
                                )
                                break

                            if event.get("type") == "content":
                                full_response_chunks.append(event.get("content", ""))

                            # ✅ SOTA 2026: Iniezione sistematica session_id per isolamento tab
                            enriched_event = {**event, "session_id": _session_id}

                            try:
                                yield f"data: {_json.dumps(enriched_event, ensure_ascii=False)}\n\n"
                            except (GeneratorExit, ConnectionError, BrokenPipeError):
                                # FIX Issue #4: Client disconnected mid-stream
                                _client_disconnected = True
                                logger.info(
                                    "engine_stream_client_disconnected",
                                    session_id=_session_id,
                                    event_type=event.get("type"),
                                )
                                break

                            event_type = event.get("type")
                            content = event.get("content", "")

                            # DEBUG: Log chunk size to debug 524-character limit issue
                            logger.info(
                                "engine_stream_event_sent",
                                type=event_type,
                                session_id=_session_id,
                                content_length=len(content) if content else 0,
                                content_preview=content[:100] if content else "",
                            )

                    except Exception as stream_err:
                        import traceback

                        tb_str = traceback.format_exc()
                        logger.error("stream_error", error=str(stream_err), traceback=tb_str)
                        error_msg = f"Errore durante l'elaborazione: {str(stream_err)[:100]}"
                        yield f"data: {_json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    finally:
                        yield "data: [DONE]\n\n"

                        # 5. Persistenza interaction (background task)
                        if _session_id and (full_response_chunks or _original_query):
                            full_ans = "".join(full_response_chunks)
                            asyncio.create_task(
                                _persist_interaction(
                                    session_id=_session_id,
                                    query=None,  # Already persisted early
                                    answer=full_ans,
                                )
                            )

            return StreamingResponse(
                _event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        # Non-streaming mode
        query_is_complex = (
            len(request.query) > 300
            or request.query.count(",") >= 2
            or any(
                word in request.query.lower()
                for word in [
                    "analizza",
                    "cerca",
                    "trova",
                    "elenca",
                    "salva",
                    "crea",
                    "analyze",
                    "search",
                    "find",
                    "list",
                    "save",
                    "create",
                    "e poi",
                    "inoltre",
                    "infine",
                    "quindi",
                ]
            )
        )

        # FIX Issue #6: Propagate session_id for non-streaming path
        from me4brain.engine.session_context import session_context as _session_ctx

        async def _run_with_session():
            if request.session_id:
                async with _session_ctx(request.session_id):
                    if query_is_complex:
                        return await engine.run_iterative(routing_query, context=effective_context)
                    else:
                        return await engine.run(routing_query, context=effective_context)
            else:
                if query_is_complex:
                    return await engine.run_iterative(routing_query, context=effective_context)
                else:
                    return await engine.run(routing_query, context=effective_context)

        if query_is_complex:
            logger.info(
                "using_iterative_execution",
                query_preview=routing_query[:50],
                reason="complex_query_detected",
            )
        result = await _run_with_session()

        # Costruisci risposta
        tools_called = [
            ToolCallInfo(
                tool_name=tr.tool_name,
                arguments={},
                success=tr.success,
                latency_ms=tr.latency_ms,
                error=tr.error,
            )
            for tr in result.tool_results
        ]

        response = EngineQueryResponse(
            query=result.query if hasattr(result, "query") else request.query,
            answer=result.answer,
            tools_called=tools_called,
            total_latency_ms=result.total_latency_ms,
            raw_results=[tr.data for tr in result.tool_results if tr.success and tr.data]
            if request.include_raw_results
            else None,
        )

        logger.info(
            "engine_query_completed",
            query_preview=request.query[:50],
            tools_count=len(tools_called),
            latency_ms=result.total_latency_ms,
        )

        # ── POST-QUERY: Persist interaction (fire-and-forget) ────────
        if request.session_id:
            asyncio.create_task(
                _persist_interaction(
                    session_id=request.session_id,
                    query=request.query,
                    answer=result.answer,
                )
            )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("engine_query_failed", error=str(e), query=request.query[:50])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Query failed: {e}",
        )


@router.post(
    "/call",
    response_model=EngineCallResponse,
    summary="Direct Tool Call",
    description="""
Chiama direttamente un tool per nome con gli argomenti specificati.

**Esempio:**
```json
{
    "tool_name": "coingecko_price",
    "arguments": {"ids": "bitcoin", "vs_currencies": "usd"}
}
```
""",
    responses={
        200: {"description": "Tool eseguito con successo"},
        404: {"description": "Tool non trovato"},
        500: {"description": "Esecuzione fallita"},
    },
)
async def call_tool(
    request: EngineCallRequest,
    api_key: str | None = Depends(get_optional_api_key),
) -> EngineCallResponse:
    """Chiama direttamente un tool."""
    import time

    try:
        engine = await get_engine()

        # Verifica che il tool esista
        tool = engine.catalog.get_tool(request.tool_name)
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {request.tool_name}",
            )

        # Ottieni executor
        executor_func = engine.catalog.get_executor(request.tool_name)
        if not executor_func:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Executor not found for tool: {request.tool_name}",
            )

        # Esegui
        start = time.perf_counter()
        try:
            result = await executor_func(**request.arguments)
            latency_ms = (time.perf_counter() - start) * 1000

            return EngineCallResponse(
                tool_name=request.tool_name,
                success=True,
                result=result,
                error=None,
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start) * 1000
            return EngineCallResponse(
                tool_name=request.tool_name,
                success=False,
                result=None,
                error=str(e),
                latency_ms=latency_ms,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "engine_call_failed",
            tool_name=request.tool_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Call failed: {e}",
        )


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="List Available Tools",
    description="Lista tutti i tool disponibili nel catalog con filtri opzionali.",
)
async def list_tools(
    domain: str | None = Query(
        default=None,
        description="Filtra per dominio (es. 'finance_crypto', 'geo_weather')",
    ),
    category: str | None = Query(
        default=None,
        description="Filtra per categoria (es. 'crypto', 'weather')",
    ),
    search: str | None = Query(
        default=None,
        description="Cerca nel nome/descrizione dei tool",
    ),
    api_key: str | None = Depends(get_optional_api_key),
) -> ToolListResponse:
    """Lista tool dal catalog."""
    try:
        engine = await get_engine()

        all_tools = engine.catalog.get_all_tools()

        # Applica filtri
        filtered = all_tools

        if domain:
            filtered = [t for t in filtered if t.domain == domain]

        if category:
            filtered = [t for t in filtered if t.category == category]

        if search:
            search_lower = search.lower()
            filtered = [
                t
                for t in filtered
                if search_lower in t.name.lower() or search_lower in (t.description or "").lower()
            ]

        # Converti a ToolInfo
        tools_info = [
            ToolInfo(
                name=t.name,
                description=t.description,
                domain=t.domain,
                category=t.category,
                parameters={
                    name: {
                        "type": param.type,
                        "description": param.description,
                        "required": param.required,
                    }
                    for name, param in t.parameters.items()
                },
            )
            for t in filtered
        ]

        # Estrai domini unici
        domains = sorted(set(t.domain for t in all_tools if t.domain))

        return ToolListResponse(
            tools=tools_info,
            total=len(tools_info),
            domains=domains,
        )

    except Exception as e:
        logger.error("engine_list_tools_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"List failed: {e}",
        )


@router.get(
    "/tools/{tool_name}",
    response_model=ToolInfo,
    summary="Get Tool Details",
    description="Ottiene i dettagli di un tool specifico.",
    responses={
        200: {"description": "Tool trovato"},
        404: {"description": "Tool non trovato"},
    },
)
async def get_tool(
    tool_name: str,
    api_key: str | None = Depends(get_optional_api_key),
) -> ToolInfo:
    """Dettagli di un singolo tool."""
    try:
        engine = await get_engine()

        tool = engine.catalog.get_tool(tool_name)
        if not tool:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Tool not found: {tool_name}",
            )

        return ToolInfo(
            name=tool.name,
            description=tool.description,
            domain=tool.domain,
            category=tool.category,
            parameters={
                name: {
                    "type": param.type,
                    "description": param.description,
                    "required": param.required,
                }
                for name, param in tool.parameters.items()
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "engine_get_tool_failed",
            tool_name=tool_name,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Get tool failed: {e}",
        )


@router.get(
    "/stats",
    response_model=CatalogStatsResponse,
    summary="Get Catalog Statistics",
    description="Statistiche sul catalog dei tool per dominio.",
)
async def get_stats(
    api_key: str | None = Depends(get_optional_api_key),
) -> CatalogStatsResponse:
    """Statistiche del catalog."""
    try:
        engine = await get_engine()

        all_tools = engine.catalog.get_all_tools()

        # Raggruppa per dominio
        domain_tools: dict[str, list[str]] = {}
        for tool in all_tools:
            domain = tool.domain or "unknown"
            if domain not in domain_tools:
                domain_tools[domain] = []
            domain_tools[domain].append(tool.name)

        # Costruisci stats
        domains = [
            DomainStats(
                domain=domain,
                tool_count=len(tools),
                tools=sorted(tools),
            )
            for domain, tools in sorted(domain_tools.items())
        ]

        return CatalogStatsResponse(
            total_tools=len(all_tools),
            domains=domains,
        )

    except Exception as e:
        logger.error("engine_stats_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Stats failed: {e}",
        )
