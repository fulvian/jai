"""Skill Recorder - Recording azioni browser per generare skill."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import structlog

from me4brain.core.browser.types import (
    ActionType,
    BrowserAction,
    BrowserSession,
    BrowserSkill,
    BrowserStatus,
    RecordingState,
)

logger = structlog.get_logger(__name__)


class SkillRecorder:
    """
    Recorder per catturare sequenze di azioni browser.

    Flow:
    1. start() - Inizia recording
    2. record_action() - Registra ogni azione
    3. stop() - Ferma e restituisce RecordingState
    4. to_skill() - Converte in BrowserSkill
    """

    def __init__(self, session: BrowserSession):
        """
        Inizializza recorder.

        Args:
            session: Sessione browser associata
        """
        self.session = session
        self._state: Optional[RecordingState] = None
        self._is_active = False

    @property
    def is_recording(self) -> bool:
        """Check se recording attivo."""
        return self._is_active

    @property
    def state(self) -> Optional[RecordingState]:
        """Ottiene stato recording."""
        return self._state

    def start(self, name: Optional[str] = None) -> RecordingState:
        """
        Avvia recording.

        Args:
            name: Nome opzionale per skill

        Returns:
            Stato recording inizializzato

        Raises:
            RuntimeError: Se già in recording
        """
        if self._is_active:
            raise RuntimeError("Recording already active")

        recording_id = str(uuid.uuid4())[:12]

        self._state = RecordingState(
            id=recording_id,
            session_id=self.session.id,
            status="active",
            name=name,
        )

        self._is_active = True
        self.session.is_recording = True
        self.session.recording_id = recording_id
        self.session.status = BrowserStatus.RECORDING

        logger.info(
            "recording_started",
            recording_id=recording_id,
            session_id=self.session.id,
        )

        return self._state

    def record_action(
        self,
        action_type: ActionType,
        target: Optional[str] = None,
        value: Optional[str] = None,
        instruction: Optional[str] = None,
        success: bool = True,
        duration_ms: int = 0,
        extracted_data: Optional[dict] = None,
    ) -> BrowserAction:
        """
        Registra singola azione.

        Args:
            action_type: Tipo azione
            target: Selector o URL
            value: Valore input
            instruction: Istruzione NL (Stagehand)
            success: Esito azione
            duration_ms: Durata
            extracted_data: Dati estratti

        Returns:
            Azione registrata

        Raises:
            RuntimeError: Se recording non attivo
        """
        if not self._is_active or not self._state:
            raise RuntimeError("Recording not active")

        action = BrowserAction(
            id=str(uuid.uuid4())[:8],
            type=action_type,
            target=target,
            value=value,
            instruction=instruction,
            success=success,
            duration_ms=duration_ms,
            extracted_data=extracted_data,
        )

        self._state.actions.append(action)
        self._state.total_duration_ms += duration_ms

        logger.debug(
            "action_recorded",
            recording_id=self._state.id,
            action_type=action_type.value,
            action_count=len(self._state.actions),
        )

        return action

    def pause(self) -> None:
        """Pausa recording."""
        if self._state:
            self._state.status = "paused"
            logger.debug("recording_paused", recording_id=self._state.id)

    def resume(self) -> None:
        """Riprende recording."""
        if self._state:
            self._state.status = "active"
            logger.debug("recording_resumed", recording_id=self._state.id)

    def stop(self) -> RecordingState:
        """
        Ferma recording.

        Returns:
            Stato finale con tutte le azioni

        Raises:
            RuntimeError: Se recording non attivo
        """
        if not self._is_active or not self._state:
            raise RuntimeError("Recording not active")

        self._state.status = "stopped"
        self._state.stopped_at = datetime.now()

        # Calcola durata totale
        duration = (self._state.stopped_at - self._state.started_at).total_seconds()
        self._state.total_duration_ms = int(duration * 1000)

        self._is_active = False
        self.session.is_recording = False
        self.session.status = BrowserStatus.READY

        logger.info(
            "recording_stopped",
            recording_id=self._state.id,
            action_count=len(self._state.actions),
            duration_ms=self._state.total_duration_ms,
        )

        return self._state

    def to_skill(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> BrowserSkill:
        """
        Converte recording in skill.

        Args:
            name: Nome skill (override)
            description: Descrizione skill

        Returns:
            BrowserSkill generata

        Raises:
            RuntimeError: Se recording non completato
        """
        if not self._state:
            raise RuntimeError("No recording available")

        if self._state.status == "active":
            raise RuntimeError("Recording still active - call stop() first")

        # Genera nome se non fornito
        skill_name = name or self._state.name or f"skill_{self._state.id}"

        # Genera descrizione da azioni
        if not description:
            action_types = [a.type.value for a in self._state.actions[:5]]
            description = f"Skill with {len(self._state.actions)} actions: {', '.join(action_types)}"

        # Estrai possibili parametri (URL, valori input)
        parameters = self._extract_parameters()

        skill = BrowserSkill(
            id=str(uuid.uuid4())[:12],
            name=skill_name,
            description=description,
            actions=self._state.actions.copy(),
            parameters=parameters,
            recording_id=self._state.id,
            source_url=self._state.actions[0].target if self._state.actions else None,
        )

        logger.info(
            "skill_created_from_recording",
            skill_id=skill.id,
            name=skill.name,
            action_count=len(skill.actions),
        )

        return skill

    def _extract_parameters(self) -> list[dict]:
        """Estrae parametri variabili dalle azioni."""
        parameters = []

        for action in self._state.actions if self._state else []:
            # URL come parametro
            if action.type == ActionType.NAVIGATE and action.target:
                parameters.append(
                    {
                        "name": "url",
                        "type": "string",
                        "source": "navigate_target",
                        "example": action.target,
                    }
                )

            # Valori input come parametri
            if action.type == ActionType.TYPE and action.value:
                param_name = f"input_{len(parameters)}"
                parameters.append(
                    {
                        "name": param_name,
                        "type": "string",
                        "source": "type_value",
                        "example": action.value,
                    }
                )

        return parameters

    def clear(self) -> None:
        """Reset recorder."""
        self._state = None
        self._is_active = False
        self.session.is_recording = False
        self.session.recording_id = None
