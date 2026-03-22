"""Me4BrAIn Core - Cognitive State.

Definisce lo stato condiviso tra i nodi del grafo LangGraph.
Basato su TypedDict per compatibilità con LangGraph.
"""

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Messaggio nel thread di conversazione."""

    role: Literal["human", "ai", "system", "tool"]
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    """Risultato di un retrieval (episodico o semantico)."""

    source: Literal["episodic", "semantic", "procedural"]
    content: str
    score: float
    entity_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Richiesta di chiamata tool."""

    tool_name: str
    tool_id: str
    arguments: dict[str, Any]
    from_muscle_memory: bool = False


class ToolResult(BaseModel):
    """Risultato di una chiamata tool."""

    tool_name: str
    success: bool
    result: Any
    error: str | None = None
    latency_ms: float = 0.0


class ConflictInfo(BaseModel):
    """Informazioni su un conflitto rilevato."""

    vector_answer: str
    graph_answer: str
    resolution: Literal["vector", "graph", "merged"]
    reason: str


class CognitiveState(TypedDict, total=False):
    """Stato cognitivo condiviso tra i nodi LangGraph.

    Questo è il "cervello" dell'agente durante un ciclo di ragionamento.
    Ogni campo rappresenta un aspetto dello stato mentale.
    """

    # Identificatori
    tenant_id: str
    user_id: str
    session_id: str
    thread_id: str

    # Conversazione
    messages: list[dict[str, Any]]  # Serialized Messages
    current_input: str
    current_input_embedding: list[float]

    # Routing
    query_type: Literal["simple", "complex", "tool_required"]
    routing_decision: Literal["vector_only", "graph_only", "hybrid"]
    routing_confidence: float

    # Retrieval
    lightrag_results: list[dict[str, Any]]
    episodic_results: list[dict[str, Any]]  # Serialized RetrievalResults
    semantic_results: list[dict[str, Any]]
    procedural_results: list[dict[str, Any]]

    # Conflict Resolution
    has_conflict: bool
    conflict_info: dict[str, Any] | None  # Serialized ConflictInfo

    # Reasoning (ToG-2)
    reasoning_steps: list[str]
    current_reasoning: str
    graph_traversal_path: list[str]

    # Tool Execution
    selected_tool: dict[str, Any] | None  # Serialized ToolCall
    tool_result: dict[str, Any] | None  # Serialized ToolResult
    muscle_memory_hit: bool

    # Output
    final_response: str
    confidence: float
    sources_used: list[str]

    # Metadata
    iteration_count: int
    max_iterations: int
    started_at: str
    completed_at: str | None


def create_initial_state(
    tenant_id: str,
    user_id: str,
    session_id: str,
    thread_id: str,
    user_input: str,
    max_iterations: int = 5,
) -> CognitiveState:
    """Crea lo stato iniziale per un nuovo ciclo cognitivo.

    Args:
        tenant_id: ID del tenant
        user_id: ID dell'utente
        session_id: ID della sessione corrente
        thread_id: ID del thread LangGraph
        user_input: Input dell'utente
        max_iterations: Numero massimo di iterazioni

    Returns:
        Stato iniziale del ciclo cognitivo
    """
    return CognitiveState(
        # Identificatori
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        thread_id=thread_id,
        # Conversazione
        messages=[],
        current_input=user_input,
        current_input_embedding=[],
        # Routing
        query_type="simple",
        routing_decision="vector_only",
        routing_confidence=0.0,
        # Retrieval
        lightrag_results=[],
        episodic_results=[],
        semantic_results=[],
        procedural_results=[],
        # Conflict
        has_conflict=False,
        conflict_info=None,
        # Reasoning
        reasoning_steps=[],
        current_reasoning="",
        graph_traversal_path=[],
        # Tool
        selected_tool=None,
        tool_result=None,
        muscle_memory_hit=False,
        # Output
        final_response="",
        confidence=0.0,
        sources_used=[],
        # Metadata
        iteration_count=0,
        max_iterations=max_iterations,
        started_at=datetime.now(UTC).isoformat(),
        completed_at=None,
    )
