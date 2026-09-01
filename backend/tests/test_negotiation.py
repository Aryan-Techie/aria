"""The three layers, end to end, with a fake deal desk.

The desk is an LLM call in production; here it is a stub returning whatever
proposal a given test needs, which is the whole reason engine.authorise sits
between it and the customer. A desk that recommends 40% is not a hypothetical
- it is a generation away - so it is exactly what most of these tests feed in.
"""
import json

import pytest
from fastapi.testclient import TestClient

from app.crm import service as crm_service
from app.deal import desk
from app.deal.desk import DeskProposal
from app.deal.models import Commitment, Concession
from app.escalation.inbox import inbox
from app.main import app
from app.sessions.models import SessionState
from app.sessions.store import session_store
from app.tools import executor


class StubDesk:
    """A deal desk that proposes whatever the test says, and records what it
    was told about the call so the prompt-building can be asserted on."""

    def __init__(self, proposal: DeskProposal):
        self.proposal = proposal
        self.prompts: list[str] = []

    def complete(self, *, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.proposal.model_dump())


@pytest.fixture
def session():
    state = SessionState(session_id="sess-negotiation")
    state.left_brain.user_count = 60
    session_store.save(state)
    return state


def _consult_returning(proposal: DeskProposal, monkeypatch) -> StubDesk:
    stub = StubDesk(proposal)
    real_consult = desk.consult
    monkeypatch.setattr(
        desk, "consult", lambda **kwargs: real_consult(**{**kwargs, "client": stub})
    )
    return stub


def test_a_modest_ask_is_authorised_by_aria_alone(session, monkeypatch):
    _consult_returning(DeskProposal(recommended_discount_pct=2.0), monkeypatch)

    result = executor.dispatch(
        "negotiate_deal", {"customer_ask": "any movement on price?"}, session
    )

    assert result["granted_discount_pct"] == 2.0
    assert result["authorised_by"] == "aria"
    assert result["awaiting_human_approval"] is False


def test_the_desk_signs_a_larger_discount_but_only_against_a_commitment(session, monkeypatch):
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=5.0,
            concessions=[Concession(kind="trade_in", detail="Trade in the old fleet.")],
            commitments=[Commitment(kind="decision_by", detail="Decide by the 15th.")],
        ),
        monkeypatch,
    )

    result = executor.dispatch(
        "negotiate_deal", {"customer_ask": "Dell came in well under this"}, session
    )

    assert result["granted_discount_pct"] == 5.0
    assert result["authorised_by"] == "deal_desk"
    assert result["ask_for_in_return"] == ["Decide by the 15th."]


def test_a_runaway_desk_recommendation_never_reaches_the_customer(session, monkeypatch):
    """The failure this whole layer exists to make impossible: the desk
    proposes 40%, and what gets spoken is a capped number."""
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=40.0,
            commitments=[Commitment(kind="single_po", detail="One purchase order.")],
        ),
        monkeypatch,
    )

    result = executor.dispatch("negotiate_deal", {"customer_ask": "half price or no deal"}, session)

    assert result["granted_discount_pct"] == 0.0
    assert "40%" not in result["price_summary"]
    assert session.negotiation.last_offer.quote.negotiated_discount_pct == 0.0
    assert session.negotiation.last_offer.clamped is True
    assert "floor" in session.negotiation.last_offer.clamp_reason


def test_past_the_desk_ceiling_a_human_is_asked_without_ending_the_call(session, monkeypatch):
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=14.0,
            commitments=[Commitment(kind="case_study", detail="Agree to a case study.")],
        ),
        monkeypatch,
    )

    result = executor.dispatch(
        "negotiate_deal", {"customer_ask": "I need fifteen percent to sign this"}, session
    )

    assert result["awaiting_human_approval"] is True
    assert result["granted_discount_pct"] <= 10.0
    # The call is emphatically NOT handed over: a question about margin is not
    # a handoff, and the customer stays with Aria while a person answers it.
    assert session.status == "active"
    assert session.outcome is None

    record = inbox.all()[-1]
    assert record.kind == "deal_approval"
    assert record.trigger_source == "deal_approval"


def test_guidance_forbids_stating_an_unapproved_number_as_agreed(session, monkeypatch):
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=14.0,
            commitments=[Commitment(kind="single_po", detail="One PO.")],
        ),
        monkeypatch,
    )
    result = executor.dispatch("negotiate_deal", {"customer_ask": "fifteen percent"}, session)
    assert "manager" in result["guidance"]
    assert "do NOT" in result["guidance"] or "Do NOT" in result["guidance"]


def test_nothing_is_priced_before_a_device_count_exists():
    bare = SessionState(session_id="sess-no-count")
    result = executor.dispatch("negotiate_deal", {"customer_ask": "what's your best price?"}, bare)
    assert result["error"] == "no_device_count"
    assert "how many devices" in result["guidance"]


def test_every_round_is_written_to_the_crm_record(session, monkeypatch):
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=5.0,
            commitments=[Commitment(kind="decision_by", detail="Decide by Friday.")],
        ),
        monkeypatch,
    )

    executor.dispatch("negotiate_deal", {"customer_ask": "can you do better?"}, session)

    notes = crm_service.get_lead(session.session_id).notes
    assert any("granted 5%" in note and "deal_desk" in note for note in notes)
    assert any("asked in return" in note for note in notes)


def test_a_second_push_is_met_with_a_smaller_move(session, monkeypatch):
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=10.0,
            commitments=[Commitment(kind="decision_by", detail="Decide by Friday.")],
        ),
        monkeypatch,
    )

    first = executor.dispatch("negotiate_deal", {"customer_ask": "that's too much"}, session)
    second = executor.dispatch("negotiate_deal", {"customer_ask": "still too much"}, session)
    third = executor.dispatch("negotiate_deal", {"customer_ask": "come on"}, session)

    moves = [
        second["granted_discount_pct"] - first["granted_discount_pct"],
        third["granted_discount_pct"] - second["granted_discount_pct"],
    ]
    assert moves[1] < moves[0]
    assert third["granted_discount_pct"] <= 10.0


