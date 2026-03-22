"""Unit tests for Browser module (M7)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.core.browser.types import (
    ActionType,
    BrowserAction,
    BrowserConfig,
    BrowserSession,
    BrowserSkill,
    BrowserStatus,
    BrowserType,
    CreateSessionRequest,
    ExtractRequest,
    NavigateRequest,
    RecordingState,
    SessionResponse,
)
from me4brain.core.browser.recorder import SkillRecorder
from me4brain.core.browser.extractor import SkillExtractor


# --- Types Tests ---


class TestBrowserTypes:
    """Test per modelli Pydantic browser."""

    def test_browser_type_enum(self):
        """Test enum valori."""
        assert BrowserType.CHROMIUM.value == "chromium"
        assert BrowserType.FIREFOX.value == "firefox"

    def test_browser_status_enum(self):
        """Test stati browser."""
        assert BrowserStatus.READY.value == "ready"
        assert BrowserStatus.RECORDING.value == "recording"

    def test_action_type_enum(self):
        """Test tipi azione."""
        assert ActionType.NAVIGATE.value == "navigate"
        assert ActionType.CLICK.value == "click"
        assert ActionType.EXTRACT.value == "extract"

    def test_browser_config_defaults(self):
        """Test valori default config."""
        config = BrowserConfig()
        assert config.browser_type == BrowserType.CHROMIUM
        assert config.headless is True
        assert config.viewport_width == 1280
        assert config.timeout_ms == 30000

    def test_browser_session_creation(self):
        """Test creazione sessione."""
        session = BrowserSession(
            id="sess-123",
            status=BrowserStatus.READY,
        )
        assert session.id == "sess-123"
        assert session.action_count == 0
        assert session.is_recording is False

    def test_browser_action_creation(self):
        """Test creazione azione."""
        action = BrowserAction(
            id="act-123",
            type=ActionType.CLICK,
            target="button.submit",
            success=True,
            duration_ms=150,
        )
        assert action.id == "act-123"
        assert action.type == ActionType.CLICK
        assert action.duration_ms == 150

    def test_browser_action_with_instruction(self):
        """Test azione con istruzione NL."""
        action = BrowserAction(
            id="act-456",
            type=ActionType.CUSTOM,
            instruction="Click the login button",
        )
        assert action.instruction == "Click the login button"

    def test_recording_state_creation(self):
        """Test stato recording."""
        state = RecordingState(
            id="rec-123",
            session_id="sess-123",
        )
        assert state.status == "active"
        assert len(state.actions) == 0

    def test_browser_skill_creation(self):
        """Test creazione skill."""
        skill = BrowserSkill(
            id="skill-123",
            name="login_flow",
            description="Login to website",
            actions=[],
        )
        assert skill.name == "login_flow"
        assert skill.execution_count == 0
        assert skill.success_rate == 1.0

    def test_browser_skill_success_rate(self):
        """Test calcolo success rate."""
        skill = BrowserSkill(
            id="skill-123",
            name="test",
            description="test",
            execution_count=10,
            success_count=8,
        )
        assert skill.success_rate == 0.8

    def test_session_response_from_session(self):
        """Test conversione SessionResponse."""
        session = BrowserSession(
            id="sess-123",
            status=BrowserStatus.READY,
            current_url="https://example.com",
            action_count=5,
        )
        response = SessionResponse.from_session(session)
        assert response.id == "sess-123"
        assert response.status == "ready"
        assert response.action_count == 5

    def test_create_session_request(self):
        """Test request creazione sessione."""
        req = CreateSessionRequest(
            start_url="https://example.com",
        )
        assert req.start_url == "https://example.com"
        assert req.config is None

    def test_navigate_request(self):
        """Test request navigazione."""
        req = NavigateRequest(url="https://example.com")
        assert req.url == "https://example.com"
        assert req.wait_until == "load"


# --- Recorder Tests ---


class TestSkillRecorder:
    """Test per SkillRecorder."""

    def test_recorder_init(self):
        """Test inizializzazione recorder."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        assert recorder.is_recording is False
        assert recorder.state is None

    def test_start_recording(self):
        """Test avvio recording."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)

        state = recorder.start(name="test_skill")

        assert recorder.is_recording is True
        assert state.status == "active"
        assert state.name == "test_skill"
        assert session.is_recording is True

    def test_start_recording_already_active(self):
        """Test errore se già in recording."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()

        with pytest.raises(RuntimeError, match="already active"):
            recorder.start()

    def test_record_action(self):
        """Test registrazione azione."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()

        action = recorder.record_action(
            ActionType.NAVIGATE,
            target="https://example.com",
            duration_ms=500,
        )

        assert len(recorder.state.actions) == 1
        assert action.type == ActionType.NAVIGATE
        assert recorder.state.total_duration_ms == 500

    def test_record_action_not_active(self):
        """Test errore se recording non attivo."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)

        with pytest.raises(RuntimeError, match="not active"):
            recorder.record_action(ActionType.CLICK)

    def test_pause_resume(self):
        """Test pause e resume."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()

        recorder.pause()
        assert recorder.state.status == "paused"

        recorder.resume()
        assert recorder.state.status == "active"

    def test_stop_recording(self):
        """Test stop recording."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()
        recorder.record_action(ActionType.CLICK, target="button")

        state = recorder.stop()

        assert recorder.is_recording is False
        assert state.status == "stopped"
        assert state.stopped_at is not None
        assert session.is_recording is False

    def test_stop_not_active(self):
        """Test errore stop se non attivo."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)

        with pytest.raises(RuntimeError, match="not active"):
            recorder.stop()

    def test_to_skill(self):
        """Test conversione a skill."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()
        recorder.record_action(ActionType.NAVIGATE, target="https://example.com")
        recorder.record_action(ActionType.CLICK, target="button")
        recorder.stop()

        skill = recorder.to_skill(name="my_skill", description="Test skill")

        assert skill.name == "my_skill"
        assert len(skill.actions) == 2
        assert skill.recording_id == recorder.state.id

    def test_to_skill_still_active(self):
        """Test errore to_skill se ancora attivo."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()

        with pytest.raises(RuntimeError, match="still active"):
            recorder.to_skill()

    def test_extract_parameters(self):
        """Test estrazione parametri."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()
        recorder.record_action(ActionType.NAVIGATE, target="https://example.com")
        recorder.record_action(ActionType.TYPE, value="test@email.com")
        recorder.stop()

        skill = recorder.to_skill()

        assert len(skill.parameters) >= 1

    def test_clear(self):
        """Test reset recorder."""
        session = BrowserSession(id="sess-123")
        recorder = SkillRecorder(session)
        recorder.start()
        recorder.stop()
        recorder.clear()

        assert recorder.state is None
        assert recorder.is_recording is False


