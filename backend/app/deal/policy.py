"""The commercial envelope Aria negotiates inside - prices, tiers, and the
limit of what each layer is allowed to give away.

This is deliberately data, not prompt text. A discount the model merely
*believes* it is allowed to offer is a discount it can hallucinate its way
past; every number below is read by engine.py and enforced in code after the
model has spoken, so the worst a bad generation can do is get clamped.

The list prices and volume bands mirror app/rag/docs/pricing.json, which is
what she quotes from - a negotiation that starts from a different list price
than the one she just read out loud is worse than no negotiation at all.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# Model name (as the customer or the knowledge base says it) -> list price.
# Keys are matched loosely by normalise_model(), because ASR turns
# "MacBook Air M3" into anything from "macbook air" to "mac book air m three".
DEVICE_LIST_PRICES: dict[str, int] = {
    "macbook_air": 999,
    "macbook_pro": 1599,
    "iphone": 799,
    "iphone_pro": 999,
    "ipad": 349,
    "ipad_pro": 999,
}

DEVICE_LABELS: dict[str, str] = {
    "macbook_air": "MacBook Air (M3)",
    "macbook_pro": "MacBook Pro (M4)",
    "iphone": "iPhone 16",
    "iphone_pro": "iPhone 16 Pro",
    "ipad": "iPad (10th gen)",
    "ipad_pro": "iPad Pro (M4)",
}

# What a device of each class is worth as trade-in credit against the new
# fleet. Credit lowers total outlay without touching unit price, which is why
# it is the first lever to reach for when the objection is the total number.
TRADE_IN_CREDIT: dict[str, int] = {
    "macbook_air": 180,
    "macbook_pro": 260,
    "iphone": 120,
    "iphone_pro": 150,
    "ipad": 60,
    "ipad_pro": 140,
}
DEFAULT_TRADE_IN_CREDIT = 120

_MODEL_ALIASES: tuple[tuple[str, str], ...] = (
    ("macbook pro", "macbook_pro"),
    ("mac book pro", "macbook_pro"),
    ("macbook air", "macbook_air"),
    ("mac book air", "macbook_air"),
    ("macbook", "macbook_air"),
    ("mac book", "macbook_air"),
    ("mac", "macbook_air"),
    ("iphone pro", "iphone_pro"),
    ("iphone 16 pro", "iphone_pro"),
    ("iphone", "iphone"),
    ("ipad pro", "ipad_pro"),
    ("ipad", "ipad"),
    ("laptop", "macbook_air"),
    ("phone", "iphone"),
    ("tablet", "ipad"),
)


def normalise_model(raw: str) -> str:
    """Best-effort map from whatever the model passed to a catalogue key.

    Longest alias first, so "macbook pro" is not swallowed by "macbook".
    Anything unrecognised falls back to the MacBook Air, the cheapest laptop
    and the device this deck is quoted around - guessing high would inflate a
    quote the customer then hears out loud.
    """
    text = (raw or "").strip().lower().replace("-", " ")
    if text in DEVICE_LIST_PRICES:
        return text
    for alias, key in sorted(_MODEL_ALIASES, key=lambda pair: -len(pair[0])):
        if alias in text:
            return key
    return "macbook_air"


class VolumeTier(BaseModel):
    name: str
    min_units: int
    discount_pct: float


class DealPolicy(BaseModel):
    """Everything the deal desk is allowed to work with.

    Held as a model rather than module constants so a test can hand the engine
    a tighter or looser envelope without monkeypatching, and so a future
    per-account policy is a value change rather than a code change.
    """

    # Automatic, earned by size alone - not a concession and not negotiated.
    # Bands match pricing.json: 1-19 / 20-99 / 100+.
    volume_tiers: list[VolumeTier] = Field(
        default_factory=lambda: [
            VolumeTier(name="Starter", min_units=1, discount_pct=0.0),
            VolumeTier(name="Growth", min_units=20, discount_pct=5.0),
            VolumeTier(name="Enterprise", min_units=100, discount_pct=10.0),
        ]
    )

    # The authority ladder. Each layer may grant up to its own cap and no
    # further; crossing a cap is what promotes the decision to the next layer.
    #   aria      - what she can say yes to on her own, instantly
    #   deal_desk - the second-layer agent, and it must take something back
    #   human     - a real person signs off, and this is also the floor
    aria_max_discount_pct: float = 3.0
    desk_max_discount_pct: float = 10.0
    walk_away_discount_pct: float = 18.0

    # Above this, a concession has to buy something: a firmer device count, a
    # decision date, a term. Below it the give is small enough that asking for
    # something in return costs more goodwill than it earns.
    commitment_required_above_pct: float = 3.0

    # Concession pacing. A negotiator who moves 5, then 5, then 5 teaches the
    # other side that waiting is free. Each round's headroom is the previous
    # step scaled by `concession_decay`, so the offer visibly converges:
    # 5.0, +3.0, +1.8, +1.08 ... and the customer can feel the floor coming.
    first_step_pct: float = 5.0
    concession_decay: float = 0.6

    # Non-price levers, always available, never need approval.
    financing_months: int = 24
    trade_in_enabled: bool = True

    @property
    def tiers_by_size(self) -> list[VolumeTier]:
        return sorted(self.volume_tiers, key=lambda t: t.min_units)


DEFAULT_POLICY = DealPolicy()
