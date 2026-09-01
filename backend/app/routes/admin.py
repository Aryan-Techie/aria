"""Demo/debug endpoints — for showing judges the CRM record, calendar slot,
and escalation inbox that a live call actually produced.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.calendar import service as calendar_service
from app.crm import service as crm_service
from app.escalation.inbox import inbox
from app.handoff import service as handoff_service
from app.rtm.publisher import default_rtm_publisher
from app.sessions.store import session_store

router = APIRouter()


@router.get("/api/leads")
def list_leads() -> list[dict]:
    return [lead.model_dump(mode="json") for lead in crm_service.list_leads()]


@router.get("/api/calendar/slots")
def list_slots() -> list[dict]:
    return [slot.model_dump(mode="json") for slot in calendar_service.list_available()]


@router.get("/api/inbox")
def list_inbox() -> list[dict]:
    return [record.model_dump(mode="json") for record in inbox.all()]


@router.get("/api/summaries")
def list_summaries() -> list[dict]:
    """The wrap-up produced when each call ended - what the rep was told."""
    return [summary.model_dump(mode="json") for summary in handoff_service.all_summaries()]


@router.get("/api/summaries/{session_id}")
def get_summary(session_id: str) -> dict:
    summary = handoff_service.get(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No wrap-up for session: {session_id}")
    return summary.model_dump(mode="json")


class ApprovalRequest(BaseModel):
    approved_pct: float
    approved_by: str = "sales manager"


@router.post("/api/inbox/{escalation_id}/approve")
def approve_discount(escalation_id: str, body: ApprovalRequest) -> dict:
    """Layer 3, answering while the call is still running.

    The whole point of separating a discount approval from a handoff is that
    this does not take the call away from Aria — a person answers one question
    about margin and the conversation carries on. So this writes the approved
    figure onto the live session, and the next system prompt renders it
    (pipeline.py::_render_negotiation): she can lead her very next sentence
    with the number a human just signed, seconds after they clicked.

    It deliberately does not push anything at the model. There is no way to
    interrupt a turn that is already generating, and a mid-sentence injection
    would be heard as her talking over herself. Picking it up on the next turn
    is both simpler and what a rep being handed a note would do.
    """
    record = inbox.get(escalation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such escalation: {escalation_id}")
    if record.kind != "deal_approval":
        raise HTTPException(
            status_code=400,
            detail="That escalation is a handoff, not a discount approval — there is nothing to approve.",
        )

    inbox.resolve_approval(escalation_id, body.approved_pct, body.approved_by)

    session = session_store.get(record.session_id)
    if session is not None:
        negotiation = session.negotiation
        negotiation.human_approved_pct = body.approved_pct
        negotiation.human_approved_by = body.approved_by
        negotiation.pending_human_approval = False
        session_store.save(session)
        default_rtm_publisher().publish(
            record.session_id,
            "deal_approval_granted",
            {
                "escalation_id": escalation_id,
                "approved_pct": body.approved_pct,
                "approved_by": body.approved_by,
            },
        )

    return {
        "escalation_id": escalation_id,
        "session_id": record.session_id,
        "approved_pct": body.approved_pct,
        "approved_by": body.approved_by,
        # False when the call has already ended, or the backend restarted
        # since — the answer is still recorded on the inbox record either way.
        "applied_to_live_call": session is not None,
    }
