"""Layer 2's other seat: the specialist that stops a technical question from
becoming a handoff.

The claim being tested is not "it answers questions" - it is that it answers
only from the material, reports the boundary rather than rounding it down to
reassurance, and hands over cleanly when there genuinely is nothing to say.
"""
import json

import pytest

from app.escalation import triggers
from app.sessions.models import SessionState
from app.specialists import solutions
from app.specialists.solutions import SolutionsAnswer
from app.tools import executor


class StubEngineer:
    def __init__(self, answer: SolutionsAnswer):
        self.answer = answer
        self.prompts: list[str] = []

    def complete(self, *, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.answer.model_dump())


@pytest.fixture
def session():
    state = SessionState(session_id="sess-specialist")
    state.left_brain.company = "Northwind Logistics"
    return state


def _engineer_returning(answer: SolutionsAnswer, monkeypatch) -> StubEngineer:
    stub = StubEngineer(answer)
    real = solutions.consult
    monkeypatch.setattr(solutions, "consult", lambda **kw: real(**{**kw, "client": stub}))
    return stub


def test_the_open_questions_come_back_to_be_said_out_loud(session, monkeypatch):
    """A customer told precisely what still needs checking trusts you more
    than one told everything will be fine."""
    _engineer_returning(
        SolutionsAnswer(
            answer="Standard productivity software is covered.",
            confidence="medium",
            open_questions=["Whether their dispatch client has an Apple Silicon build"],
        ),
        monkeypatch,
    )

    result = executor.dispatch(
        "ask_solutions_engineer", {"question": "will our software still work?"}, session
    )

    assert result["still_open"] == ["Whether their dispatch client has an Apple Silicon build"]
    assert result["confidence"] == "medium"
    assert "say the open questions out loud" in result["guidance"].lower()


def test_a_question_the_material_cannot_answer_hands_over_cleanly(session, monkeypatch):
    _engineer_returning(
        SolutionsAnswer(answer="I would rather not guess at this.", confidence="low", escalate_recommended=True),
        monkeypatch,
    )

    result = executor.dispatch(
        "ask_solutions_engineer", {"question": "does it support our AS/400 terminal emulator?"}, session
    )

    assert "escalate_to_human" in result["guidance"]
    # And the handoff carries the actual question, so the person arrives
    # knowing what is being asked rather than reading a transcript.
    assert "specific question" in result["guidance"]


def test_the_engineer_reads_more_widely_than_the_sales_lookup(session, monkeypatch):
    """Four chunks is enough to answer a pricing question and not enough to be
    sure what a corpus does not say."""
    stub = _engineer_returning(SolutionsAnswer(answer="ok", confidence="high"), monkeypatch)
    executor.dispatch("ask_solutions_engineer", {"question": "MDM enrollment"}, session)
    assert stub.prompts[0].count("[") >= 4


def test_their_setup_is_passed_through_so_the_answer_can_be_specific(session, monkeypatch):
    stub = _engineer_returning(SolutionsAnswer(answer="ok", confidence="high"), monkeypatch)
    executor.dispatch(
        "ask_solutions_engineer",
        {"question": "will it work", "their_setup": "Windows 10 fleet with an in-house WPF app"},
        session,
    )
    assert "in-house WPF app" in stub.prompts[0]


def test_an_unavailable_engineer_refuses_to_invent_an_answer():
    """Making one up is the exact failure this specialist exists to prevent,
    so the fallback says so instead of guessing."""
    answer = solutions.heuristic_answer([])
    assert answer.escalate_recommended is True
    assert "guess" in answer.answer.lower()
    assert answer.confidence == "low"


def test_a_broken_engineer_does_not_fail_the_turn(session, monkeypatch):
    class Broken:
        def complete(self, *, system: str, prompt: str) -> str:
            raise TimeoutError("specialist unreachable")

    real = solutions.consult
    monkeypatch.setattr(solutions, "consult", lambda **kw: real(**{**kw, "client": Broken()}))

    result = executor.dispatch("ask_solutions_engineer", {"question": "anything"}, session)
    assert result["answer"]
    assert result["confidence"] == "low"


def test_a_weak_search_points_at_the_engineer_rather_than_at_a_human(session):
    """A technical question the knowledge base cannot settle is the case
    where escalating looks most reasonable, so it is the case the nudge has to
    cover."""
    result = executor.dispatch(
        "search_pricing_rag",
        # A real question this corpus genuinely does not cover, rather than
        # gibberish - the point is a plausible technical ask landing outside
        # four sales documents, which is what actually happens on a call.
        {"query": "kubernetes helm chart rollback"},
        session,
    )
    assert session.last_rag_score < triggers.LOW_CONFIDENCE_THRESHOLD
    assert "ask_solutions_engineer" in result["guidance"]
    assert "do NOT" in result["guidance"]


def test_a_confident_search_says_nothing_extra(session):
    result = executor.dispatch("search_pricing_rag", {"query": "MacBook Air price per device"}, session)
    assert "guidance" not in result
