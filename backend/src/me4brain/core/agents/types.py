"""Agent Types - Modelli Pydantic per sistema Agent-to-Agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AgentType(str, Enum):
    """Tipi di agente."""

    SUPERVISOR = "supervisor"  # Coordina altri agenti
    SPECIALIST = "specialist"  # Agente specializzato (research, coding, etc.)
    WORKER = "worker"  # Worker generico


class AgentStatus(str, Enum):
    """Stati agente."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class AgentProfile(BaseModel):
    """Profilo agente registrato."""

    id: str
    name: str
    type: AgentType = AgentType.WORKER
    capabilities: list[str] = Field(default_factory=list)  # ["research", "coding"]

    # State
    status: AgentStatus = AgentStatus.IDLE
    session_id: Optional[str] = None
    current_task: Optional[str] = None

    # Metadata
    tenant_id: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    # Stats
    created_at: datetime = Field(default_factory=datetime.now)
    last_active: Optional[datetime] = None
    tasks_completed: int = 0
    tasks_failed: int = 0

    @property
    def success_rate(self) -> float:
        total = self.tasks_completed + self.tasks_failed
        if total == 0:
            return 1.0
        return self.tasks_completed / total


class MessageFlag(str, Enum):
    """Flag per messaggi inter-agente."""

    REPLY_SKIP = "REPLY_SKIP"  # Non aspettare risposta
    ANNOUNCE_SKIP = "ANNOUNCE_SKIP"  # Non annunciare ricezione
    PRIORITY_HIGH = "PRIORITY_HIGH"  # Alta priorità
    BROADCAST = "BROADCAST"  # Invia a tutti gli agenti


class AgentMessage(BaseModel):
    """Messaggio tra agenti."""

    id: str
    from_agent: str
    to_agent: str  # ID agente o "*" per broadcast
    content: str

    # Context
    context: dict = Field(default_factory=dict)
    reply_to: Optional[str] = None  # ID messaggio a cui risponde

    # Flags
    flags: list[MessageFlag] = Field(default_factory=list)

    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    acknowledged: bool = False
    processed: bool = False


class HandoffRequest(BaseModel):
    """Richiesta di handoff task tra agenti."""

    id: str
    from_agent: str
    to_agent: str
    task: str
    context: dict = Field(default_factory=dict)
    priority: int = 0  # 0 = normale, 1+ = alta priorità

    # State
    status: Literal["pending", "accepted", "rejected", "completed"] = "pending"
    result: Optional[dict] = None

    # Timing
    created_at: datetime = Field(default_factory=datetime.now)
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class TaskContext(BaseModel):
    """Context condiviso per task multi-agente."""

    task_id: str
    data: dict = Field(default_factory=dict)
    agents_involved: list[str] = Field(default_factory=list)

    # State
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    ttl_seconds: int = 3600  # 1 ora default


# --- API Models ---


class RegisterAgentRequest(BaseModel):
    """Request per registrazione agente."""

    name: str
    type: AgentType = AgentType.WORKER
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class SendMessageRequest(BaseModel):
    """Request per invio messaggio."""

    content: str
    context: dict = Field(default_factory=dict)
    reply_to: Optional[str] = None
    flags: list[str] = Field(default_factory=list)


class HandoffTaskRequest(BaseModel):
    """Request per handoff task."""

    task: str
    to_agent: Optional[str] = None  # Se None, il supervisor sceglie
    context: dict = Field(default_factory=dict)
    priority: int = 0


class AgentResponse(BaseModel):
    """Response per agente via API."""

    id: str
    name: str
    type: str
    capabilities: list[str]
    status: str
    success_rate: float

    @classmethod
    def from_profile(cls, profile: AgentProfile) -> "AgentResponse":
        return cls(
            id=profile.id,
            name=profile.name,
            type=profile.type.value,
            capabilities=profile.capabilities,
            status=profile.status.value,
            success_rate=profile.success_rate,
        )


class MessageResponse(BaseModel):
    """Response per messaggio via API."""

    id: str
    from_agent: str
    to_agent: str
    content: str
    timestamp: datetime
    acknowledged: bool
