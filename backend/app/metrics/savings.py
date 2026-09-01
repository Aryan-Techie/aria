"""How much human time a call actually took off someone's desk.

The honest version of "AI saves you time", which means being careful about
three things that are easy to fudge:

* **Two different numbers, never added up sloppily.** Talking to the customer
  for eleven minutes is eleven minutes a rep did not spend on the phone. The
  CRM record, the quote, the calendar back-and-forth and the confirmation
  email are *separate* work that would have happened after the call. They are
  counted apart and reported apart.

* **Idempotent work is counted once.** `crm_upsert_lead` firing five times as
  the customer corrects themselves is still one lead record, not five lots of
  data entry. Only the tools that genuinely repeat work accrue per use.

* **Human time is not saved by being spent.** An escalation is worth zero
  here, because it *is* a person's time. Counting a handoff as a saving is
  the exact way these numbers become a lie.

The baselines are our own estimates for how long each piece takes a rep, kept
in one table so they can be argued with rather than buried in a calculation.
"""
from __future__ import annotations

# Minutes of human work each tool stands in for, if a person had to do it
# after the call from their own notes.
BASELINE_MINUTES: dict[str, float] = {
    # Writing up who called, what they need, and how many devices.
    "crm_upsert_lead": 3.0,
    "crm_qualify_lead": 1.0,
    # Looking a price, spec or comparison up in the deck.
    "search_pricing_rag": 2.0,
    # Emailing a solutions engineer and waiting for the reply - the part
    # that used to happen after the call, if it happened at all.
    "ask_solutions_engineer": 12.0,
    # Building a priced quote and chasing whoever has to approve the discount.
    "negotiate_deal": 20.0,
    # The email thread that finds a time everyone can make.
    "calendar_check_availability": 4.0,
    "calendar_book_meeting": 11.0,
    # Call notes.
    "log_objection": 0.5,
    "update_sentiment": 0.0,
    # A handoff spends human time rather than saving it.
    "escalate_to_human": 0.0,
}

# Work that produces one artefact however many times it is called. Repeated
# calls refine the same record, so they do not earn the baseline again.
ONCE_PER_CALL = {
    "crm_upsert_lead",
    "crm_qualify_lead",
    "calendar_book_meeting",
}

# Sending the confirmation and the calendar invite, which the tools do not
# model as a call of their own - it fires from the booking path.
CONFIRMATION_MINUTES = 4.0


def admin_minutes(tool_calls: list[str], *, confirmation_sent: bool = False) -> float:
    """Post-call paperwork the agent has already finished by the time the
    customer hangs up. `tool_calls` is the tool name of every dispatch on the
    call, in order and with repeats."""
    counted_once: set[str] = set()
    total = 0.0
    for name in tool_calls:
        if name in ONCE_PER_CALL:
            if name in counted_once:
                continue
            counted_once.add(name)
        total += BASELINE_MINUTES.get(name, 0.0)
    if confirmation_sent:
        total += CONFIRMATION_MINUTES
    return round(total, 1)


def agent_minutes(duration_seconds: int) -> float:
    """Time on the phone - a rep's hour that was never booked."""
    return round(max(0, duration_seconds) / 60.0, 1)


def total_minutes(
    tool_calls: list[str], duration_seconds: int, *, confirmation_sent: bool = False
) -> float:
    return round(
        admin_minutes(tool_calls, confirmation_sent=confirmation_sent)
        + agent_minutes(duration_seconds),
        1,
    )