def test_the_desk_is_told_what_has_already_been_conceded(session, monkeypatch):
    stub = _consult_returning(
        DeskProposal(
            recommended_discount_pct=6.0,
            commitments=[Commitment(kind="single_po", detail="One PO.")],
        ),
        monkeypatch,
    )

    executor.dispatch("negotiate_deal", {"customer_ask": "discount?"}, session)
    executor.dispatch("negotiate_deal", {"customer_ask": "more?"}, session)

    assert "Already conceded on this call: 0%" in stub.prompts[0]
    # 6% was proposed, 5% was authorised (round-one pacing), and it is the
    # authorised figure the desk is told about on the next round - not the one
    # it asked for.
    assert "Already conceded on this call: 5%" in stub.prompts[1]
    assert "Negotiation round: 2" in stub.prompts[1]


def test_a_target_total_is_converted_into_the_ask_the_ladder_understands(session, monkeypatch):
    stub = _consult_returning(DeskProposal(recommended_discount_pct=0.0), monkeypatch)

    executor.dispatch(
        "negotiate_deal",
        {"customer_ask": "we need to land under fifty thousand", "target_total_price": 50000},
        session,
    )

    assert "% off list" in stub.prompts[0]


def test_a_desk_that_cannot_answer_falls_back_rather_than_failing_the_turn(session, monkeypatch):
    class BrokenDesk:
        def complete(self, *, system: str, prompt: str) -> str:
            raise TimeoutError("desk unreachable")

    real_consult = desk.consult
    monkeypatch.setattr(
        desk, "consult", lambda **kwargs: real_consult(**{**kwargs, "client": BrokenDesk()})
    )

    result = executor.dispatch(
        "negotiate_deal",
        {"customer_ask": "ten percent and we're done", "requested_discount_pct": 10},
        session,
    )

    assert "price_summary" in result
    assert result["granted_discount_pct"] > 0


def test_a_human_approval_reaches_the_live_call(session, monkeypatch):
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=14.0,
            commitments=[Commitment(kind="case_study", detail="Case study.")],
        ),
        monkeypatch,
    )
    executor.dispatch("negotiate_deal", {"customer_ask": "fifteen percent"}, session)
    escalation_id = session.negotiation.approval_escalation_id

    client = TestClient(app)
    response = client.post(
        f"/api/inbox/{escalation_id}/approve",
        json={"approved_pct": 13.0, "approved_by": "Priya (sales manager)"},
    )

    assert response.status_code == 200
    assert response.json()["applied_to_live_call"] is True

    live = session_store.get(session.session_id)
    assert live.negotiation.human_approved_pct == 13.0
    assert live.negotiation.pending_human_approval is False

    # And the next round can now actually offer it.
    _consult_returning(
        DeskProposal(
            recommended_discount_pct=13.0,
            commitments=[Commitment(kind="case_study", detail="Case study.")],
        ),
        monkeypatch,
    )
    result = executor.dispatch("negotiate_deal", {"customer_ask": "so where are we?"}, live)
    assert result["granted_discount_pct"] == 13.0
    assert result["authorised_by"] == "human"


def test_approving_a_plain_handoff_is_rejected(session):
    from app.escalation import service as escalation_service

    record, _ = escalation_service.escalate(
        session.session_id,
        "customer asked for a person",
        "llm",
        transcript=[],
        left_brain=session.left_brain,
        right_brain=session.right_brain,
        summarizer_client=None,
    )
    response = TestClient(app).post(
        f"/api/inbox/{record.id}/approve", json={"approved_pct": 12.0}
    )
    assert response.status_code == 400


def test_heuristic_proposal_stays_inside_the_desk_ceiling():
    proposal = desk.heuristic_proposal(requested_pct=25, already_granted=0)
    assert proposal.recommended_discount_pct <= 10.0
    assert proposal.commitments, "a fallback that gives ground for nothing is worse than none"


def test_the_system_prompt_restates_the_offer_that_actually_stands(session, monkeypatch):
    """Two turns later the tool result has scrolled out of the useful part of
    the history. Without this she re-opens the round from zero, or contradicts
    her own last offer."""
    from app.orchestrator import pipeline

    _consult_returning(
        DeskProposal(
            recommended_discount_pct=5.0,
            commitments=[Commitment(kind="decision_by", detail="Decide by Friday.")],
        ),
        monkeypatch,
    )
    executor.dispatch("negotiate_deal", {"customer_ask": "can you do better?"}, session)

    rendered = pipeline._render_call_state(session)
    assert "already offered 5%" in rendered
    assert "Decide by Friday." in rendered
    assert "never go below it" in rendered


def test_a_pending_approval_is_visible_to_the_next_turn(session, monkeypatch):
    from app.orchestrator import pipeline

    _consult_returning(
        DeskProposal(
            recommended_discount_pct=14.0,
            commitments=[Commitment(kind="case_study", detail="Case study.")],
        ),
        monkeypatch,
    )
    executor.dispatch("negotiate_deal", {"customer_ask": "fifteen percent"}, session)

    rendered = pipeline._render_call_state(session)
    assert "sales manager is being asked" in rendered
    assert "Do NOT state it as agreed" in rendered


def test_nothing_is_rendered_before_a_negotiation_starts():
    from app.orchestrator import pipeline

    assert pipeline._render_negotiation(SessionState(session_id="quiet")) == ""
