"""Deterministic pricing and the authority ladder.

Two jobs, both of which exist because a language model must not be the last
thing standing between a customer and the margin:

1. `build_quote` does every piece of arithmetic. The model never multiplies a
   unit price by a device count, for exactly the reason it never works out a
   weekday any more (see calendar/labels.py) - it is confidently wrong often
   enough to matter, and a wrong number said out loud to a buyer is worse than
   a wrong weekday.

2. `authorise` is the clamp. The layer-2 deal desk agent proposes a discount
   in prose; this decides what is actually granted, which layer is allowed to
   sign it, and what has to be taken back in return. A proposal of 40% does
   not become a 40% offer - it becomes a capped offer plus a flag saying a
   human has to sign, and the customer never hears the number the model
   invented.
"""
from __future__ import annotations

from app.deal.models import (
    AuthorityLevel,
    Commitment,
    Concession,
    DeviceLine,
    Offer,
    Quote,
)
from app.deal.policy import (
    DEFAULT_POLICY,
    DEFAULT_TRADE_IN_CREDIT,
    DEVICE_LABELS,
    DEVICE_LIST_PRICES,
    TRADE_IN_CREDIT,
    DealPolicy,
    normalise_model,
)

DEFAULT_MODEL_KEY = "macbook_air"


def volume_tier(units: int, policy: DealPolicy = DEFAULT_POLICY):
    """The band this fleet size earns on its own. Never a concession - it is
    published pricing, and presenting it as a favour is the fastest way to
    lose a buyer who has already read the price list."""
    tier = policy.tiers_by_size[0]
    for candidate in policy.tiers_by_size:
        if units >= candidate.min_units:
            tier = candidate
    return tier


def _money(value: float) -> float:
    return round(value + 1e-9, 2)


def build_quote(
    *,
    units: int,
    device_mix: list[dict] | None = None,
    trade_in_devices: int = 0,
    term_months: int = 0,
    negotiated_discount_pct: float = 0.0,
    policy: DealPolicy = DEFAULT_POLICY,
) -> Quote:
    """Prices a fleet. `device_mix` is [{"model": ..., "quantity": n}, ...];
    with none given the whole fleet is priced as MacBook Airs, the device this
    deck is quoted around.

    A mix whose quantities do not add up to `units` is trusted over `units` -
    the model spelled the mix out on purpose, and the bare count is the looser
    of the two figures.
    """
    lines: list[DeviceLine] = []
    for entry in device_mix or []:
        quantity = int(entry.get("quantity") or 0)
        if quantity <= 0:
            continue
        key = normalise_model(str(entry.get("model", "")))
        lines.append(
            DeviceLine(
                model_key=key,
                label=DEVICE_LABELS.get(key, key),
                quantity=quantity,
                list_unit_price=float(
                    DEVICE_LIST_PRICES.get(key, DEVICE_LIST_PRICES[DEFAULT_MODEL_KEY])
                ),
            )
        )

    if not lines:
        units = max(1, int(units or 1))
        key = DEFAULT_MODEL_KEY
        lines = [
            DeviceLine(
                model_key=key,
                label=DEVICE_LABELS[key],
                quantity=units,
                list_unit_price=float(DEVICE_LIST_PRICES[key]),
            )
        ]

    total_units = sum(line.quantity for line in lines)
    list_total = sum(line.quantity * line.list_unit_price for line in lines)
    tier = volume_tier(total_units, policy)

    discount_fraction = (tier.discount_pct + negotiated_discount_pct) / 100.0
    total_before_credit = list_total * (1.0 - discount_fraction)

    credit = 0.0
    if policy.trade_in_enabled and trade_in_devices > 0:
        # Credited at the rate of the largest line in the mix - the devices
        # they are most likely actually replacing - rather than a blended
        # average, which would quietly overpay for a fleet of iPads.
        largest = max(lines, key=lambda line: line.quantity)
        per_device = TRADE_IN_CREDIT.get(largest.model_key, DEFAULT_TRADE_IN_CREDIT)
        credit = float(min(trade_in_devices, total_units) * per_device)

    effective_total = max(0.0, total_before_credit - credit)

    return Quote(
        units=total_units,
        lines=lines,
        list_unit_price=_money(list_total / total_units if total_units else 0.0),
        list_total=_money(list_total),
        tier_name=tier.name,
        volume_discount_pct=tier.discount_pct,
        negotiated_discount_pct=round(negotiated_discount_pct, 2),
        trade_in_credit=_money(credit),
        effective_unit_price=_money(total_before_credit / total_units if total_units else 0.0),
        effective_total=_money(effective_total),
        total_savings=_money(list_total - effective_total),
        term_months=term_months,
    )


