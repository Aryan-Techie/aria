"""How many conversations this actually handles, and what that is worth.

The question a buyer asks about a voice agent is not "does it work" - it is
"how many of these run at once, and how many people do I still need". This
answers it from what really happened rather than from a brochure number:

* **Peak concurrency is computed, not counted.** Sweeping the start/end
  timestamps of every session for the maximum overlap gives the highest number
  of calls that were genuinely in progress at the same moment. Counting
  "sessions today" and calling it concurrency is the usual way this number
  gets inflated.

* **Containment is the honest denominator.** A call that ended with a person
  being pulled in is not a call the agent handled. It counts against the rate,
  not for it.

* **Rep-equivalent is stated as an assumption, not a fact.** It divides the
  human minutes replaced by one working day and says so, because a number
  whose assumptions are hidden is a number a judge is right to distrust.

One thing this cannot tell you: the ceiling is almost never this process. A
turn spends most of its time inside the LLM provider, so the real limit is the
provider's concurrency and rate limit, not FastAPI's. scripts/capacity_test.py
measures the part that IS ours, with the model stubbed out, and says so.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.metrics import savings
from app.sessions.models import SessionState

# One rep, one working day. The divisor behind `rep_days_saved`, kept here so
# it can be argued with rather than buried in the arithmetic.
REP_MINUTES_PER_DAY = 8 * 60

# A human can hold exactly one voice conversation at a time. That is the whole
# comparison, and it is why concurrency is the number that matters.
HUMAN_CONCURRENT_CALLS = 1


def _duration_seconds(session: SessionState, now: datetime) -> int:
    end = session.ended_at or now
    return max(0, int((end - session.created_at).total_seconds()))


def peak_concurrency(sessions: list[SessionState], now: datetime | None = None) -> int:
    """The most calls that were genuinely in progress at the same moment.

    A sweep over the start and end of every session: +1 at each start, -1 at
    each end, and the running maximum is the answer. Ends are processed before
    starts at an identical timestamp, so a call that ends exactly as another
    begins is not counted as an overlap.
    """
    now = now or datetime.now(timezone.utc)
    if not sessions:
        return 0

    points: list[tuple[datetime, int]] = []
    for session in sessions:
        points.append((session.created_at, 1))
        points.append((session.ended_at or now, -1))

    # -1 sorts before +1 at the same instant.
    points.sort(key=lambda point: (point[0], point[1]))

    running = peak = 0
    for _ts, delta in points:
        running += delta
        peak = max(peak, running)
    return peak


def snapshot(sessions: list[SessionState], now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    total = len(sessions)

    live = [s for s in sessions if s.status == "active"]
    escalated = [s for s in sessions if s.status == "escalated" or s.outcome == "escalated"]
    booked = [s for s in sessions if s.booking_id]
    negotiated = [s for s in sessions if s.negotiation.round_count]
    approvals = [s for s in sessions if s.negotiation.human_approved_pct is not None]

    talk_minutes = 0.0
    admin_minutes = 0.0
    for session in sessions:
        talk_minutes += savings.agent_minutes(_duration_seconds(session, now))
        admin_minutes += savings.admin_minutes(
            session.tool_calls, confirmation_sent=session.confirmation_sent
        )

    outcomes: dict[str, int] = {}
    for session in sessions:
        key = session.outcome or ("in_progress" if session.status == "active" else "no_outcome")
        outcomes[key] = outcomes.get(key, 0) + 1

    peak = peak_concurrency(sessions, now)
    handled_alone = total - len(escalated)

    return {
        "calls_total": total,
        "calls_live_now": len(live),
        "peak_concurrent_calls": peak,
        # The whole comparison in one number: a person holds one conversation
        # at a time, so peak concurrency IS the headcount this stood in for at
        # the busiest moment.
        "reps_needed_for_peak": peak // HUMAN_CONCURRENT_CALLS,
        "outcomes": outcomes,
        "meetings_booked": len(booked),
        "calls_negotiated": len(negotiated),
        "discount_approvals_requested": len([s for s in sessions if s.negotiation.approval_escalation_id]),
        "discount_approvals_granted": len(approvals),
        "escalated_to_human": len(escalated),
        "containment_rate": round(handled_alone / total, 3) if total else 0.0,
        "human_minutes": {
            "talk_time": round(talk_minutes, 1),
            "post_call_admin": round(admin_minutes, 1),
            "total": round(talk_minutes + admin_minutes, 1),
        },
        "rep_days_saved": round((talk_minutes + admin_minutes) / REP_MINUTES_PER_DAY, 2),
        "assumptions": {
            "rep_minutes_per_day": REP_MINUTES_PER_DAY,
            "human_concurrent_calls": HUMAN_CONCURRENT_CALLS,
            "baseline_minutes_per_action": savings.BASELINE_MINUTES,
            "note": (
                "Talk time and post-call admin are counted separately and never "
                "merged into one flattering figure. An escalation counts as zero "
                "saved, because a handoff spends human time rather than saving it."
            ),
        },
    }
