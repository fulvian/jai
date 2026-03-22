"""Working Memory API Routes.

Endpoints per gestione sessioni e short-term memory:
- Sessions: create, delete, info
- Messages: add, list
- Graph: entities, relations, export
- Reference resolution
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from me4brain.api.middleware.auth import (
    AuthenticatedUser,
    get_current_user_dev as get_current_user,
)
from me4brain.memory.working import WorkingMemory

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/working", tags=["Working Memory"])


# =============================================================================
# Request/Response Models
# =============================================================================


class TemplatePromptModel(BaseModel):
    """Singolo prompt template."""

    id: str
    label: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=10000)
    enabled: bool = True
    variables: list[str] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class SessionConfigRequest(BaseModel):
    """Config sessione categorizzata."""

    session_type: str = Field(
        default="free",
        pattern="^(free|topic|template)$",
        description="Tipo sessione: free, topic, template",
    )
    topic: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = Field(default=None, max_items=20)
    prompts: list[TemplatePromptModel] | None = None
    schedule: str | None = Field(
        default=None, max_length=100, description="Cron expression (futuro)"
    )


class CreateSessionRequest(BaseModel):
    """Richiesta creazione sessione."""

    user_id: str = Field(..., min_length=1, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    config: SessionConfigRequest | None = None


class CreateSessionResponse(BaseModel):
    """Risposta creazione sessione."""

    session_id: str
    user_id: str
    created_at: datetime


class AddMessageRequest(BaseModel):
    """Richiesta aggiunta messaggio."""

    role: str = Field(..., pattern="^(human|ai|user|assistant|system|tool)$")
    content: str = Field(..., min_length=1, max_length=50000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    """Singolo messaggio."""

    id: str
    role: str
    content: str
    timestamp: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessagesResponse(BaseModel):
    """Lista messaggi."""

    session_id: str
    messages: list[MessageResponse]
    count: int


class AddEntityRequest(BaseModel):
    """Richiesta aggiunta entità al grafo."""

    entity_id: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(..., min_length=1, max_length=50)
    label: str = Field(..., min_length=1, max_length=255)
    properties: dict[str, Any] = Field(default_factory=dict)


class AddRelationRequest(BaseModel):
    """Richiesta aggiunta relazione."""

    source_id: str = Field(..., min_length=1)
    target_id: str = Field(..., min_length=1)
    relation_type: str = Field(..., min_length=1, max_length=50)
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    """Nodo del grafo."""

    id: str
    type: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """Arco del grafo."""

    source: str
    target: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    """Grafo sessione."""

    session_id: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int
    edge_count: int


class ResolveRequest(BaseModel):
    """Richiesta risoluzione riferimento."""

    reference: str = Field(..., min_length=1, description="Es: 'lui', 'il progetto'")
    entity_type: str | None = Field(default=None, description="Filtra per tipo")


class ResolveResponse(BaseModel):
    """Risposta risoluzione."""

    reference: str
    resolved_entity_id: str | None
    resolved_label: str | None
    confidence: float


class SessionInfoResponse(BaseModel):
    """Info sessione singola."""

    session_id: str
    title: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    message_count: int = 0
    session_type: str = "free"
    topic: str | None = None
    tags: list[str] | None = None
    prompts: list[TemplatePromptModel] | None = None
    schedule: str | None = None


class SessionsListResponse(BaseModel):
    """Lista sessioni."""

    sessions: list[SessionInfoResponse]
    count: int


class UpdateSessionRequest(BaseModel):
    """Richiesta aggiornamento sessione."""

    title: str = Field(..., min_length=1, max_length=255)


class UpdateSessionConfigRequest(BaseModel):
    """Richiesta aggiornamento config sessione."""

    session_type: str | None = Field(default=None, pattern="^(free|topic|template)$")
    topic: str | None = Field(default=None, max_length=255)
    tags: list[str] | None = Field(default=None, max_items=20)
    prompts: list[TemplatePromptModel] | None = None
    schedule: str | None = Field(default=None, max_length=100)


# =============================================================================
# Singleton WorkingMemory
# =============================================================================

_working_memory: WorkingMemory | None = None


async def get_working_memory() -> WorkingMemory:
    """Lazy init WorkingMemory."""
    global _working_memory
    if _working_memory is None:
        _working_memory = WorkingMemory()
    return _working_memory


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_session(
    request: CreateSessionRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> CreateSessionResponse:
    """Crea una nuova sessione di working memory."""
    session_id = str(uuid.uuid4())
    tenant_id = user.tenant_id

    # Prepara parametri config sessione
    config = request.config
    register_kwargs: dict[str, Any] = {
        "tenant_id": tenant_id,
        "user_id": request.user_id,
        "session_id": session_id,
        "title": request.metadata.get("title"),
    }
    if config:
        register_kwargs["session_type"] = config.session_type
        if config.topic is not None:
            register_kwargs["topic"] = config.topic
        if config.tags is not None:
            register_kwargs["tags"] = config.tags
        if config.prompts is not None:
            register_kwargs["prompts"] = [p.model_dump() for p in config.prompts]
        if config.schedule is not None:
            register_kwargs["schedule"] = config.schedule

    # Registra sessione nell'indice per list_sessions
    await wm.register_session(**register_kwargs)

    # Inizializza la sessione con un messaggio system
    await wm.add_message(
        tenant_id=tenant_id,
        user_id=request.user_id,
        session_id=session_id,
        role="system",
        content="Session initialized",
        metadata=request.metadata,
    )

    logger.info(
        "working_session_created",
        session_id=session_id,
        user_id=request.user_id,
        tenant_id=tenant_id,
        session_type=config.session_type if config else "free",
    )

    return CreateSessionResponse(
        session_id=session_id,
        user_id=request.user_id,
        created_at=datetime.now(UTC),
    )


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Elimina una sessione."""
    await wm.clear_session(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
    )

    logger.info("working_session_deleted", session_id=session_id)
    return {"deleted": True, "session_id": session_id}


