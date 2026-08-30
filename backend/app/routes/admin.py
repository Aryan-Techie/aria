"""Demo/debug endpoints — for showing judges the CRM record, calendar slot,
and escalation inbox that a live call actually produced.
"""
from fastapi import APIRouter

from app.calendar import service as calendar_service
from app.crm import service as crm_service
from app.escalation.inbox import inbox

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
