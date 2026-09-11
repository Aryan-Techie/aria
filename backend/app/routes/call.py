from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.crm import service as crm_service
from app.rtm.publisher import default_rtm_publisher
from app.sessions import controller
from app.sessions.store import session_store

router = APIRouter()


class LeadUpdate(BaseModel):
    """A manual edit typed into the console rather than said on the call.

    Every field optional - a partial edit (just the email, say) must not
    clobber what Aria has already captured, same rule crm_upsert_lead
    follows for the voice path."""

    name: str | None = None
    title: str | None = None
    company: str | None = None
    industry: str | None = None
    email: str | None = None
    phone: str | None = None
    user_count: int | None = None
    budget_range: str | None = None
    timeline: str | None = None


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


@router.patch("/api/session/{session_id}/lead")
def update_lead_manually(session_id: str, body: LeadUpdate) -> dict:
    """The console's own "Edit details" affordance - typed in rather than
    said out loud. Written through the exact same crm_upsert_lead path the
    voice tools use, then mirrored onto the live session's LeftBrain so
    Aria's next turn already has it and never asks again."""
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"No such session: {session_id}")

    lead = crm_service.upsert_lead(session_id, **body.model_dump(exclude_none=True))
    session.crm_lead_id = lead.id
    crm_service.sync_left_brain(session, lead)
    default_rtm_publisher().publish(session_id, "qualification_updated", session.left_brain.model_dump(mode="json"))
    return {"lead_id": lead.id, "lead": lead.model_dump(mode="json")}


@router.post("/api/call/{session_id}/end")
def end_call(session_id: str) -> dict:
    try:
        return controller.end_call(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
