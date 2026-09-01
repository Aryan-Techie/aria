"""Build the wrap-up, deliver it, and keep it where the console can read it.

One entry point, called from sessions/controller.end_call. Deterministic, not
a tool: the model does not get to decide whether a human is told what happened
on a call, for the same reason it does not decide whether a customer is told
about their own meeting.
"""
from __future__ import annotations

import logging

from app.handoff import builder, delivery
from app.handoff.models import CallSummary
from app.sessions.models import SessionState

logger = logging.getLogger("aria.handoff")

# session_id -> the wrap-up produced when that call ended. Read by
# GET /api/summaries; kept in the process alongside the session store rather
# than in the CRM, because the console wants the structured object and the CRM
# note is prose.
_summaries: dict[str, CallSummary] = {}


def on_call_end(session: SessionState) -> CallSummary | None:
    """Always called through background.run_in_background - see the caller."""
    try:
        summary = builder.build(session)
    except Exception:
        logger.warning("could not build a wrap-up for session %s", session.session_id, exc_info=True)
        return None

    _summaries[session.session_id] = summary
    delivery.deliver(summary)
    return summary


def get(session_id: str) -> CallSummary | None:
    return _summaries.get(session_id)


def all_summaries() -> list[CallSummary]:
    return list(_summaries.values())


def reset() -> None:
    _summaries.clear()
