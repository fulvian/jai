"""LLM Models - Pydantic models per richieste/risposte LLM.

Definisce i modelli dati per l'interazione con NanoGPT API.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ReasoningLevel(str, Enum):
    """Livelli di reasoning effort per NanoGPT."""

    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MessageRole(str, Enum):
    """Ruoli dei messaggi nella conversazione."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ToolFunction(BaseModel):
    """Definizione di una funzione tool."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class Tool(BaseModel):
    """Tool definition per function calling."""

    type: str = "function"
    function: ToolFunction


class ToolCallFunction(BaseModel):
    """Chiamata a funzione tool."""

    name: str
    arguments: str  # JSON string


class ToolCall(BaseModel):
    """Tool call generata dal modello."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    type: str = "function"
    function: ToolCallFunction


class MessageContent(BaseModel):
    """Contenuto multimodale di un messaggio."""

    type: str  # "text", "image_url"
    text: str | None = None
    image_url: dict[str, str] | None = None  # {"url": "..."}


class Message(BaseModel):
    """Messaggio nella conversazione."""

    role: str | MessageRole = "user"  # Accept both string literals and enum for flexibility
    content: str | list[MessageContent] | None = None

    # Per messaggi assistant con tool calls
    tool_calls: list[ToolCall] | None = None

    # Per messaggi tool (risposta a tool call)
    tool_call_id: str | None = None
    name: str | None = None  # Nome del tool chiamato


class LLMRequest(BaseModel):
    """Richiesta al provider LLM."""

    messages: list[Message]
    model: str

    # Parametri generazione
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=8192, ge=1)
    top_p: float | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    stop: list[str] | None = None

    # Reasoning (NanoGPT specific)
    reasoning_effort: ReasoningLevel = ReasoningLevel.MEDIUM
    reasoning_exclude: bool = False  # Escludi reasoning dalla risposta

    # Tool calling
    tools: list[Tool] | None = None
    tool_choice: str | dict[str, Any] | None = "auto"
    parallel_tool_calls: bool = True

    # Streaming
    stream: bool = False

    # Structured output
    response_format: dict[str, Any] | None = None

    # Metadata
    request_id: str = Field(default_factory=lambda: str(uuid4()))


class Usage(BaseModel):
    """Token usage della risposta."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0  # Token usati per reasoning


class ChoiceMessage(BaseModel):
    """Messaggio nella choice della risposta."""

    role: str = "assistant"
    content: str | None = None
    reasoning: str | None = None  # Reasoning content
    tool_calls: list[ToolCall] | None = None


class Choice(BaseModel):
    """Singola choice nella risposta."""

    index: int = 0
    message: ChoiceMessage
    finish_reason: str | None = None  # "stop", "tool_calls", "length"


class LLMResponse(BaseModel):
    """Risposta completa dal provider LLM."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model: str
    choices: list[Choice]
    usage: Usage = Field(default_factory=Usage)

    # Metadata
    request_id: str | None = None
    latency_ms: float = 0.0

    @property
    def content(self) -> str | None:
        """Shortcut per il contenuto della prima choice."""
        if self.choices:
            return self.choices[0].message.content
        return None

    @property
    def reasoning(self) -> str | None:
        """Shortcut per il reasoning della prima choice."""
        if self.choices:
            return self.choices[0].message.reasoning
        return None

    @property
    def tool_calls(self) -> list[ToolCall] | None:
        """Shortcut per le tool calls della prima choice."""
        if self.choices:
            return self.choices[0].message.tool_calls
        return None

    @property
    def finish_reason(self) -> str | None:
        """Shortcut per il finish reason della prima choice."""
        if self.choices:
            return self.choices[0].finish_reason
        return None


class DeltaContent(BaseModel):
    """Delta content per streaming."""

    content: str | None = None
    reasoning: str | None = None
    tool_calls: list[ToolCall] | None = None


class ChoiceDelta(BaseModel):
    """Choice delta per streaming."""

    index: int = 0
    delta: DeltaContent
    finish_reason: str | None = None


class LLMChunk(BaseModel):
    """Chunk di risposta streaming."""

    id: str
    created: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model: str
    choices: list[ChoiceDelta]

    @property
    def content(self) -> str | None:
        """Shortcut per il contenuto delta."""
        if self.choices:
            return self.choices[0].delta.content
        return None

    @property
    def reasoning(self) -> str | None:
        """Shortcut per il reasoning delta."""
        if self.choices:
            return self.choices[0].delta.reasoning
        return None

    @property
    def is_done(self) -> bool:
        """Check se lo stream è terminato."""
        if self.choices:
            return self.choices[0].finish_reason is not None
        return False
