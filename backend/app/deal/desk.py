"""Layer 2: the deal desk agent.

Aria is layer 1. She is optimised for a live conversation - short replies, one
question at a time, a voice that has to keep moving. Reasoning about margin is
a different job with a different objective, and asking one prompt to do both
is how you get an agent that is either a pushover on price or a robot in
conversation.

So the desk is a genuinely separate agent: its own system prompt, its own
model call, its own view of the call (qualification state, what has already
been conceded, what the customer is holding over us), and no ability to speak
to the customer at all. It returns a *proposal*. engine.authorise() decides
what any of it is worth, and layer 3 - a person - is reached only when the
proposal is past what layer 2 is allowed to sign.

Two properties make this safe to put on a live call:

  * it is off the customer's ear. The desk answers to Aria, not to the buyer,
    so a weak or strange proposal is clamped before a word of it is spoken.
  * it can fail. `heuristic_proposal` is a deterministic fallback, so a desk
    that times out or returns unparseable JSON costs one bridge line, not the
    negotiation.

The latency is not hidden either - it is narrated. "Let me see what I can do
on that" is what a human rep says while checking with their manager, and that
is exactly what is happening.
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

from pydantic import BaseModel, Field

from app.deal.models import Commitment, Concession
from app.deal.policy import DEFAULT_POLICY, DealPolicy

logger = logging.getLogger("aria.deal")


class DeskProposal(BaseModel):
    """What the desk would like to do, before policy is applied to it."""

    recommended_discount_pct: float = 0.0
    concessions: list[Concession] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)
    rationale: str = ""
    read: str = ""  # the desk's read of what is really blocking the deal


class DeskClient(Protocol):
    def complete(self, *, system: str, prompt: str) -> str: ...


class LLMDeskClient:
    """Runs the desk on the same provider stack the conversation uses.

    Groq first, Anthropic behind it - the desk sits on the turn path, so it
    inherits the latency work already done for the conversation rather than
    adding a second, slower vendor path of its own.
    """

    def __init__(self, client=None):
        self._client = client

    def complete(self, *, system: str, prompt: str) -> str:
        client = self._client
        if client is None:
            from app.orchestrator.llm_client import default_llm_client

            client = self._client = default_llm_client()
        turn = client.create_turn(
            system=system, messages=[{"role": "user", "content": prompt}], tools=[]
        )
        return turn.text


def _system_prompt(policy: DealPolicy) -> str:
    return f"""You are the deal desk for Apple's business sales team. A voice agent (Aria) is live on a call with a customer right now and has come to you because the customer is pushing on price. You do not talk to the customer and nothing you write is read out loud. You advise Aria.

Your job is to protect margin while keeping the deal alive. You are commercial, not generous: a discount is the last lever you reach for, never the first.

What you are working with:
- Aria can say yes to {policy.aria_max_discount_pct:g}% on her own, instantly.
- You can sign up to {policy.desk_max_discount_pct:g}%, and only ever in exchange for something.
- Above {policy.desk_max_discount_pct:g}% a human sales manager has to approve it. Recommend that only when the deal genuinely turns on it.
- Below {policy.walk_away_discount_pct:g}% off list there is no deal at all. Never recommend past it.

Levers that cost nothing and should carry most of your answers:
- Trade-in credit against the fleet they are replacing (lowers total outlay, leaves unit price intact)
- {policy.financing_months}-month financing, when the blocker is cash flow rather than total cost
- Model mix: the cheaper model for general staff, the premium one only for the roles that need it
- Bundled value already included - support, MDM, onboarding, warranty - that a competing quote probably excludes
- Three-year total cost rather than day-one price

Every discount above {policy.commitment_required_above_pct:g}% must be paid for. Ask for at least one of: a firmer device count, a decision date, a {policy.financing_months}-month term, a single purchase order, or a reference/case study.

Concessions shrink. If Aria has already given ground this call, your next move is smaller than the last one, never larger.

