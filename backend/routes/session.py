"""Session management endpoints."""
import logging
from fastapi import APIRouter, Query
from backend.models.schemas import SessionInfo, SessionClearRequest
from backend.services.session_store import SessionStore

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/session/{session_id}", response_model=SessionInfo, summary="Get session history")
async def get_session(session_id: str) -> SessionInfo:
    """
    Retrieve query history for a specific session.
    Each session stores the last N interactions (configurable via SESSION_MAX_HISTORY).
    Sessions are fully isolated — no cross-session data leakage.
    """
    store = SessionStore.get_instance()
    info = store.session_info(session_id)
    return SessionInfo(**info)


@router.delete("/session/{session_id}", summary="Clear session history")
async def clear_session(session_id: str) -> dict:
    """Clear all stored history for a session."""
    store = SessionStore.get_instance()
    store.clear(session_id)
    log.info("Session cleared: %s", session_id)
    return {"cleared": True, "session_id": session_id}


@router.get("/session", summary="Get session stats")
async def session_stats() -> dict:
    """Return aggregate session statistics."""
    store = SessionStore.get_instance()
    return {
        "active_sessions": store.active_sessions(),
        "max_history_per_session": store._max_history,
    }