@router.get("/sessions", response_model=SessionsListResponse)
async def list_sessions(
    user_id: str,
    limit: int = 50,
    session_type: str | None = None,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> SessionsListResponse:
    """Lista sessioni utente con metadati. Filtra opzionalmente per tipo."""
    sessions = await wm.list_sessions(
        tenant_id=user.tenant_id,
        user_id=user_id,
        limit=limit,
    )

    # Filtra per session_type se specificato
    if session_type:
        sessions = [s for s in sessions if s.get("session_type", "free") == session_type]

    return SessionsListResponse(
        sessions=[
            SessionInfoResponse(
                session_id=s["session_id"],
                title=s.get("title") or None,
                created_at=datetime.fromisoformat(s["created_at"]) if s.get("created_at") else None,
                updated_at=datetime.fromisoformat(s["updated_at"]) if s.get("updated_at") else None,
                message_count=s.get("message_count", 0),
                session_type=s.get("session_type", "free"),
                topic=s.get("topic"),
                tags=s.get("tags"),
            )
            for s in sessions
        ],
        count=len(sessions),
    )


@router.get("/sessions/{session_id}", response_model=SessionInfoResponse)
async def get_session(
    session_id: str,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> SessionInfoResponse:
    """Recupera info di una sessione."""
    meta = await wm.get_session_metadata(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
    )

    if not meta:
        raise HTTPException(status_code=404, detail="Session not found")

    # Conta messaggi
    r = await wm.get_redis()
    stream_key = wm._stream_key(user.tenant_id, user_id, session_id)
    msg_count = await r.xlen(stream_key)

    # Prepara prompts come modelli Pydantic
    prompts_raw = meta.get("prompts")
    prompts = None
    if prompts_raw and isinstance(prompts_raw, list):
        prompts = [TemplatePromptModel(**p) for p in prompts_raw]

    return SessionInfoResponse(
        session_id=session_id,
        title=meta.get("title") or None,
        created_at=datetime.fromisoformat(meta["created_at"]) if meta.get("created_at") else None,
        updated_at=datetime.fromisoformat(meta["updated_at"]) if meta.get("updated_at") else None,
        message_count=msg_count,
        session_type=meta.get("session_type", "free"),
        topic=meta.get("topic"),
        tags=meta.get("tags") if isinstance(meta.get("tags"), list) else None,
        prompts=prompts,
        schedule=meta.get("schedule"),
    )


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    request: UpdateSessionRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Aggiorna metadati sessione (es. titolo)."""
    success = await wm.update_session_metadata(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        title=request.title,
    )

    logger.info(
        "working_session_updated",
        session_id=session_id,
        title=request.title,
    )

    return {"updated": success, "session_id": session_id, "title": request.title}


@router.patch("/sessions/{session_id}/config")
async def update_session_config(
    session_id: str,
    request: UpdateSessionConfigRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Aggiorna la configurazione di una sessione (tipo, topic, tags, prompts)."""
    update_kwargs: dict[str, Any] = {
        "tenant_id": user.tenant_id,
        "user_id": user_id,
        "session_id": session_id,
    }

    if request.session_type is not None:
        update_kwargs["session_type"] = request.session_type
    if request.topic is not None:
        update_kwargs["topic"] = request.topic
    if request.tags is not None:
        update_kwargs["tags"] = request.tags
    if request.prompts is not None:
        update_kwargs["prompts"] = [p.model_dump() for p in request.prompts]
    if request.schedule is not None:
        update_kwargs["schedule"] = request.schedule

    success = await wm.update_session_metadata(**update_kwargs)

    logger.info(
        "working_session_config_updated",
        session_id=session_id,
        session_type=request.session_type,
    )

    return {"updated": success, "session_id": session_id}


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
async def add_message(
    session_id: str,
    request: AddMessageRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> MessageResponse:
    """Aggiunge un messaggio alla sessione."""
    message_id = await wm.add_message(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata,
    )

    return MessageResponse(
        id=message_id,
        role=request.role,
        content=request.content,
        timestamp=datetime.now(UTC).isoformat(),
        metadata=request.metadata,
    )


@router.get("/sessions/{session_id}/messages", response_model=MessagesResponse)
async def get_messages(
    session_id: str,
    user_id: str,
    count: int = 20,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> MessagesResponse:
    """Recupera gli ultimi N messaggi della sessione."""
    messages = await wm.get_messages(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        count=count,
    )

    return MessagesResponse(
        session_id=session_id,
        messages=[
            MessageResponse(
                id=m.get("id", ""),
                role=m.get("role", ""),
                content=m.get("content", ""),
                timestamp=m.get("timestamp", ""),
                metadata=m.get("metadata", {}),
            )
            for m in messages
        ],
        count=len(messages),
    )


@router.post("/sessions/{session_id}/entities")
async def add_entity(
    session_id: str,
    request: AddEntityRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Aggiunge un'entità al grafo di sessione."""
    await wm.add_entity(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        entity_id=request.entity_id,
        entity_type=request.entity_type,
        label=request.label,
        properties=request.properties,
    )

    return {
        "added": True,
        "entity_id": request.entity_id,
        "session_id": session_id,
    }


@router.post("/sessions/{session_id}/relations")
async def add_relation(
    session_id: str,
    request: AddRelationRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Aggiunge una relazione tra entità nel grafo."""
    await wm.add_relation(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        source_id=request.source_id,
        target_id=request.target_id,
        relation_type=request.relation_type,
        properties=request.properties,
    )

    return {
        "added": True,
        "source_id": request.source_id,
        "target_id": request.target_id,
        "relation_type": request.relation_type,
    }


@router.get("/sessions/{session_id}/graph", response_model=GraphResponse)
async def get_session_graph(
    session_id: str,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> GraphResponse:
    """Esporta il grafo della sessione."""
    graph = await wm.get_session_graph(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
    )

    nodes = []
    edges = []

    if graph is not None:
        for node_id, data in graph.nodes(data=True):
            nodes.append(
                GraphNode(
                    id=str(node_id),
                    type=data.get("type", "unknown"),
                    label=data.get("label", str(node_id)),
                    properties={k: v for k, v in data.items() if k not in ("type", "label")},
                )
            )

        for source, target, data in graph.edges(data=True):
            edges.append(
                GraphEdge(
                    source=str(source),
                    target=str(target),
                    type=data.get("type", "RELATED_TO"),
                    properties={k: v for k, v in data.items() if k != "type"},
                )
            )

    return GraphResponse(
        session_id=session_id,
        nodes=nodes,
        edges=edges,
        node_count=len(nodes),
        edge_count=len(edges),
    )


@router.post("/sessions/{session_id}/resolve", response_model=ResolveResponse)
async def resolve_reference(
    session_id: str,
    request: ResolveRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> ResolveResponse:
    """Risolve un riferimento ambiguo usando il grafo di sessione."""
    resolved_id = await wm.resolve_reference(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        reference=request.reference,
        entity_type=request.entity_type,
    )

    resolved_label = None
    confidence = 0.0

    if resolved_id:
        graph = await wm.get_session_graph(
            tenant_id=user.tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if graph and resolved_id in graph.nodes:
            resolved_label = graph.nodes[resolved_id].get("label", resolved_id)
            confidence = 0.9

    return ResolveResponse(
        reference=request.reference,
        resolved_entity_id=resolved_id,
        resolved_label=resolved_label,
        confidence=confidence,
    )


# =============================================================================
# Feedback & Delete Endpoints (Memory Sync)
# =============================================================================


class FeedbackRequest(BaseModel):
    """Richiesta aggiornamento feedback."""

    score: int = Field(..., ge=-1, le=1, description="1=upvote, -1=downvote, 0=remove")
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    """Singolo feedback."""

    message_id: str
    score: int
    comment: str = ""


@router.delete("/sessions/{session_id}/messages/{message_id}")
async def delete_message(
    session_id: str,
    message_id: str,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Elimina un messaggio dalla working memory."""
    deleted = await wm.delete_message(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        message_id=message_id,
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found")

    logger.info(
        "working_message_deleted",
        session_id=session_id,
        message_id=message_id,
    )

    return {"deleted": True, "session_id": session_id, "message_id": message_id}


@router.put("/sessions/{session_id}/messages/{message_id}/feedback")
async def update_feedback(
    session_id: str,
    message_id: str,
    request: FeedbackRequest,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Aggiorna il feedback (upvote/downvote) per un messaggio."""
    success = await wm.update_feedback(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
        message_id=message_id,
        score=request.score,
        comment=request.comment,
    )

    logger.info(
        "working_feedback_updated",
        session_id=session_id,
        message_id=message_id,
        score=request.score,
    )

    return {
        "updated": success,
        "session_id": session_id,
        "message_id": message_id,
        "score": request.score,
    }


@router.get("/sessions/{session_id}/feedback")
async def get_session_feedback(
    session_id: str,
    user_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    wm: WorkingMemory = Depends(get_working_memory),
) -> dict[str, Any]:
    """Recupera tutti i feedback per una sessione."""
    feedback = await wm.get_feedback(
        tenant_id=user.tenant_id,
        user_id=user_id,
        session_id=session_id,
    )

    return {
        "session_id": session_id,
        "feedback": [
            FeedbackResponse(
                message_id=msg_id,
                score=fb.get("score", 0),
                comment=fb.get("comment", ""),
            ).model_dump()
            for msg_id, fb in feedback.items()
        ],
        "count": len(feedback),
    }
