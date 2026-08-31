"""Dispatches a single tool call to the right module and mutates SessionState
in place. Pure logic — no RTM publishing here (pipeline.py wraps each
dispatch call with tool_call_started/finished + event-specific publishes, per
the plan's RTM event schema). Kept side-effect-scoped to (session, backing
stores) so it's directly unit-testable without any LLM or network involved.
"""
import os
from datetime import datetime, timezone

from app.calendar import service as calendar_service
from app.calendar.models import SlotTakenError
from app.crm import service as crm_service
from app.escalation import service as escalation_service
from app.escalation.models import TriggerSource
from app.memory.schema import Objection
from app.rag import retriever


def _dt(value: str | None) -> datetime | None:
    """Parses an ISO datetime from the model and always returns it tz-aware.

    The seeded slots are UTC-aware, but the model naturally emits a bare
    "2026-08-31T10:00:00" with no offset. Comparing the two raised
    "can't compare offset-naive and offset-aware datetimes" inside
    calendar.list_available, which killed the whole turn - so booking a
    meeting, the demo's headline outcome, could never actually complete.
    A missing offset is treated as UTC, matching the seeded slots.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def dispatch(tool_name: str, tool_input: dict, session, *, trigger_source: TriggerSource = "llm") -> dict:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"unknown tool: {tool_name}"}
    return handler(tool_input, session, trigger_source=trigger_source)


def _search_pricing_rag(tool_input: dict, session, **_) -> dict:
    results = retriever.search(tool_input["query"], top_k=tool_input.get("top_k", 4))
    session.last_rag_score = results[0].score if results else 0.0
    return {"chunks": [r.model_dump() for r in results]}


def _crm_upsert_lead(tool_input: dict, session, **_) -> dict:
    lead = crm_service.upsert_lead(
        session.session_id,
        company=tool_input.get("company"),
        user_count=tool_input.get("user_count"),
        budget_range=tool_input.get("budget_range"),
        timeline=tool_input.get("timeline"),
        pain_points=tool_input.get("pain_points"),
        decision_stage=tool_input.get("decision_stage"),
        name=tool_input.get("name"),
        email=tool_input.get("email"),
        phone=tool_input.get("phone"),
    )
    session.crm_lead_id = lead.id
    for field in ("company", "user_count", "budget_range", "timeline", "decision_stage"):
        value = getattr(lead, field)
        if value is not None:
            setattr(session.left_brain, field, value)
    session.left_brain.pain_points = lead.pain_points
    return {"lead_id": lead.id, "lead": lead.model_dump(mode="json")}


def _crm_qualify_lead(tool_input: dict, session, **_) -> dict:
    lead = crm_service.qualify_lead(session.session_id, tool_input["status"], tool_input["reason"])
    session.crm_lead_id = lead.id
    if tool_input["status"] in ("qualified", "disqualified"):
        session.outcome = tool_input["status"]
    return {"lead_id": lead.id, "status": lead.status}



def _slot_label(start: datetime) -> str:
    """"Tuesday 1 September at 10:00 AM".

    glibc and MSVC disagree on the no-padding strftime flag - "%-d" on Linux,
    "%#d" on Windows - and the wrong one is not an error, it emits the literal
    text. Branch on the platform rather than shipping "Tuesday %-d September".
    """
    fmt = "%A %#d %B at %#I:%M %p" if os.name == "nt" else "%A %-d %B at %-I:%M %p"
    return start.strftime(fmt)


def _calendar_check_availability(tool_input: dict, session, **_) -> dict:
    slots = calendar_service.list_available(
        _dt(tool_input.get("date_range_start")), _dt(tool_input.get("date_range_end"))
    )

    # `label` is pre-formatted rather than left to the model. Stamping today's
    # date into the system prompt was not enough on its own: asked for slots
    # on Monday 7 September 2026 the model offered "Sunday the seventh", and
    # in an earlier run called 1 September "the second". A customer being
    # asked to commit to a time hears that as carelessness. Handing over the
    # finished phrase removes the arithmetic instead of asking it to be
    # careful.
    return {
        "slots": [
            {
                **slot.model_dump(mode="json"),
                "label": _slot_label(slot.start),
            }
            for slot in slots
        ],
        "speak_these_labels_verbatim": (
            "Use each slot's `label` exactly as written when offering times - do "
            "not work out the weekday or date yourself."
        ),
    }


def _calendar_book_meeting(tool_input: dict, session, **_) -> dict:
    lead_id = session.crm_lead_id
    if lead_id is None:
        lead = crm_service.upsert_lead(session.session_id)
        lead_id = session.crm_lead_id = lead.id

    try:
        booking = calendar_service.book(tool_input["slot_id"], lead_id=lead_id, session_id=session.session_id)
    except (SlotTakenError, ValueError) as exc:
        return {"error": str(exc)}

    session.booking_id = booking.id
    session.outcome = "meeting_booked"
    crm_service.qualify_lead(session.session_id, "meeting_booked", "meeting booked via calendar tool")
    slot = calendar_service.calendar_store.get_slot(tool_input["slot_id"])
    return {"booking_id": booking.id, "slot": slot.model_dump(mode="json") if slot else None}


def _escalate_to_human(tool_input: dict, session, *, trigger_source: TriggerSource, **_) -> dict:
    record, position = escalation_service.escalate(
        session.session_id,
        tool_input["reason"],
        trigger_source,
        transcript=session.transcript,
        left_brain=session.left_brain,
        right_brain=session.right_brain,
        lead_id=session.crm_lead_id,
    )
    session.status = "escalated"
    session.outcome = "escalated"
    return {"escalation_id": record.id, "inbox_position": position}


def _log_objection(tool_input: dict, session, **_) -> dict:
    topic = tool_input["topic"]
    resolved = tool_input.get("resolved", False)
    existing = next(
        (o for o in session.right_brain.objections if o.topic == topic and not o.resolved),
        None,
    )
    if existing is not None:
        existing.attempts += 1
        if resolved:
            existing.resolved = True
            existing.resolution_text = tool_input.get("resolution_text")
        objection = existing
    else:
        objection = Objection(
            topic=topic,
            raised_text=tool_input["raised_text"],
            resolved=resolved,
            resolution_text=tool_input.get("resolution_text"),
        )
        session.right_brain.objections.append(objection)
    return {"topic": objection.topic, "attempts": objection.attempts, "resolved": objection.resolved}


def _update_sentiment(tool_input: dict, session, **_) -> dict:
    sentiment = tool_input["sentiment"]
    session.right_brain.sentiment = sentiment
    session.right_brain.sentiment_history.append(sentiment)
    return {"sentiment": sentiment}


_HANDLERS = {
    "search_pricing_rag": _search_pricing_rag,
    "crm_upsert_lead": _crm_upsert_lead,
    "crm_qualify_lead": _crm_qualify_lead,
    "calendar_check_availability": _calendar_check_availability,
    "calendar_book_meeting": _calendar_book_meeting,
    "escalate_to_human": _escalate_to_human,
    "log_objection": _log_objection,
    "update_sentiment": _update_sentiment,
}
