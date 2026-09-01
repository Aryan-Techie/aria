"""Dispatches a single tool call to the right module and mutates SessionState
in place. Pure logic — no RTM publishing here (pipeline.py wraps each
dispatch call with tool_call_started/finished + event-specific publishes, per
the plan's RTM event schema). Kept side-effect-scoped to (session, backing
stores) so it's directly unit-testable without any LLM or network involved.
"""
from datetime import datetime, timezone

from app.background import run_in_background
from app.calendar import service as calendar_service
from app.calendar.labels import slot_label as _slot_label
from app.calendar.models import SlotTakenError
from app.crm import service as crm_service
from app.deal import desk, engine, policy
from app.escalation import service as escalation_service, triggers
from app.escalation.models import TriggerSource
from app.memory.schema import Objection
from app.notify import service as notify_service
from app.rag import retriever
from app.specialists import solutions


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
    payload = {"chunks": [r.model_dump() for r in results]}

    # A weak retrieval used to leave two options - guess, or fetch a human -
    # and the second is the one that looks most reasonable in the moment.
    # There is a third now, and the model is pointed at it here rather than
    # left to remember the prompt on the one turn where it matters.
    if session.last_rag_score < triggers.LOW_CONFIDENCE_THRESHOLD:
        payload["guidance"] = (
            "This search did not turn up a confident answer. Do NOT guess and do NOT "
            "escalate yet - if the question is technical, put it to "
            "ask_solutions_engineer, which reads everything we have and will tell you "
            "exactly what is supported and what is genuinely still open."
        )
    return payload


def _ask_solutions_engineer(tool_input: dict, session, **_) -> dict:
    """Layer 2, the other seat - see app/specialists/solutions.py.

    Retrieves more widely than the sales lookup does, because a specialist
    reading everything and reporting the boundary is the whole point; four
    chunks is enough to answer a pricing question and not enough to be sure
    what a corpus does not say.
    """
    question = tool_input["question"]
    results = retriever.search(question, top_k=8)
    session.last_rag_score = results[0].score if results else 0.0

    answer = solutions.consult(
        question=question,
        chunks=[r.model_dump() for r in results],
        context=tool_input.get("their_setup") or session.left_brain.model_dump_json(),
    )

    return {
        "answer": answer.answer,
        "confidence": answer.confidence,
        "still_open": answer.open_questions,
        "guidance": (
            "Say the answer in your own words, and say the open questions out loud too - "
            "a customer told precisely what is still to be checked trusts you more than one "
            "told everything will be fine. Offer to have an engineer confirm them, and keep "
            "the call moving."
            if not answer.escalate_recommended
            else "Our material does not support an answer here. Tell them you would rather "
            "have an engineer confirm it than guess, then call escalate_to_human with this "
            "specific question so the person arrives knowing exactly what is being asked."
        ),
    }


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
    session.booking_slot_id = tool_input["slot_id"]
    session.outcome = "meeting_booked"
    crm_service.qualify_lead(session.session_id, "meeting_booked", "meeting booked via calendar tool")
    slot = calendar_service.calendar_store.get_slot(tool_input["slot_id"])

    if slot is not None:
        # Off the turn path: an SMTP handshake takes 1-3s, which is spent
        # directly out of Agora's webhook timeout window. The booking is
        # already committed, so the reply must not wait on the email.
        run_in_background(notify_service.on_booking, session, slot)

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


