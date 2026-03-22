"""Skill System Types - Modelli Pydantic per il sistema skill ibrido."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Rappresenta una singola chiamata tool."""

    name: str
    args: dict[str, Any]
    result: Optional[Any] = None
    success: bool = True
    duration_ms: float = 0.0


class ExecutionTrace(BaseModel):
    """Traccia completa di un'esecuzione multi-tool."""

    session_id: str
    input_query: str
    tool_chain: list[ToolCall] = Field(default_factory=list)
    final_output: Optional[str] = None
    success: bool = False
    total_duration_ms: float = 0.0
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def signature(self) -> str:
        """Genera signature unica basata sulla sequenza di tool."""
        tool_names = [t.name for t in self.tool_chain]
        return ":".join(sorted(tool_names))


class Skill(BaseModel):
    """Modello unificato per skill esplicite e cristallizzate."""

    id: str
    name: str
    description: str
    type: Literal["explicit", "crystallized"]

    # Storage
    code: str  # Tool chain serializzata o istruzioni markdown
    embedding: list[float] = Field(default_factory=list)

    # Reinforcement Learning (pattern Voyager)
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    tenant_id: Optional[str] = None
    enabled: bool = True

    # Per skill esplicite
    file_path: Optional[str] = None
    version: str = "1.0"

    # Per skill cristallizzate
    source_trace_id: Optional[str] = None
    tool_signature: Optional[str] = None

    @property
    def success_rate(self) -> float:
        """Calcola il tasso di successo."""
        if self.usage_count == 0:
            return 0.5  # Prior neutro per skill nuove
        return self.success_count / self.usage_count

    @property
    def confidence(self) -> float:
        """Calcola confidence (aumenta con più usage)."""
        # Formula: 1 - 1/(1 + usage_count)
        # 0 usage -> 0.0, 1 usage -> 0.5, 10 usage -> 0.91
        return 1 - 1 / (1 + self.usage_count)

    def record_usage(self, success: bool) -> None:
        """Registra un utilizzo della skill."""
        self.usage_count += 1
        self.last_used = datetime.now()
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1


class SkillDefinition(BaseModel):
    """Definizione skill da file SKILL.md (frontmatter YAML)."""

    name: str
    description: str
    version: str = "1.0"
    author: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)  # Pattern di attivazione
    tools_required: list[str] = Field(default_factory=list)
    tenant_id: Optional[str] = None

    # Contenuto markdown (istruzioni)
    instructions: str = ""


class ScoredSkill(BaseModel):
    """Skill con score di retrieval."""

    skill: Skill
    similarity_score: float
    weighted_score: float  # similarity * success_rate * confidence

    @classmethod
    def from_skill(cls, skill: Skill, similarity: float) -> "ScoredSkill":
        """Crea ScoredSkill con calcolo automatico weighted score."""
        weighted = similarity * skill.success_rate * skill.confidence
        return cls(skill=skill, similarity_score=similarity, weighted_score=weighted)


class SkillStats(BaseModel):
    """Statistiche aggregate del sistema skill."""

    total_explicit: int = 0
    total_crystallized: int = 0
    total_usage: int = 0
    avg_success_rate: float = 0.0
    top_skills: list[str] = Field(default_factory=list)
    crystallization_rate: float = 0.0  # % trace che diventano skill


class VerificationResult(BaseModel):
    """Risultato verifica skill post-esecuzione."""

    success: bool
    error_message: Optional[str] = None
    suggestions: list[str] = Field(default_factory=list)
    retry_count: int = 0
