"""LangGraph Cognitive Orchestrator.

Implementa il ciclo cognitivo principale usando LangGraph.
Pattern Think-on-Graph 2.0 con retrieval ibrido.
"""

from datetime import UTC, datetime
from typing import Any, Literal

import structlog
from langgraph.graph import END, StateGraph

from me4brain.core.conflict import ConflictSource, get_conflict_resolver
from me4brain.core.router import get_semantic_router
from me4brain.core.state import CognitiveState, create_initial_state
from me4brain.embeddings import get_embedding_service
from me4brain.memory import (
    get_procedural_memory,
    get_working_memory,
)
from me4brain.retrieval.lightrag import LightRAG

logger = structlog.get_logger(__name__)


# =============================================================================
# LightRAG Instance (Singleton)
# =============================================================================
_lightrag_engine = None


def get_lightrag_engine() -> LightRAG:
    """Ottiene l'istanza singleton di LightRAG."""
    global _lightrag_engine
    if _lightrag_engine is None:
        _lightrag_engine = LightRAG()
    return _lightrag_engine


# =============================================================================
# Node Functions
# =============================================================================


async def embed_input(state: CognitiveState) -> dict[str, Any]:
    """Nodo: calcola embedding dell'input utente."""
    embedding_service = get_embedding_service()
    embedding = embedding_service.embed_query(state["current_input"])

    logger.debug(
        "input_embedded",
        input_length=len(state["current_input"]),
        embedding_dim=len(embedding),
    )

    return {"current_input_embedding": embedding}


async def route_query(state: CognitiveState) -> dict[str, Any]:
    """Nodo: classifica la query e decide il routing."""
    router = get_semantic_router()

    result = router.route(
        query=state["current_input"],
        query_embedding=state.get("current_input_embedding"),
    )

    logger.info(
        "query_routed",
        query_type=result.query_type.value,
        decision=result.decision.value,
        confidence=result.confidence,
    )

    return {
        "query_type": result.query_type.value,
        "routing_decision": result.decision.value,
        "routing_confidence": result.confidence,
    }


async def retrieve_lightrag(state: CognitiveState) -> dict[str, Any]:
    """Nodo: retrieval unificato (Local + Global) via LightRAG.

    Implementa SOTA 2026: RRF Fusion tra vettori (Qdrant) e grafo (KuzuDB).
    """
    engine = get_lightrag_engine()

    results = await engine.dual_retrieval(
        query=state["current_input"], tenant_id=state["tenant_id"], top_k=8
    )

    # Mappiamo i risultati nel formato atteso dai downstream (legacy support)
    lightrag_results = [
        {"content": r.content, "source": r.source, "score": r.score, "metadata": r.metadata}
        for r in results
    ]

    logger.info(
        "lightrag_retrieved",
        count=len(lightrag_results),
        top_source=lightrag_results[0]["source"] if lightrag_results else "none",
    )

    return {
        "lightrag_results": lightrag_results,
        "episodic_results": [r for r in lightrag_results if r["source"] == "local"],
        "semantic_results": [r for r in lightrag_results if r["source"] == "global"],
    }


async def check_muscle_memory(state: CognitiveState) -> dict[str, Any]:
    """Nodo: verifica se esiste un'esecuzione simile in Muscle Memory.

    Se trova un match, può bypassare il ragionamento completo.
    """
    if state["routing_decision"] != "tool_required":
        return {"muscle_memory_hit": False}

    procedural = get_procedural_memory()

    execution = await procedural.find_similar_execution(
        tenant_id=state["tenant_id"],
        intent_embedding=state["current_input_embedding"],
        min_score=0.85,
    )

    if execution:
        logger.info(
            "muscle_memory_hit",
            tool=execution.tool_name,
            original_intent=execution.intent[:50],
        )
        return {
            "muscle_memory_hit": True,
            "selected_tool": {
                "tool_name": execution.tool_name,
                "tool_id": execution.tool_id,
                "arguments": execution.input_json,
                "from_muscle_memory": True,
            },
        }

    return {"muscle_memory_hit": False}


