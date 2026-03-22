"""Browser Types - Modelli Pydantic per browser automation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

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
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None

    # Stealth
    stealth_mode: bool = True
    user_agent: Optional[str] = None

    # Resource limits
    max_memory_mb: int = 512
    max_pages: int = 5


class StagehandConfig(BaseModel):
    """Configurazione Stagehand AI."""

    model_name: str = "gpt-4o"  # LLM per decisioni
    api_key: Optional[str] = None  # Default da env
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
    current_url: Optional[str] = None
    current_title: Optional[str] = None
    page_count: int = 0

    # Recording
    is_recording: bool = False
    recording_id: Optional[str] = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    last_action_at: Optional[datetime] = None
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
    target: Optional[str] = None  # Selector, URL, or instruction
    value: Optional[str] = None  # Input value

    # Result
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0

    # Stagehand
    instruction: Optional[str] = None  # Natural language
    extracted_data: Optional[dict] = None


class BrowserActionResult(BaseModel):
    """Risultato esecuzione azione."""

    action_id: str
    success: bool
    duration_ms: int

    # Response data
    data: Optional[dict] = None
    screenshot_path: Optional[str] = None
    error: Optional[str] = None

    # Page state after action
    url: Optional[str] = None
    title: Optional[str] = None


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
    stopped_at: Optional[datetime] = None
    total_duration_ms: int = 0

    # Metadata
    name: Optional[str] = None
    description: Optional[str] = None


class BrowserSkill(BaseModel):
    """Skill estratta da recording."""

    id: str
    name: str
    description: str

    # Steps
    actions: list[BrowserAction] = Field(default_factory=list)
    parameters: list[dict] = Field(default_factory=list)  # Variabili estraibili

    # Source
    recording_id: Optional[str] = None
    source_url: Optional[str] = None

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

    config: Optional[BrowserConfig] = None
    start_url: Optional[str] = None
    name: Optional[str] = None


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
    output_schema: Optional[dict] = None  # JSON Schema per output strutturato


class SessionResponse(BaseModel):
    """Response per sessione browser."""

    id: str
    status: str
    url: Optional[str]
    title: Optional[str]
    action_count: int
    is_recording: bool

    @classmethod
    def from_session(cls, session: BrowserSession) -> "SessionResponse":
        return cls(
            id=session.id,
            status=session.status.value,
            url=session.current_url,
            title=session.current_title,
            action_count=session.action_count,
            is_recording=session.is_recording,
        )
