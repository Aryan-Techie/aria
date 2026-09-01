"""Every call ends with a human being told what happened.

The claim under test is narrower and more useful than "it writes a summary":
the factual half is read off the records the tools wrote, so it cannot contain
something nobody said, and it survives a summariser that fails entirely.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.crm import service as crm_service
from app.handoff import builder, delivery, service as handoff_service
from app.handoff.models import CallSummary
from app.main import app
from app.memory.schema import Objection
from app.metrics import savings
from app.sessions.models import SessionState
from app.sessions.store import session_store


class StubSummarizer:
    def __init__(self, payload: dict | str):
        self.payload = payload
        self.prompts: list[str] = []

    def complete(self, *, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class BrokenSummarizer:
    def complete(self, *, system: str, prompt: str) -> str:
        raise RuntimeError("no model configured")


@pytest.fixture
def finished_call():
    session = SessionState(session_id="sess-wrapup")
    session.created_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    session.ended_at = datetime.now(timezone.utc)
    session.left_brain.company = "Northwind Logistics"
    session.left_brain.user_count = 60
    session.left_brain.timeline = "end of October"
    session.outcome = "meeting_booked"
    session.booking_id = "booking-1"
    session.tool_calls = ["crm_upsert_lead", "crm_upsert_lead", "search_pricing_rag"]
    crm_service.upsert_lead(session.session_id, company="Northwind Logistics", name="Priya")
    session_store.save(session)
    return session


def test_the_facts_come_off_the_record_not_the_transcript(finished_call):
    summary = builder.build(finished_call, client=StubSummarizer({"headline": "x", "recommended_action": "y"}))
    assert "60 devices" in summary.facts
    assert "timeline end of October" in summary.facts
    assert summary.company == "Northwind Logistics"
    assert summary.contact == "Priya"


def test_what_was_already_promised_is_the_section_a_rep_cannot_miss(finished_call, monkeypatch):
    """Walking into a call not knowing what was already offered is how a deal
    gets re-negotiated from a worse position."""
    from app.deal import desk
    from app.deal.desk import DeskProposal
    from app.deal.models import Commitment
    from app.tools import executor

    real_consult = desk.consult
    monkeypatch.setattr(
        desk,
        "consult",
        lambda **kwargs: real_consult(
            **{
                **kwargs,
                "client": type(
                    "S",
                    (),
                    {
                        "complete": lambda self, *, system, prompt: json.dumps(
                            DeskProposal(
                                recommended_discount_pct=5.0,
                                commitments=[
                                    Commitment(kind="decision_by", detail="Decide by the 15th.")
                                ],
                            ).model_dump()
                        )
                    },
                )(),
            }
        ),
    )
    executor.dispatch("negotiate_deal", {"customer_ask": "can you do better?"}, finished_call)

    summary = builder.build(finished_call, client=BrokenSummarizer())
    assert any("5% off list was offered and stands" in line for line in summary.agreed)
    assert any("Quoted:" in line for line in summary.agreed)
    assert any("Decide by the 15th." in line for line in summary.owed)


def test_unresolved_objections_are_flagged_as_risk(finished_call):
    finished_call.right_brain.objections.append(
        Objection(topic="pricing", raised_text="more than our Windows laptops", resolved=False)
    )
    finished_call.right_brain.sentiment = "skeptical"
    summary = builder.build(finished_call, client=BrokenSummarizer())
    assert any("Unresolved pricing objection" in r for r in summary.risks)
    assert any("skeptical" in r for r in summary.risks)


def test_a_dead_summariser_still_produces_a_usable_wrap_up(finished_call):
    summary = builder.build(finished_call, client=BrokenSummarizer())
    assert summary.headline
    assert summary.recommended_action
    assert "Northwind Logistics" in summary.headline


def test_an_escalated_call_is_the_one_marked_urgent():
    session = SessionState(session_id="sess-escalated")
    session.ended_at = session.created_at
    session.status = "escalated"
    session.outcome = "escalated"
    summary = builder.build(session, client=BrokenSummarizer())
    assert summary.urgency == "now"
    assert "waiting on a person" in summary.headline


def test_the_model_only_writes_the_two_sentences(finished_call):
    stub = StubSummarizer(
        {
            "headline": "Northwind want 60 Macs by October and booked a demo.",
            "recommended_action": "Send the trade-in valuation before Thursday.",
            "urgency": "today",
        }
    )
    summary = builder.build(finished_call, client=stub)
    assert summary.headline.startswith("Northwind want 60")
    assert summary.urgency == "today"
    # ...and it is handed the structured record, not a transcript to re-read.
    # A summariser given raw turns invents a detail nobody said, and a rep
    # opening a call with an invented detail is worse off than one with a
    # thin summary.
    prompt = stub.prompts[0]
    assert "Outcome: meeting_booked" in prompt
    assert [line.split(":")[0] for line in prompt.splitlines()] == [
        "Company",
        "Contact",
        "Outcome",
        "What they need",
        "What was agreed",
        "What we owe them",
        "Risks",
        "Call length",
    ]


def test_a_nonsense_urgency_falls_back_rather_than_being_stored(finished_call):
    stub = StubSummarizer({"headline": "h", "recommended_action": "a", "urgency": "immediately"})
    summary = builder.build(finished_call, client=stub)
    assert summary.urgency in ("now", "today", "this_week", "none")


def test_the_crm_always_gets_it_even_with_nothing_configured(finished_call):
    summary = builder.build(finished_call, client=BrokenSummarizer())
    delivered = delivery.deliver(summary)
    assert delivered["crm"] is True
    assert delivered["slack"] is False and delivered["email"] is False
    notes = crm_service.get_lead(finished_call.session_id).notes
    assert any("Call wrap-up" in note for note in notes)


def test_slack_failure_does_not_cost_the_crm_note(finished_call, monkeypatch):
    import httpx

    def explode(*args, **kwargs):
        raise httpx.ConnectError("slack is down")

    monkeypatch.setattr(httpx, "post", explode)
    summary = builder.build(finished_call, client=BrokenSummarizer())
    delivered = delivery.deliver(summary, settings=type("S", (), {"slack_webhook_url": "https://hooks.example/x", "email_enabled": False, "rep_summary_email": ""})())
    assert delivered["slack"] is False
    assert delivered["crm"] is True


def test_the_wrap_up_is_readable_over_http(finished_call):
    handoff_service.on_call_end(finished_call)
    response = TestClient(app).get(f"/api/summaries/{finished_call.session_id}")
    assert response.status_code == 200
    assert response.json()["outcome"] == "meeting_booked"
    assert TestClient(app).get("/api/summaries/nope").status_code == 404


def test_as_text_is_one_account_of_the_call_for_all_three_routes():
    summary = CallSummary(
        session_id="s",
        company="Acme",
        outcome="qualified",
        headline="They need 40 iPads.",
        recommended_action="Call them today.",
        facts=["40 devices"],
        agreed=["5% offered"],
        duration_seconds=125,
        turn_count=14,
    )
    text = summary.as_text()
    assert "Acme - qualified" in text
    assert "They need 40 iPads." in text
    assert "- 40 devices" in text
    assert "2m 5s" in text


def test_repeated_data_entry_is_counted_once_but_lookups_are_not():
    """Five upserts as the customer corrects themselves is one lead record,
    not five lots of typing."""
    once = savings.admin_minutes(["crm_upsert_lead"])
    five_times = savings.admin_minutes(["crm_upsert_lead"] * 5)
    assert once == five_times

    lookups = savings.admin_minutes(["search_pricing_rag"] * 3)
    assert lookups == savings.BASELINE_MINUTES["search_pricing_rag"] * 3


def test_an_escalation_saves_no_human_time():
    """Counting a handoff as a saving is exactly how these numbers become a lie."""
    assert savings.admin_minutes(["escalate_to_human"]) == 0.0


def test_talk_time_and_paperwork_are_reported_apart():
    assert savings.agent_minutes(660) == 11.0
    assert savings.total_minutes(["crm_upsert_lead"], 660) == 14.0