async def resolve_conflicts(state: CognitiveState) -> dict[str, Any]:
    """Nodo: risolve conflitti tra risultati episodici e semantici."""
    # Se i risultati provengono da LightRAG, la fusione è già avvenuta via RRF
    if state.get("lightrag_results"):
        return {"has_conflict": False}

    episodic_results = state.get("episodic_results", [])
    semantic_results = state.get("semantic_results", [])

    # Se non abbiamo entrambi, nessun conflitto
    if not episodic_results or not semantic_results:
        return {"has_conflict": False}

    # Prendi i top result di ciascuno
    top_episodic = episodic_results[0] if episodic_results else None
    top_semantic = semantic_results[0] if semantic_results else None

    if not top_episodic or not top_semantic:
        return {"has_conflict": False}

    # Converti in ConflictSource
    resolver = get_conflict_resolver()

    vector_source = ConflictSource(
        source_type="episodic",
        content=top_episodic["content"],
        score=top_episodic["score"],
        timestamp=datetime.fromisoformat(
            top_episodic["metadata"].get("event_time", datetime.now(UTC).isoformat())
        ),
        entity_id=top_episodic.get("entity_id"),
    )

    graph_source = ConflictSource(
        source_type="semantic",
        content=top_semantic["content"],
        score=top_semantic["score"],
        timestamp=datetime.fromisoformat(
            top_semantic["metadata"].get("created_at", datetime.now(UTC).isoformat())
        ),
        entity_id=top_semantic.get("entity_id"),
    )

    # Rileva conflitto
    has_conflict = resolver.detect_conflict(vector_source, graph_source)

    if not has_conflict:
        return {"has_conflict": False}

    # Risolvi conflitto (Recency Bias di default)
    resolution = resolver.resolve(vector_source, graph_source, strategy="recency")

    logger.info(
        "conflict_resolved",
        winner=resolution.winner.source_type,
        strategy=resolution.strategy,
        confidence=resolution.confidence,
    )

    return {
        "has_conflict": True,
        "conflict_info": {
            "vector_answer": vector_source.content,
            "graph_answer": graph_source.content,
            "resolution": resolution.winner.source_type,
            "reason": resolution.explanation,
        },
    }