def discount_for_target(quote: Quote, target_total: float) -> float:
    """The negotiated discount that would land a list-priced fleet on
    `target_total` - i.e. what "we need to be under ninety grand" is actually
    asking for, expressed in the only unit the ladder can reason about."""
    if quote.list_total <= 0 or target_total <= 0:
        return 0.0
    implied = (1.0 - target_total / quote.list_total) * 100.0
    return round(max(0.0, implied - quote.volume_discount_pct), 2)


def authority_for(pct: float, policy: DealPolicy = DEFAULT_POLICY) -> AuthorityLevel:
    if pct <= policy.aria_max_discount_pct:
        return "aria"
    if pct <= policy.desk_max_discount_pct:
        return "deal_desk"
    return "human"


def round_ceiling(
    round_number: int, already_granted: float, policy: DealPolicy = DEFAULT_POLICY
) -> float:
    """How far this round may move, before the caps apply.

    Diminishing steps, so the offer converges visibly instead of sliding at a
    constant rate. Round 1 opens at `first_step_pct` from zero; every round
    after adds the previous step scaled by `concession_decay`. A negotiator
    who moves five, then five, then five has taught the buyer that waiting is
    free.
    """
    step = policy.first_step_pct * (policy.concession_decay ** max(0, round_number - 1))
    return round(already_granted + step, 2)


def authorise(
    *,
    requested_pct: float,
    round_number: int,
    already_granted: float,
    has_commitment: bool,
    human_approved_pct: float | None = None,
    policy: DealPolicy = DEFAULT_POLICY,
) -> tuple[float, AuthorityLevel, bool, str | None, bool]:
    """Decide what is actually granted.

    Returns (granted_pct, authorised_by, clamped, clamp_reason, requires_human).

    The rules, in the order they bite:
      * a discount is never clawed back - a customer who heard 8% never hears
        7% later, whatever the desk proposes on a later round
      * pacing caps how far a single round may move
      * the desk cap is the ceiling any agent can sign; past it the offer is
        held at the cap and a human is asked, rather than the customer being
        told a number nobody has approved
      * past the walk-away floor the answer is no, and it is a *deterministic*
        no - the desk is not consulted, because this is the one number the
        business cannot let a generation talk it past
      * a meaningful discount with nothing asked in return is cut back to what
        needs nothing in return
    """
    requested = max(0.0, round(float(requested_pct or 0.0), 2))
    granted = requested
    clamped = False
    reason: str | None = None
    requires_human = False

    if human_approved_pct is not None:
        # A person has already signed off on this call. Their number is the
        # ceiling now, and it outranks the desk cap in both directions.
        granted = max(already_granted, min(requested, human_approved_pct))
        if requested > human_approved_pct:
            clamped = True
            reason = f"held to the {human_approved_pct:g}% a human approved on this call"
        return round(granted, 2), "human", clamped, reason, False

    if requested > policy.walk_away_discount_pct:
        # Not an escalation. Below the floor there is no deal for a human to
        # approve, so promoting it would only cost them a round trip to say no.
        held = max(already_granted, 0.0)
        return (
            round(held, 2),
            authority_for(held, policy),
            True,
            (
                f"asked for {requested:g}%, past the {policy.walk_away_discount_pct:g}% "
                "floor this deck can be sold at"
            ),
            False,
        )

    if requested > policy.desk_max_discount_pct:
        requires_human = True
        granted = policy.desk_max_discount_pct
        clamped = True
        reason = (
            f"{requested:g}% is above what the deal desk can sign "
            f"({policy.desk_max_discount_pct:g}%), so it needs a human"
        )

    ceiling = round_ceiling(round_number, already_granted, policy)
    if granted > ceiling:
        granted = ceiling
        clamped = True
        reason = reason or f"paced to {ceiling:g}% for round {round_number}"

    if granted > policy.commitment_required_above_pct and not has_commitment:
        granted = policy.commitment_required_above_pct
        clamped = True
        reason = "nothing was asked for in return, so it is held to what needs no commitment"

    granted = min(max(granted, already_granted), policy.desk_max_discount_pct)
    return round(granted, 2), authority_for(granted, policy), clamped, reason, requires_human