# --- Extractor Tests ---


class TestSkillExtractor:
    """Test per SkillExtractor."""

    def test_extractor_init(self):
        """Test inizializzazione."""
        extractor = SkillExtractor()
        assert extractor._cache == {}

    def test_analyze_recording(self):
        """Test analisi recording."""
        state = RecordingState(
            id="rec-123",
            session_id="sess-123",
            actions=[
                BrowserAction(
                    id="1", type=ActionType.NAVIGATE, target="https://example.com"
                ),
                BrowserAction(id="2", type=ActionType.CLICK, target="button"),
                BrowserAction(id="3", type=ActionType.TYPE, value="test"),
            ],
        )

        extractor = SkillExtractor()
        analysis = extractor.analyze(state)

        assert analysis["total_actions"] == 3
        assert analysis["action_types"]["navigate"] == 1
        assert analysis["action_types"]["click"] == 1

    def test_find_redundant_actions(self):
        """Test identificazione azioni ridondanti."""
        extractor = SkillExtractor()
        actions = [
            BrowserAction(id="1", type=ActionType.NAVIGATE, target="https://a.com"),
            BrowserAction(
                id="2", type=ActionType.NAVIGATE, target="https://a.com"
            ),  # Ridondante
            BrowserAction(id="3", type=ActionType.SCREENSHOT),
            BrowserAction(id="4", type=ActionType.SCREENSHOT),  # Ridondante
        ]

        redundant = extractor._find_redundant(actions)
        assert 1 in redundant
        assert 3 in redundant

    def test_remove_redundant(self):
        """Test rimozione ridondanti."""
        extractor = SkillExtractor()
        actions = [
            BrowserAction(id="1", type=ActionType.NAVIGATE, target="https://a.com"),
            BrowserAction(id="2", type=ActionType.NAVIGATE, target="https://a.com"),
            BrowserAction(id="3", type=ActionType.CLICK, target="button"),
        ]

        cleaned = extractor._remove_redundant(actions)
        assert len(cleaned) == 2

    def test_generalize_selectors(self):
        """Test generalizzazione selectors."""
        extractor = SkillExtractor()
        actions = [
            BrowserAction(
                id="1",
                type=ActionType.CLICK,
                target="button#btn-12345678",
            ),
        ]

        generalized = extractor._generalize_selectors(actions)
        assert "{dynamic_id}" in generalized[0].target

    def test_extract_skill(self):
        """Test estrazione skill completa."""
        state = RecordingState(
            id="rec-123",
            session_id="sess-123",
            status="stopped",
            actions=[
                BrowserAction(
                    id="1", type=ActionType.NAVIGATE, target="https://example.com"
                ),
                BrowserAction(id="2", type=ActionType.CLICK, target="button.login"),
            ],
        )

        extractor = SkillExtractor()
        skill = extractor.extract_skill(state, name="test_skill")

        assert skill.name == "test_skill"
        assert len(skill.actions) == 2

    def test_extract_skill_with_optimization(self):
        """Test estrazione con ottimizzazione."""
        state = RecordingState(
            id="rec-123",
            session_id="sess-123",
            status="stopped",
            actions=[
                BrowserAction(id="1", type=ActionType.NAVIGATE, target="https://a.com"),
                BrowserAction(
                    id="2", type=ActionType.NAVIGATE, target="https://a.com"
                ),  # Ridondante
                BrowserAction(id="3", type=ActionType.CLICK, target="button"),
            ],
        )

        extractor = SkillExtractor()
        skill = extractor.extract_skill(state, optimize=True)

        assert len(skill.actions) == 2  # Una nav rimossa

    def test_generate_name(self):
        """Test generazione nome automatico."""
        state = RecordingState(
            id="rec-123",
            session_id="sess-123",
            actions=[
                BrowserAction(
                    id="1", type=ActionType.NAVIGATE, target="https://github.com/test"
                ),
            ],
        )

        extractor = SkillExtractor()
        name = extractor._generate_name(state, state.actions)

        assert "github" in name or "skill_" in name

    def test_generate_description(self):
        """Test generazione descrizione."""
        extractor = SkillExtractor()
        actions = [
            BrowserAction(id="1", type=ActionType.NAVIGATE),
            BrowserAction(id="2", type=ActionType.CLICK),
            BrowserAction(id="3", type=ActionType.TYPE),
        ]

        desc = extractor._generate_description(actions)
        assert "3 steps" in desc

    def test_find_source_url(self):
        """Test ricerca URL sorgente."""
        extractor = SkillExtractor()
        actions = [
            BrowserAction(
                id="1", type=ActionType.NAVIGATE, target="https://example.com"
            ),
            BrowserAction(id="2", type=ActionType.CLICK),
        ]

        url = extractor._find_source_url(actions)
        assert url == "https://example.com"

    def test_generate_suggestions(self):
        """Test generazione suggerimenti."""
        extractor = SkillExtractor()
        state = RecordingState(id="rec-123", session_id="sess-123")

        analysis = {
            "action_types": {"screenshot": 5, "wait": 4},
            "redundant_actions": [1, 2],
            "potential_parameters": [1, 2, 3, 4, 5, 6],
        }

        suggestions = extractor._generate_suggestions(state, analysis)

        assert len(suggestions) >= 2