async def generate_response(state: CognitiveState) -> dict[str, Any]:
    """Nodo: genera la risposta finale usando NanoGPT LLM.

    Prima prova a usare tool (LLM-based decision), poi genera risposta.
    """
    from me4brain.core.tool_agent import run_tool_agent
    from me4brain.llm import LLMRequest, Message, NanoGPTClient, get_llm_config

    # Step 1: Prova tool calling (LLM decide se serve)
    tool_result = await run_tool_agent(
        tenant_id=state.get("tenant_id", "me4brain_core"),
        query=state["current_input"],
        query_embedding=state.get("current_input_embedding"),
    )

    if tool_result.get("used_tool") and tool_result.get("formatted_response"):
        # Tool usato con successo - restituisci risposta formattata
        logger.info(
            "response_from_tool",
            tool_name=tool_result.get("tool_name"),
            success=tool_result.get("tool_result", {}).get("success", False),
        )

        return {
            "final_response": tool_result["formatted_response"],
            "confidence": 0.85 if tool_result.get("tool_result", {}).get("success") else 0.5,
            "sources_used": [f"tool:{tool_result.get('tool_name', 'unknown')}"],
            "completed_at": datetime.now(UTC).isoformat(),
            "tool_used": tool_result.get("tool_name"),
            "tool_result": tool_result.get("tool_result"),
        }

    # Step 2: Nessun tool - genera risposta normale
    config = get_llm_config()
    client = NanoGPTClient(
        api_key=config.nanogpt_api_key,
        base_url=config.nanogpt_base_url,
    )

    sources_used = []
    context_str = ""

    # Raccogli contesto da tutte le fonti
    if state.get("lightrag_results"):
        context_str += "\n## Hybrid Knowledge (LightRAG Local+Global)\n"
        for result in state["lightrag_results"][:5]:
            context_str += f"- [{result['source']}] {result['content']}\n"
            sources_used.append(f"lightrag:{result['source']}")
    else:
        # Fallback se LightRAG non ha restituito nulla ma ci sono risultati legacy
        if state.get("episodic_results"):
            context_str += "\n## Episodic Memory\n"
            for result in state["episodic_results"][:3]:
                context_str += f"- {result['content']}\n"
                sources_used.append(f"episodic:{result.get('entity_id', 'unknown')}")

        if state.get("semantic_results"):
            context_str += "\n## Semantic Memory\n"
            for result in state["semantic_results"][:3]:
                context_str += f"- {result['content']}\n"
                sources_used.append(f"semantic:{result.get('entity_id', 'unknown')}")

    # Se c'era conflitto, nota la risoluzione
    if state.get("has_conflict") and state.get("conflict_info"):
        conflict = state["conflict_info"]
        context_str += (
            f"\n## Conflict Resolution\n{conflict['reason']} (Strategy: {conflict['resolution']})\n"
        )

    # Costruisci Prompt
    system_prompt = (
        "You are Me4BrAIn, an advanced AI memory system. "
        "Answer the user query based primarily on the provided context. "
        "If the context is insufficient, use your general knowledge but mention it. "
        "Be concise, accurate, and professional."
    )

    user_message = f"Query: {state['current_input']}\n\nContext Retrieved:\n{context_str}"

    # Usa il modello Primary Thinking (DeepSeek V3.2 Speciale)
    request = LLMRequest(
        model=config.model_primary_thinking,
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_message),
        ],
        temperature=0.7,
        max_tokens=1024,
    )

    try:
        response = await client.generate_response(request)
        final_response = response.content or "Error generating response."
        reasoning = response.reasoning

        # Calcola confidence basata su retrieval
        routing_conf = state.get("routing_confidence", 0.5)
        result_count = len(state.get("episodic_results", [])) + len(
            state.get("semantic_results", [])
        )
        confidence = min(0.95, routing_conf * 0.4 + min(result_count / 5, 1.0) * 0.6)

        logger.info(
            "response_generated",
            sources_count=len(sources_used),
            confidence=confidence,
            latency_ms=response.latency_ms,
        )

        return {
            "final_response": final_response,
            "confidence": confidence,
            "sources_used": sources_used,
            "completed_at": datetime.now(UTC).isoformat(),
            "reasoning_trace": [reasoning] if reasoning else [],
        }

    except Exception as e:
        logger.error("llm_generation_failed", error=str(e))
        return {
            "final_response": "I encountered an error generating the response. Please try again.",
            "confidence": 0.0,
            "sources_used": sources_used,
            "completed_at": datetime.now(UTC).isoformat(),
        }


async def update_working_memory(state: CognitiveState) -> dict[str, Any]:
    """Nodo: aggiorna la working memory con il nuovo turno."""
    working = get_working_memory()

    # Salva messaggio utente
    await working.add_message(
        tenant_id=state["tenant_id"],
        user_id=state.get("user_id", ""),
        session_id=state["session_id"],
        role="human",
        content=state["current_input"],
    )

    # Salva risposta AI
    await working.add_message(
        tenant_id=state["tenant_id"],
        user_id=state.get("user_id", ""),
        session_id=state["session_id"],
        role="ai",
        content=state.get("final_response", ""),
        metadata={"confidence": state.get("confidence", 0)},
    )

    # Persisti grafo sessione
    await working.persist_graph(
        tenant_id=state["tenant_id"],
        user_id=state.get("user_id", ""),
        session_id=state["session_id"],
    )

    logger.debug("working_memory_updated", session=state["session_id"])

    return {"iteration_count": state.get("iteration_count", 0) + 1}


# =============================================================================
# Conditional Edges
# =============================================================================


def should_retrieve_graph(state: CognitiveState) -> Literal["graph", "vector", "both", "none"]:
    """Decide quale tipo di retrieval eseguire."""
    decision = state.get("routing_decision", "vector_only")

    if decision == "vector_only":
        return "vector"
    elif decision == "graph_only":
        return "graph"
    elif decision == "hybrid":
        return "both"
    elif decision == "no_retrieval":
        return "none"
    else:
        return "vector"  # Default