def _negotiate_deal(tool_input: dict, session, **_) -> dict:
    """The three layers, in one tool call.

    Layer 1 (Aria) does not decide this. She reports what was asked; the deal
    desk (layer 2, its own agent and its own model call) proposes; the engine
    clamps that proposal against policy; and if what the desk wants is past
    what it is allowed to sign, a human (layer 3) is asked - without ending
    the call, because a question about margin is not a handoff.

    What comes back is deliberately finished: a preformatted price sentence,
    the concessions to offer, and the commitment to ask for in return. The
    same reasoning as the calendar slot labels - the model reads out a number
    rather than working one out, because a wrong price said to a buyer is
    unrecoverable in a way a wrong weekday is not.
    """
    mix = tool_input.get("device_mix") or None
    units = sum(int(entry.get("quantity") or 0) for entry in mix) if mix else 0
    units = units or session.left_brain.user_count or 0
    if units <= 0:
        return {
            "error": "no_device_count",
            "guidance": (
                "Nothing can be priced yet. Ask how many devices they are "
                "looking at, record it with crm_upsert_lead, then negotiate."
            ),
        }

    term_months = policy.DEFAULT_POLICY.financing_months if tool_input.get("financing") else 0
    trade_in = int(tool_input.get("trade_in_devices") or 0)
    negotiation = session.negotiation

    base = engine.build_quote(
        units=units, device_mix=mix, trade_in_devices=trade_in, term_months=term_months
    )

    requested_pct = tool_input.get("requested_discount_pct")
    if requested_pct is None and tool_input.get("target_total_price"):
        requested_pct = engine.discount_for_target(base, float(tool_input["target_total_price"]))
    if requested_pct is None and tool_input.get("target_unit_price"):
        requested_pct = engine.discount_for_target(
            base, float(tool_input["target_unit_price"]) * base.units
        )
    requested_pct = float(requested_pct) if requested_pct is not None else None

    round_number = negotiation.round_count + 1
    proposal = desk.consult(
        customer_ask=tool_input["customer_ask"],
        requested_pct=requested_pct,
        list_total=base.list_total,
        units=base.units,
        tier_name=base.tier_name,
        volume_discount_pct=base.volume_discount_pct,
        already_granted=negotiation.granted_discount_pct,
        round_number=round_number,
        competitor_quote=tool_input.get("competitor_quote"),
        qualification=session.left_brain.model_dump_json(),
        objections="; ".join(o.raised_text for o in session.right_brain.objections),
    )

    granted, authorised_by, clamped, clamp_reason, requires_human = engine.authorise(
        requested_pct=proposal.recommended_discount_pct,
        round_number=round_number,
        already_granted=negotiation.granted_discount_pct,
        has_commitment=bool(proposal.commitments),
        human_approved_pct=negotiation.human_approved_pct,
    )

    offer = engine.build_offer(
        round_number=round_number,
        customer_ask=tool_input["customer_ask"],
        requested_pct=requested_pct,
        granted_pct=granted,
        authorised_by=authorised_by,
        clamped=clamped,
        clamp_reason=clamp_reason,
        requires_human=requires_human,
        concessions=proposal.concessions,
        commitments=proposal.commitments,
        rationale=proposal.rationale,
        units=units,
        device_mix=mix,
        trade_in_devices=trade_in,
        term_months=term_months,
    )

    negotiation.rounds.append(offer)
    negotiation.granted_discount_pct = granted

    crm_service.add_note(
        session.session_id,
        f"Round {round_number}: asked {requested_pct if requested_pct is not None else 'unspecified'}"
        f" -> granted {granted:g}% (authorised by {authorised_by})"
        + (f"; {clamp_reason}" if clamp_reason else "")
        + (
            "; asked in return: " + ", ".join(c.detail for c in offer.commitments)
            if offer.commitments
            else ""
        ),
    )

    if requires_human and not negotiation.pending_human_approval:
        # Not escalate_to_human: that hands the call over and ends it. The
        # customer stays with Aria while one person answers one question.
        record, _position = escalation_service.escalate(
            session.session_id,
            f"Deal desk recommends {proposal.recommended_discount_pct:g}% on "
            f"{base.units} devices (${base.list_total:,.0f} list); above the desk's "
            f"own ceiling, so it needs a human signature.",
            "deal_approval",
            kind="deal_approval",
            transcript=session.transcript,
            left_brain=session.left_brain,
            right_brain=session.right_brain,
            lead_id=session.crm_lead_id,
        )
        negotiation.pending_human_approval = True
        negotiation.approval_escalation_id = record.id

    return {
        "price_summary": offer.price_summary,
        "granted_discount_pct": granted,
        "authorised_by": authorised_by,
        "offer_concessions": [c.detail for c in offer.concessions],
        "ask_for_in_return": [c.detail for c in offer.commitments],
        "desk_read": proposal.read,
        "awaiting_human_approval": negotiation.pending_human_approval,
        "guidance": _negotiation_guidance(offer, negotiation),
    }


def _negotiation_guidance(offer, negotiation) -> str:
    """What she is allowed to say about this offer, in one line.

    Written here rather than left to the prompt because it is the difference
    between "I can do ten percent" and "I've asked my manager about ten
    percent" - and saying the first while the second is true is a promise the
    business has not made.
    """
    if negotiation.pending_human_approval and offer.requires_human:
        return (
            f"Offer the {offer.granted_discount_pct:g}% you are authorised for NOW - do not make "
            "them wait for it. Say you have gone to your sales manager for the rest and will "
            "confirm before the call ends. Do NOT state the higher number as agreed."
        )
    if offer.granted_discount_pct <= 0:
        return (
            "No discount is authorised. Do not apologise your way out of this - lead with the "
            "levers above, which cost them nothing, and ask what is actually driving the number: "
            "the total, the unit price, the timing of the spend, or a competing quote."
        )
    return (
        "Read price_summary as the numbers - do not recalculate any of it. Offer the concessions, "
        "then ask for what is in ask_for_in_return in the same breath. Never give ground without "
        "asking for something back."
    )


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
    "ask_solutions_engineer": _ask_solutions_engineer,
    "crm_upsert_lead": _crm_upsert_lead,
    "crm_qualify_lead": _crm_qualify_lead,
    "calendar_check_availability": _calendar_check_availability,
    "calendar_book_meeting": _calendar_book_meeting,
    "negotiate_deal": _negotiate_deal,
    "escalate_to_human": _escalate_to_human,
    "log_objection": _log_objection,
    "update_sentiment": _update_sentiment,
}
