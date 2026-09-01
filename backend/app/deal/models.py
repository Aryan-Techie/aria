"""The shapes a negotiation is made of: a priced quote, one round of offer,
and the running state across the whole call.

Every one of these is written by code, never parsed out of what the model
said. That is the point of the split: the second-layer deal desk agent
*proposes* in prose and loose numbers, and these objects are what survives
after engine.authorise() has clamped that proposal against policy.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# Which layer said yes. The ladder, top to bottom:
#   aria      - layer 1, live on the call, small gives, instant
#   deal_desk - layer 2, a separate agent with its own prompt and its own
#               model call, reasoning about margin rather than conversation
#   human     - layer 3, a person, reached only when the ask is past what
#               layer 2 is allowed to sign
AuthorityLevel = Literal["aria", "deal_desk", "human"]

ConcessionKind = Literal["discount", "trade_in", "financing", "model_mix", "bundle", "term"]
CommitmentKind = Literal[
    "device_count_floor", "decision_by", "term_24_month", "case_study", "single_po", "trade_in_fleet"
]


class DeviceLine(BaseModel):
    model_key: str
    label: str
    quantity: int
    list_unit_price: float


class Concession(BaseModel):
    """Something given. `discount_pct` is only meaningful on kind="discount";
    every other lever moves total outlay without touching unit price, which is
    why they are free of the authority ladder entirely."""

    kind: ConcessionKind
    detail: str
    discount_pct: float = 0.0
    value_usd: float = 0.0


class Commitment(BaseModel):
    """What we asked for in return. A concession logged without one of these
    is the thing a rep gets coached about, so the engine refuses to authorise
    a meaningful discount that has none attached."""

    kind: CommitmentKind
    detail: str


class Quote(BaseModel):
    units: int
    lines: list[DeviceLine] = Field(default_factory=list)
    list_unit_price: float = 0.0  # blended across the mix
    list_total: float = 0.0

    tier_name: str = "Starter"
    volume_discount_pct: float = 0.0
    negotiated_discount_pct: float = 0.0
    trade_in_credit: float = 0.0

    effective_unit_price: float = 0.0
    effective_total: float = 0.0
    total_savings: float = 0.0
    term_months: int = 0

    @property
    def total_discount_pct(self) -> float:
        return round(self.volume_discount_pct + self.negotiated_discount_pct, 2)


class Offer(BaseModel):
    """One round of the negotiation, as it was actually authorised.

    `clamped` and `clamp_reason` are kept even when nothing was cut, because
    the interesting audit question is not "what did she offer" but "what did
    the desk want to offer, and what stopped it".
    """

    round: int
    customer_ask: str
    requested_discount_pct: float | None = None

    quote: Quote
    granted_discount_pct: float = 0.0
    concessions: list[Concession] = Field(default_factory=list)
    commitments: list[Commitment] = Field(default_factory=list)

    authorised_by: AuthorityLevel = "aria"
    requires_human: bool = False
    clamped: bool = False
    clamp_reason: str | None = None
    declined: bool = False

    rationale: str = ""
    price_summary: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NegotiationState(BaseModel):
    """Carried on the session for the whole call.

    `human_approved_pct` is the write-back from a real person clicking approve
    while the call is still running - the next system prompt renders it, so
    she can offer it in her very next sentence.
    """

    rounds: list[Offer] = Field(default_factory=list)
    granted_discount_pct: float = 0.0
    pending_human_approval: bool = False
    human_approved_pct: float | None = None
    human_approved_by: str | None = None
    approval_escalation_id: str | None = None

    @property
    def round_count(self) -> int:
        return len(self.rounds)

    @property
    def last_offer(self) -> Offer | None:
        return self.rounds[-1] if self.rounds else None