Respond with ONLY a JSON object, no prose around it, with exactly these keys:
"recommended_discount_pct": number - the negotiated discount off list you advise, on top of automatic volume pricing. 0 is a valid and often correct answer.
"concessions": array of objects, each {{"kind": one of "discount"|"trade_in"|"financing"|"model_mix"|"bundle"|"term", "detail": one short sentence Aria can say, "value_usd": rough customer-side value as a number, 0 if unknown}}
"commitments": array of objects, each {{"kind": one of "device_count_floor"|"decision_by"|"term_24_month"|"case_study"|"single_po"|"trade_in_fleet", "detail": what Aria should ask for, in one short sentence}}
"rationale": one sentence, for the internal record, on why this is the right shape
"read": one sentence on what you think is ACTUALLY blocking this deal - the total number, the unit price, the timing of the spend, or a competing quote"""


def _build_prompt(
    *,
    customer_ask: str,
    requested_pct: float | None,
    list_total: float,
    units: int,
    tier_name: str,
    volume_discount_pct: float,
    already_granted: float,
    round_number: int,
    competitor_quote: str | None,
    qualification: str,
    objections: str,
) -> str:
    lines = [
        f"Customer just said: {customer_ask!r}",
        f"Fleet: {units} devices. List total ${list_total:,.0f}. "
        f"They already earn {tier_name} volume pricing at {volume_discount_pct:g}% off, automatically.",
        f"Negotiation round: {round_number}. Already conceded on this call: {already_granted:g}%.",
    ]
    if requested_pct:
        lines.append(f"Their ask works out to roughly {requested_pct:g}% off list.")
    if competitor_quote:
        lines.append(f"Competing quote they mentioned: {competitor_quote}")
    if qualification:
        lines.append(f"What we know about them: {qualification}")
    if objections:
        lines.append(f"Objections raised so far: {objections}")
    return "\n".join(lines)


def heuristic_proposal(
    *,
    requested_pct: float | None,
    already_granted: float,
    policy: DealPolicy = DEFAULT_POLICY,
) -> DeskProposal:
    """Deterministic fallback, used when the desk call fails or comes back
    unparseable - and directly by tests, which have no business making a
    network call to find out what the ladder does.

    Shaped like a cautious desk: the small ask is granted outright, anything
    larger is met at the desk cap with commitments attached and the free
    levers offered alongside.
    """
    asked = max(0.0, float(requested_pct or 0.0))

    if asked <= policy.aria_max_discount_pct:
        return DeskProposal(
            recommended_discount_pct=max(asked, already_granted),
            rationale="Inside what Aria can approve on her own; no commitment needed.",
            read="Testing whether there is any give at all.",
        )

    return DeskProposal(
        recommended_discount_pct=min(asked, policy.desk_max_discount_pct),
        concessions=[
            Concession(
                kind="trade_in",
                detail="Trade-in credit against the fleet they are replacing, which lowers the total without touching unit price.",
            ),
            Concession(
                kind="financing",
                detail=f"{policy.financing_months}-month financing through Apple Financial Services if the blocker is cash flow rather than total cost.",
            ),
        ],
        commitments=[
            Commitment(
                kind="device_count_floor",
                detail="Confirm the device count they are committing to.",
            ),
            Commitment(kind="decision_by", detail="Agree a date they will decide by."),
        ],
        rationale="Met at the desk ceiling with the free levers attached and a commitment asked in return.",
        read="Pushing on the total number.",
    )


def consult(
    *,
    customer_ask: str,
    requested_pct: float | None,
    list_total: float,
    units: int,
    tier_name: str,
    volume_discount_pct: float,
    already_granted: float,
    round_number: int,
    competitor_quote: str | None = None,
    qualification: str = "",
    objections: str = "",
    client: DeskClient | None = None,
    policy: DealPolicy = DEFAULT_POLICY,
) -> DeskProposal:
    """Ask layer 2 what to do. Never raises: a desk that cannot answer falls
    back to the heuristic, because the customer is mid-sentence waiting."""
    active = client or LLMDeskClient()
    prompt = _build_prompt(
        customer_ask=customer_ask,
        requested_pct=requested_pct,
        list_total=list_total,
        units=units,
        tier_name=tier_name,
        volume_discount_pct=volume_discount_pct,
        already_granted=already_granted,
        round_number=round_number,
        competitor_quote=competitor_quote,
        qualification=qualification,
        objections=objections,
    )

    try:
        raw = active.complete(system=_system_prompt(policy), prompt=prompt)
        return DeskProposal(**json.loads(_strip_fence(raw)))
    except Exception as exc:
        logger.warning("deal desk unavailable (%s); falling back to policy defaults", exc)
        return heuristic_proposal(
            requested_pct=requested_pct, already_granted=already_granted, policy=policy
        )


def _strip_fence(raw: str) -> str:
    """Some models wrap JSON in a markdown fence however firmly they are told
    not to. Cheaper to tolerate than to re-prompt mid-call."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end != -1 else text
