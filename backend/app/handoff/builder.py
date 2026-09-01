"""Turns a finished call into the wrap-up a rep can act on.

Everything factual is read off the records the tools wrote during the call -
the lead, the qualification state, the objections, the negotiation rounds, the
booking. The model is asked for exactly two sentences: a headline and a
recommended next action. That split is deliberate. A summariser handed the raw
transcript will confidently produce a detail nobody said, and a rep who opens a
call with an invented detail is worse off than a rep with a thin summary.

`heuristic_summary` fills both sentences without a model at all, so a failed or
unconfigured LLM costs a slightly duller wrap-up rather than no wrap-up.
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

from app.handoff.models import CallSummary, Urgency
from app.metrics import savings
from app.sessions.models import SessionState

logger = logging.getLogger("aria.handoff")

SUMMARY_SYSTEM_PROMPT = """You write the two-sentence top of a sales call wrap-up for the rep who now owns the lead. You are given the structured record of what an AI agent captured on the call - not a transcript to be re-summarised, so do not invent details that are not in it.

Respond with ONLY a JSON object with exactly these keys:
"headline": one sentence on what this call was and where it landed. Concrete and specific - a rep should know whether to care within five words.
"recommended_action": one sentence on the single most useful thing to do next. An action, not a sentiment: "send the trade-in valuation before Thursday", never "follow up".
"urgency": one of "now", "today", "this_week", "none"."""


class LLMClient(Protocol):
    def complete(self, *, system: str, prompt: str) -> str: ...


class _DefaultClient:
    def complete(self, *, system: str, prompt: str) -> str:
        from app.orchestrator.llm_client import default_llm_client

        turn = default_llm_client().create_turn(
            system=system, messages=[{"role": "user", "content": prompt}], tools=[]
        )
        return turn.text


def _facts(session: SessionState) -> list[str]:
    left = session.left_brain
    facts = []
    if left.user_count is not None:
        facts.append(f"{left.user_count} devices")
    if left.budget_range:
        facts.append(f"budget {left.budget_range}")
    if left.timeline:
        facts.append(f"timeline {left.timeline}")
    if left.decision_stage:
        facts.append(f"decision stage: {left.decision_stage}")
    if left.pain_points:
        facts.append("driving it: " + ", ".join(left.pain_points))
    return facts


def _agreed(session: SessionState) -> list[str]:
    """What the business is now on the hook for. This is the section a rep
    cannot afford to be missing: walking into a call not knowing what was
    already promised is how a deal gets re-negotiated from a worse position."""
    agreed: list[str] = []
    negotiation = session.negotiation
    offer = negotiation.last_offer
    if offer is not None:
        agreed.append(
            f"{negotiation.granted_discount_pct:g}% off list was offered and stands "
            f"(round {negotiation.round_count}, authorised by {offer.authorised_by})"
        )
        agreed.append(f"Quoted: {offer.price_summary}")
        for concession in offer.concessions:
            if concession.kind != "discount":
                agreed.append(f"Offered: {concession.detail}")
    if negotiation.human_approved_pct is not None:
        agreed.append(
            f"{negotiation.human_approved_pct:g}% approved by "
            f"{negotiation.human_approved_by or 'a manager'} during the call"
        )
    if session.booking_id:
        agreed.append("A meeting was booked and the invite has gone out")
    return agreed


def _owed(session: SessionState) -> list[str]:
    """The other half of the ledger - what we asked them for, and anything
    left hanging."""
    owed: list[str] = []
    offer = session.negotiation.last_offer
    if offer is not None:
        owed += [f"They were asked for: {c.detail}" for c in offer.commitments]
    if session.negotiation.pending_human_approval:
        owed.append(
            "A discount approval is still open - she told them it was with her manager"
        )
    return owed


def _risks(session: SessionState) -> list[str]:
    risks = [
        f"Unresolved {o.topic} objection: {o.raised_text}"
        for o in session.right_brain.objections
        if not o.resolved
    ]
    if session.right_brain.sentiment in ("skeptical", "frustrated"):
        risks.append(f"They ended the call sounding {session.right_brain.sentiment}")
    if session.right_brain.competitor_mentions:
        risks.append("Competing quotes in play: " + ", ".join(session.right_brain.competitor_mentions))
    if session.status == "escalated":
        risks.append("This call was escalated to a human")
    return risks


def _duration_seconds(session: SessionState) -> int:
    if session.ended_at is None:
        return 0
    return max(0, int((session.ended_at - session.created_at).total_seconds()))


def heuristic_summary(session: SessionState, summary: CallSummary) -> tuple[str, str, Urgency]:
    """Headline, action and urgency with no model involved.

    Reads off the outcome, which is the one thing about a call that is never
    ambiguous - and is exactly what a rep scanning a list of these is sorting
    on anyway.
    """
    who = summary.company or summary.contact or "An unknown caller"
    outcome = session.outcome or "follow_up"

    if outcome == "meeting_booked":
        return (
            f"{who} booked a meeting and the invite is out.",
            "Read the agreed section before the meeting - a discount may already have been offered.",
            "this_week",
        )
    if outcome == "escalated":
        return (
            f"{who} was escalated mid-call and is waiting on a person.",
            "Call them back - they asked for a human and did not get one on the call.",
            "now",
        )
    if outcome == "qualified":
        return (
            f"{who} qualified but did not book a time.",
            "Call them to put a time in the diary while the conversation is still warm.",
            "today",
        )
    if outcome == "disqualified":
        return (f"{who} is not a fit.", "No action needed; the record is closed.", "none")
    return (
        f"{who} called and the conversation did not reach a next step.",
        "Review what was captured and decide whether this is worth a call back.",
        "this_week",
    )


def build(session: SessionState, *, client: LLMClient | None = None) -> CallSummary:
    """Never raises. This runs off the back of a call that has already ended;
    there is nothing useful a caller could do with an exception, and a wrap-up
    that fails to arrive is the one failure mode this whole feature exists to
    remove."""
    from app.crm import service as crm_service

    lead = crm_service.get_lead(session.session_id)
    duration = _duration_seconds(session)

    summary = CallSummary(
        session_id=session.session_id,
        lead_id=session.crm_lead_id,
        company=(lead.company if lead else None) or session.left_brain.company,
        contact=lead.name if lead else None,
        outcome=session.outcome or "follow_up",
        facts=_facts(session),
        agreed=_agreed(session),
        owed=_owed(session),
        risks=_risks(session),
        duration_seconds=duration,
        turn_count=len(session.transcript),
        minutes_saved=savings.total_minutes(
            session.tool_calls, duration, confirmation_sent=session.confirmation_sent
        ),
    )

    headline, action, urgency = heuristic_summary(session, summary)
    try:
        raw = (client or _DefaultClient()).complete(
            system=SUMMARY_SYSTEM_PROMPT, prompt=_prompt(summary)
        )
        data = json.loads(_strip_fence(raw))
        headline = data.get("headline") or headline
        action = data.get("recommended_action") or action
        urgency = data.get("urgency") if data.get("urgency") in ("now", "today", "this_week", "none") else urgency
    except Exception as exc:
        logger.info("summary headline fell back to the heuristic (%s)", exc)

    summary.headline = headline
    summary.recommended_action = action
    summary.urgency = urgency
    return summary


def _prompt(summary: CallSummary) -> str:
    return (
        f"Company: {summary.company or 'unknown'}\n"
        f"Contact: {summary.contact or 'unknown'}\n"
        f"Outcome: {summary.outcome}\n"
        f"What they need: {'; '.join(summary.facts) or 'nothing captured'}\n"
        f"What was agreed: {'; '.join(summary.agreed) or 'nothing'}\n"
        f"What we owe them: {'; '.join(summary.owed) or 'nothing'}\n"
        f"Risks: {'; '.join(summary.risks) or 'none'}\n"
        f"Call length: {summary.duration_seconds}s over {summary.turn_count} turns"
    )


def _strip_fence(raw: str) -> str:
    text = (raw or "").strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text