def _fmt(amount: float) -> str:
    return f"${amount:,.0f}"


def price_summary(quote: Quote) -> str:
    """The finished sentence, so the model reads a number out rather than
    working one out. Same reasoning as the pre-formatted calendar slot labels:
    what gets handed over is what gets said."""
    mix = ", ".join(f"{line.quantity} x {line.label}" for line in quote.lines)
    parts = [
        f"{mix}. List {_fmt(quote.list_total)} ({_fmt(quote.list_unit_price)} a device).",
        f"{quote.tier_name} volume pricing takes {quote.volume_discount_pct:g}% off",
    ]
    if quote.negotiated_discount_pct:
        parts.append(f"plus {quote.negotiated_discount_pct:g}% negotiated")
    parts.append(
        f"- that is {_fmt(quote.effective_unit_price)} a device, "
        f"{_fmt(quote.effective_total)} for the fleet"
    )
    if quote.trade_in_credit:
        parts.append(f"after {_fmt(quote.trade_in_credit)} of trade-in credit")
    parts.append(f". Total saving against list: {_fmt(quote.total_savings)}.")
    if quote.term_months:
        monthly = quote.effective_total / quote.term_months
        parts.append(f"Over {quote.term_months} months that is about {_fmt(monthly)} a month.")
    return " ".join(parts).replace(" .", ".")


def build_offer(
    *,
    round_number: int,
    customer_ask: str,
    requested_pct: float | None,
    granted_pct: float,
    authorised_by: AuthorityLevel,
    clamped: bool,
    clamp_reason: str | None,
    requires_human: bool,
    concessions: list[Concession],
    commitments: list[Commitment],
    rationale: str,
    units: int,
    device_mix: list[dict] | None,
    trade_in_devices: int,
    term_months: int,
    policy: DealPolicy = DEFAULT_POLICY,
) -> Offer:
    """Assembles the authorised round: re-prices at the granted discount, and
    restates the discount concession from the granted figure rather than the
    proposed one, so nothing anywhere in the record still carries the number
    the desk asked for."""
    quote = build_quote(
        units=units,
        device_mix=device_mix,
        trade_in_devices=trade_in_devices,
        term_months=term_months,
        negotiated_discount_pct=granted_pct,
        policy=policy,
    )

    priced = [c for c in concessions if c.kind != "discount"]
    if granted_pct > 0:
        priced.insert(
            0,
            Concession(
                kind="discount",
                detail=f"{granted_pct:g}% off list, on top of {quote.tier_name} volume pricing",
                discount_pct=granted_pct,
                value_usd=_money(quote.list_total * granted_pct / 100.0),
            ),
        )

    return Offer(
        round=round_number,
        customer_ask=customer_ask,
        requested_discount_pct=requested_pct,
        quote=quote,
        granted_discount_pct=granted_pct,
        concessions=priced,
        commitments=commitments,
        authorised_by=authorised_by,
        requires_human=requires_human,
        clamped=clamped,
        clamp_reason=clamp_reason,
        declined=granted_pct <= 0 and not priced,
        rationale=rationale,
        price_summary=price_summary(quote),
    )
