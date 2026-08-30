from fastapi import APIRouter, HTTPException

from app.sessions import controller
from app.sessions.store import session_store

router = APIRouter()


@router.post("/api/call/start")
def start_call() -> dict:
    return controller.start_call()


@router.get("/api/session/{session_id}/events")
def session_events(session_id: str, since: int = 0) -> dict:
    """Polled by the browser for the live panels.

    `since` is the number of events the caller already has; the response
    returns only newer ones plus the current cursor, so a poll every second
    costs almost nothing once the call is quiet.
    """
    session = session_store.get(session_id)
    if session is None:
        return {"events": [], "cursor": 0, "status": None, "outcome": None}
    return {
        "events": session.events[since:],
        "cursor": len(session.events),
        "status": session.status,
        "outcome": session.outcome,
        "left_brain": session.left_brain.model_dump(mode="json"),
        "right_brain": session.right_brain.model_dump(mode="json"),
    }


@router.post("/api/call/{session_id}/end")
def end_call(session_id: str) -> dict:
    try:
        return controller.end_call(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
