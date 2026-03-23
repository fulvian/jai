"""Browser API Routes - Endpoint REST per browser automation."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from me4brain.core.browser.extractor import SkillExtractor
from me4brain.core.browser.manager import get_browser_manager
from me4brain.core.browser.recorder import SkillRecorder
from me4brain.core.browser.types import (
    ActRequest,
    CreateSessionRequest,
    ExtractRequest,
    NavigateRequest,
    SessionResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/browser", tags=["browser"])

# In-memory recorders per sessione
_recorders: dict[str, SkillRecorder] = {}


def _get_manager():
    manager = get_browser_manager()
    if manager is None:
        raise HTTPException(503, "Browser manager not initialized")
    return manager


# --- Sessions ---


@router.post("/sessions", response_model=SessionResponse)
async def create_session(request: CreateSessionRequest) -> SessionResponse:
    """
    Crea nuova sessione browser.

    Args:
        request: Configurazione sessione

    Returns:
        Sessione creata
    """
    manager = _get_manager()

    try:
        session = await manager.create_session(
            config=request.config,
            start_url=request.start_url,
        )
        return SessionResponse.from_session(session)

    except RuntimeError as e:
        raise HTTPException(429, str(e))


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions() -> list[SessionResponse]:
    """Lista sessioni attive."""
    manager = _get_manager()
    sessions = await manager.list_sessions()
    return [SessionResponse.from_session(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """Dettaglio sessione."""
    manager = _get_manager()
    session = await manager.get_session(session_id)

    if session is None:
        raise HTTPException(404, "Session not found")

    return SessionResponse.from_session(session)


@router.delete("/sessions/{session_id}")
async def close_session(session_id: str) -> dict[str, str]:
    """Chiude sessione browser."""
    manager = _get_manager()
    await manager.close_session(session_id)
    return {"message": f"Session {session_id} closed"}


# --- Actions ---


@router.post("/sessions/{session_id}/navigate")
async def navigate(session_id: str, request: NavigateRequest) -> dict:
    """
    Naviga a URL.

    Args:
        session_id: ID sessione
        request: URL e opzioni

    Returns:
        Risultato navigazione
    """
    manager = _get_manager()
    wrapper = await manager.get_wrapper(session_id)

    if wrapper is None:
        raise HTTPException(404, "Session not found")

    result = await wrapper.navigate(request.url, wait_until=request.wait_until)

    # Registra se recording attivo
    recorder = _recorders.get(session_id)
    if recorder and recorder.is_recording:
        from me4brain.core.browser.types import ActionType

        recorder.record_action(
            ActionType.NAVIGATE,
            target=request.url,
            success=result.success,
            duration_ms=result.duration_ms,
        )

    return result.model_dump()


@router.post("/sessions/{session_id}/act")
async def act(session_id: str, request: ActRequest) -> dict:
    """
    Esegue azione con natural language.

    Args:
        session_id: ID sessione
        request: Istruzione

    Returns:
        Risultato azione
    """
    manager = _get_manager()
    wrapper = await manager.get_wrapper(session_id)

    if wrapper is None:
        raise HTTPException(404, "Session not found")

    result = await wrapper.act(request.instruction)

    # Registra se recording attivo
    recorder = _recorders.get(session_id)
    if recorder and recorder.is_recording:
        from me4brain.core.browser.types import ActionType

        recorder.record_action(
            ActionType.CUSTOM,
            instruction=request.instruction,
            success=result.success,
            duration_ms=result.duration_ms,
        )

    return result.model_dump()


@router.post("/sessions/{session_id}/extract")
async def extract(session_id: str, request: ExtractRequest) -> dict:
    """
    Estrae dati strutturati.

    Args:
        session_id: ID sessione
        request: Istruzione e schema

    Returns:
        Dati estratti
    """
    manager = _get_manager()
    wrapper = await manager.get_wrapper(session_id)

    if wrapper is None:
        raise HTTPException(404, "Session not found")

    result = await wrapper.extract(request.instruction, schema=request.schema)

    # Registra se recording attivo
    recorder = _recorders.get(session_id)
    if recorder and recorder.is_recording:
        from me4brain.core.browser.types import ActionType

        recorder.record_action(
            ActionType.EXTRACT,
            instruction=request.instruction,
            success=result.success,
            extracted_data=result.data,
        )

    return result.model_dump()


@router.get("/sessions/{session_id}/observe")
async def observe(session_id: str) -> dict:
    """Osserva stato pagina."""
    manager = _get_manager()
    wrapper = await manager.get_wrapper(session_id)

    if wrapper is None:
        raise HTTPException(404, "Session not found")

    result = await wrapper.observe()
    return result.model_dump()


@router.get("/sessions/{session_id}/screenshot")
async def screenshot(session_id: str, full_page: bool = False) -> dict:
    """Cattura screenshot."""
    manager = _get_manager()
    wrapper = await manager.get_wrapper(session_id)

    if wrapper is None:
        raise HTTPException(404, "Session not found")

    result = await wrapper.screenshot(full_page=full_page)

    # Registra se recording attivo
    recorder = _recorders.get(session_id)
    if recorder and recorder.is_recording:
        from me4brain.core.browser.types import ActionType

        recorder.record_action(ActionType.SCREENSHOT, success=result.success)

    return result.model_dump()


# --- Recording ---


@router.post("/sessions/{session_id}/recording/start")
async def start_recording(session_id: str, name: str | None = None) -> dict:
    """Avvia recording azioni."""
    manager = _get_manager()
    wrapper = await manager.get_wrapper(session_id)

    if wrapper is None:
        raise HTTPException(404, "Session not found")

    recorder = SkillRecorder(wrapper.session)
    state = recorder.start(name=name)

    _recorders[session_id] = recorder

    return {
        "recording_id": state.id,
        "session_id": session_id,
        "status": state.status,
    }


@router.post("/sessions/{session_id}/recording/stop")
async def stop_recording(session_id: str, extract_skill: bool = True) -> dict:
    """
    Ferma recording e opzionalmente estrae skill.

    Args:
        session_id: ID sessione
        extract_skill: Se True, genera skill ottimizzata

    Returns:
        Recording state o skill
    """
    recorder = _recorders.get(session_id)
    if recorder is None or not recorder.is_recording:
        raise HTTPException(400, "No active recording")

    state = recorder.stop()

    result = {
        "recording_id": state.id,
        "action_count": len(state.actions),
        "duration_ms": state.total_duration_ms,
    }

    if extract_skill:
        extractor = SkillExtractor()
        skill = extractor.extract_skill(state, optimize=True)
        result["skill"] = {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "action_count": len(skill.actions),
            "parameters": skill.parameters,
        }

    del _recorders[session_id]

    return result


@router.get("/sessions/{session_id}/recording/status")
async def get_recording_status(session_id: str) -> dict:
    """Stato recording corrente."""
    recorder = _recorders.get(session_id)

    if recorder is None:
        return {"is_recording": False}

    state = recorder.state
    return {
        "is_recording": recorder.is_recording,
        "recording_id": state.id if state else None,
        "action_count": len(state.actions) if state else 0,
        "status": state.status if state else None,
    }


# --- Stats ---


@router.get("/stats")
async def get_stats() -> dict:
    """Statistiche browser manager."""
    manager = _get_manager()

    active = await manager.count_active()
    sessions = await manager.list_sessions()

    total_actions = sum(s.action_count for s in sessions)
    total_errors = sum(s.error_count for s in sessions)

    return {
        "active_sessions": active,
        "max_sessions": manager.max_sessions,
        "total_actions": total_actions,
        "total_errors": total_errors,
        "recordings_active": len(_recorders),
    }
