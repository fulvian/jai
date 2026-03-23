"""Browser Types - Modelli Pydantic per browser automation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class BrowserType(str, Enum):
    """Tipi di browser supportati."""

    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class BrowserStatus(str, Enum):
    """Stati sessione browser."""

    CREATING = "creating"
    READY = "ready"
    BUSY = "busy"
    RECORDING = "recording"
    CLOSED = "closed"
    ERROR = "error"


class ActionType(str, Enum):
    """Tipi di azioni browser."""

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    SCREENSHOT = "screenshot"
    EXTRACT = "extract"
    WAIT = "wait"
    CUSTOM = "custom"


# --- Configuration ---


class BrowserConfig(BaseModel):
    """Configurazione sessione browser."""

    browser_type: BrowserType = BrowserType.CHROMIUM
    headless: bool = True
    viewport_width: int = 1280
    viewport_height: int = 720
    timeout_ms: int = 30000
    slow_mo_ms: int = 0  # Rallenta per debug

    # Proxy
    proxy_server: str | None = None
    proxy_username: str | None = None
    proxy_password: str | None = None

    # Stealth
    stealth_mode: bool = True
    user_agent: str | None = None

    # Resource limits
    max_memory_mb: int = 512
    max_pages: int = 5


class StagehandConfig(BaseModel):
    """Configurazione Stagehand AI."""

    model_name: str = "gpt-4o"  # LLM per decisioni
    api_key: str | None = None  # Default da env
    enable_caching: bool = True
    verbose: bool = False
    dom_settle_timeout_ms: int = 3000


# --- Session ---


class BrowserSession(BaseModel):
    """Stato sessione browser."""

    id: str
    status: BrowserStatus = BrowserStatus.CREATING
    config: BrowserConfig = Field(default_factory=BrowserConfig)

    # Current state
    current_url: str | None = None
    current_title: str | None = None
    page_count: int = 0

    # Recording
    is_recording: bool = False
    recording_id: str | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    last_action_at: datetime | None = None
    action_count: int = 0
    error_count: int = 0

    # Stats
    total_time_ms: int = 0


# --- Actions ---


class BrowserAction(BaseModel):
    """Singola azione browser."""

    id: str
    type: ActionType
    timestamp: datetime = Field(default_factory=datetime.now)

    # Target
    target: str | None = None  # Selector, URL, or instruction
    value: str | None = None  # Input value

    # Result
    success: bool = True
    error: str | None = None
    duration_ms: int = 0

    # Stagehand
    instruction: str | None = None  # Natural language
    extracted_data: dict | None = None


class BrowserActionResult(BaseModel):
    """Risultato esecuzione azione."""

    action_id: str
    success: bool
    duration_ms: int

    # Response data
    data: dict | None = None
    screenshot_path: str | None = None
    error: str | None = None

    # Page state after action
    url: str | None = None
    title: str | None = None


# --- Recording & Skills ---


class RecordingState(BaseModel):
    """Stato sessione di recording."""

    id: str
    session_id: str
    status: Literal["active", "paused", "stopped"] = "active"

    # Actions
    actions: list[BrowserAction] = Field(default_factory=list)

    # Timing
    started_at: datetime = Field(default_factory=datetime.now)
    stopped_at: datetime | None = None
    total_duration_ms: int = 0

    # Metadata
    name: str | None = None
    description: str | None = None


class BrowserSkill(BaseModel):
    """Skill estratta da recording."""

    id: str
    name: str
    description: str

    # Steps
    actions: list[BrowserAction] = Field(default_factory=list)
    parameters: list[dict] = Field(default_factory=list)  # Variabili estraibili

    # Source
    recording_id: str | None = None
    source_url: str | None = None

    # Stats
    created_at: datetime = Field(default_factory=datetime.now)
    execution_count: int = 0
    success_count: int = 0
    avg_duration_ms: int = 0

    @property
    def success_rate(self) -> float:
        if self.execution_count == 0:
            return 1.0
        return self.success_count / self.execution_count


# --- API Models ---


class CreateSessionRequest(BaseModel):
    """Request per creare sessione browser."""

    config: BrowserConfig | None = None
    start_url: str | None = None
    name: str | None = None


class NavigateRequest(BaseModel):
    """Request per navigazione."""

    url: str
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "load"


class ActRequest(BaseModel):
    """Request per azione natural language."""

    instruction: str
    timeout_ms: int = 30000


class ExtractRequest(BaseModel):
    """Request per estrazione dati."""

    instruction: str
    output_schema: dict | None = None  # JSON Schema per output strutturato


class SessionResponse(BaseModel):
    """Response per sessione browser."""

    id: str
    status: str
    url: str | None
    title: str | None
    action_count: int
    is_recording: bool

    @classmethod
    def from_session(cls, session: BrowserSession) -> SessionResponse:
        return cls(
            id=session.id,
            status=session.status.value,
            url=session.current_url,
            title=session.current_title,
            action_count=session.action_count,
            is_recording=session.is_recording,
        )
