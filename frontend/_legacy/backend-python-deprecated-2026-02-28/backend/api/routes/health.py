"""Health check and status endpoints."""

from fastapi import APIRouter

from backend.services.me4brain_service import Me4BrAInService

router = APIRouter()


@router.get("/health")
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {"status": "ok", "service": "persan"}


@router.get("/status")
async def status() -> dict:
    """
    Detailed status including Me4BrAIn connection.

    Returns:
        Status of PersAn and Me4BrAIn connection.
    """
    me4brain = Me4BrAInService()
    me4brain_status = await me4brain.check_health()

    return {
        "persan": "ok",
        "me4brain": me4brain_status,
    }
