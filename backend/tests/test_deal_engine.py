"""The engine is the part that has to hold when the model does not.

Every test here is a claim about what a bad, adversarial, or simply
enthusiastic generation cannot do: give away more than the desk may sign,
move faster than the pacing allows, give ground for nothing, or cross the
walk-away floor.
"""
from app.deal import engine
from app.deal.models import Commitment
from app.deal.policy import DEFAULT_POLICY, normalise_model


def test_volume_tier_bands_match_the_published_price_list():
    assert engine.volume_tier(10).name == "Starter"
    assert engine.volume_tier(20).name == "Growth"
    assert engine.volume_tier(99).name == "Growth"
    assert engine.volume_tier(100).name == "Enterprise"


def test_quote_prices_a_bare_device_count_as_macbook_airs():
    quote = engine.build_quote(units=50)
    assert quote.units == 50
    assert quote.list_total == 50 * 999
    assert quote.volume_discount_pct == 5.0
    assert quote.effective_total == round(50 * 999 * 0.95, 2)


def test_quote_prices_a_mixed_fleet_line_by_line():
    quote = engine.build_quote(
        units=0,
        device_mix=[
            {"model": "MacBook Pro (M4)", "quantity": 20},
            {"model": "iPhone 16", "quantity": 80},
        ],
    )
    assert quote.units == 100
    assert quote.list_total == 20 * 1599 + 80 * 799
    # 100 units crosses into Enterprise even though neither line does alone.
    assert quote.tier_name == "Enterprise"


def test_device_mix_overrides_a_contradictory_unit_count():
    """The model spelled the mix out on purpose; the bare count is the looser
    of the two figures."""
    quote = engine.build_quote(units=5, device_mix=[{"model": "ipad", "quantity": 40}])
    assert quote.units == 40


def test_trade_in_credit_lowers_the_total_without_touching_unit_price():
    plain = engine.build_quote(units=30)
    traded = engine.build_quote(units=30, trade_in_devices=30)
    assert traded.effective_unit_price == plain.effective_unit_price
    assert traded.effective_total < plain.effective_total


def test_trade_in_is_capped_at_the_size_of_the_fleet_being_bought():
    """A customer with 500 old laptops replacing 10 does not get 500 credits."""
    modest = engine.build_quote(units=10, trade_in_devices=10)
    absurd = engine.build_quote(units=10, trade_in_devices=500)
    assert absurd.trade_in_credit == modest.trade_in_credit


def test_discount_for_target_converts_a_target_total_into_a_negotiated_ask():
    quote = engine.build_quote(units=100)
    # Enterprise volume already takes 10% off, so a target 20% under list is
    # asking for 10 points of *negotiated* discount, not 20.
    asked = engine.discount_for_target(quote, quote.list_total * 0.80)
    assert asked == 10.0


def test_walk_away_floor_is_enforced_in_code_not_by_the_prompt():
    granted, level, clamped, reason, requires_human = engine.authorise(
        requested_pct=40,
        round_number=1,
        already_granted=0,
        has_commitment=True,
    )
    assert granted == 0
    assert clamped is True
    assert requires_human is False, "below the floor there is no deal for a human to approve"
    assert "floor" in reason


def test_above_the_desk_ceiling_holds_the_offer_and_asks_a_human():
    granted, level, clamped, reason, requires_human = engine.authorise(
        requested_pct=14,
        round_number=3,
        already_granted=9.0,
        has_commitment=True,
    )
    assert requires_human is True
    assert granted <= DEFAULT_POLICY.desk_max_discount_pct
    assert level in ("deal_desk", "aria")


def test_a_discount_with_nothing_asked_in_return_is_cut_back():
    granted, _level, clamped, reason, _human = engine.authorise(
        requested_pct=9,
        round_number=1,
        already_granted=0,
        has_commitment=False,
    )
    assert granted == DEFAULT_POLICY.commitment_required_above_pct
    assert clamped is True
    assert "in return" in reason


def test_small_gives_need_no_commitment():
    granted, level, clamped, _reason, _human = engine.authorise(
        requested_pct=2,
        round_number=1,
        already_granted=0,
        has_commitment=False,
    )
    assert granted == 2
    assert level == "aria"
    assert clamped is False


def test_concessions_shrink_round_over_round():
    """A negotiator who moves five, then five, then five has taught the buyer
    that waiting is free."""
    granted = 0.0
    steps = []
    for round_number in range(1, 5):
        granted, _level, _clamped, _reason, _human = engine.authorise(
            requested_pct=10,
            round_number=round_number,
            already_granted=granted,
            has_commitment=True,
        )
        steps.append(granted)
    increments = [b - a for a, b in zip(steps, steps[1:])]
    assert all(later <= earlier for earlier, later in zip(increments, increments[1:]))
    assert steps[-1] <= DEFAULT_POLICY.desk_max_discount_pct


def test_a_discount_is_never_clawed_back():
    granted, _level, _clamped, _reason, _human = engine.authorise(
        requested_pct=1,
        round_number=2,
        already_granted=8.0,
        has_commitment=True,
    )
    assert granted == 8.0


def test_a_human_approval_outranks_the_desk_ceiling():
    granted, level, _clamped, _reason, requires_human = engine.authorise(
        requested_pct=15,
        round_number=2,
        already_granted=10.0,
        has_commitment=True,
        human_approved_pct=14.0,
    )
    assert granted == 14.0
    assert level == "human"
    assert requires_human is False


def test_a_human_approval_is_still_a_ceiling():
    granted, _level, clamped, reason, _human = engine.authorise(
        requested_pct=17,
        round_number=3,
        already_granted=10.0,
        has_commitment=True,
        human_approved_pct=12.0,
    )
    assert granted == 12.0
    assert clamped is True
    assert "approved" in reason


def test_offer_restates_the_discount_from_the_granted_figure():
    """The number the desk asked for must not survive anywhere on the record."""
    offer = engine.build_offer(
        round_number=1,
        customer_ask="we need twenty percent",
        requested_pct=20.0,
        granted_pct=6.0,
        authorised_by="deal_desk",
        clamped=True,
        clamp_reason="paced",
        requires_human=False,
        concessions=[],
        commitments=[Commitment(kind="decision_by", detail="Decide by the 15th")],
        rationale="",
        units=60,
        device_mix=None,
        trade_in_devices=0,
        term_months=0,
    )
    assert offer.quote.negotiated_discount_pct == 6.0
    assert offer.concessions[0].discount_pct == 6.0
    assert "6%" in offer.concessions[0].detail
    assert "20" not in offer.price_summary.replace("2026", "")


def test_price_summary_carries_the_finished_numbers():
    quote = engine.build_quote(units=50, negotiated_discount_pct=5, term_months=24)
    summary = engine.price_summary(quote)
    assert "MacBook Air" in summary
    assert "$" in summary
    assert "a month" in summary


def test_model_names_survive_speech_recognition():
    assert normalise_model("mac book pro") == "macbook_pro"
    assert normalise_model("MacBook Air M3") == "macbook_air"
    assert normalise_model("iPhone 16 Pro") == "iphone_pro"
    assert normalise_model("iphone") == "iphone"
    assert normalise_model("iPads") == "ipad"
    assert normalise_model("something nobody sells") == "macbook_air"