def should_continue(state: CognitiveState) -> Literal["continue", "end"]:
    """Decide se continuare l'iterazione o terminare."""
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 5)

    if iteration >= max_iter:
        return "end"

    # Se abbiamo una risposta finale, termina
    if state.get("final_response"):
        return "end"

    return "continue"


# =============================================================================
# Graph Builder
# =============================================================================


def build_cognitive_graph() -> StateGraph:
    """Costruisce il grafo LangGraph per il ciclo cognitivo.

    Architettura:
    1. embed_input: Calcola embedding query
    2. route_query: Classifica e decide routing
    3. retrieve_*: Retrieval parallelo (condizionale)
    4. check_muscle_memory: Verifica cache procedurale
    5. resolve_conflicts: Gestisce conflitti Vector vs Graph
    6. generate_response: Sintetizza risposta
    7. update_working_memory: Persiste stato

    Returns:
        StateGraph compilato
    """
    # Crea grafo
    graph = StateGraph(CognitiveState)

    # Aggiungi nodi
    graph.add_node("embed_input", embed_input)
    graph.add_node("route_query", route_query)
    graph.add_node("retrieve_lightrag", retrieve_lightrag)
    graph.add_node("check_muscle_memory", check_muscle_memory)
    graph.add_node("resolve_conflicts", resolve_conflicts)
    graph.add_node("generate_response", generate_response)
    graph.add_node("update_working_memory", update_working_memory)

    # Entry point
    graph.set_entry_point("embed_input")

    # Edge: embed -> route
    graph.add_edge("embed_input", "route_query")

    # Conditional edge: route -> retrieve (basato su routing_decision)
    graph.add_conditional_edges(
        "route_query",
        should_retrieve_graph,
        {
            "vector": "retrieve_lightrag",
            "graph": "retrieve_lightrag",
            "both": "retrieve_lightrag",
            "none": "generate_response",
        },
    )

    # Edge: lightrag -> muscle memory
    graph.add_edge("retrieve_lightrag", "check_muscle_memory")

    # Edge: muscle memory -> conflicts
    graph.add_edge("check_muscle_memory", "resolve_conflicts")

    # Edge: conflicts -> generate
    graph.add_edge("resolve_conflicts", "generate_response")

    # Edge: generate -> update memory
    graph.add_edge("generate_response", "update_working_memory")

    # Edge: update -> END
    graph.add_edge("update_working_memory", END)

    return graph


# =============================================================================
# Compiled Graph (Singleton)
# =============================================================================

_compiled_graph = None


def get_cognitive_graph():
    """Ottiene il grafo compilato (singleton)."""
    global _compiled_graph
    if _compiled_graph is None:
        graph = build_cognitive_graph()
        _compiled_graph = graph.compile()
    return _compiled_graph


async def run_cognitive_cycle(
    tenant_id: str,
    user_id: str,
    session_id: str,
    user_input: str,
    thread_id: str | None = None,
) -> CognitiveState:
    """Esegue un ciclo cognitivo completo.

    Args:
        tenant_id: ID del tenant
        user_id: ID dell'utente
        session_id: ID della sessione
        user_input: Input dell'utente
        thread_id: ID del thread LangGraph (opzionale)

    Returns:
        Stato finale del ciclo cognitivo
    """
    from uuid import uuid4

    thread_id = thread_id or str(uuid4())

    # Crea stato iniziale
    initial_state = create_initial_state(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        thread_id=thread_id,
        user_input=user_input,
    )

    # Esegui grafo
    graph = get_cognitive_graph()

    config = {"configurable": {"thread_id": thread_id}}

    final_state = await graph.ainvoke(initial_state, config=config)

    logger.info(
        "cognitive_cycle_completed",
        thread_id=thread_id,
        confidence=final_state.get("confidence", 0),
        sources=len(final_state.get("sources_used", [])),
    )

    return final_state
