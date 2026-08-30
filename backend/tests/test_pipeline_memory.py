"""Verifies the memory_recall/memory_write_back injection points in
orchestrator/pipeline.py are wired correctly, using fakes instead of real
mem0/Voyage/Anthropic calls — proves the plumbing without needing credentials."""
from app.escalation.models import TranscriptTurn
from app.orchestrator import pipeline
from app.orchestrator.llm_client import LLMTurn
from app.rtm.publisher import LoggingPublisher
from app.sessions.models import SessionState


class RecordingLLMClient:
    def __init__(self, reply_text: str):
        self._reply_text = reply_text
        self.received_systems: list[str] = []

    def create_turn(self, *, system, messages, tools):
        self.received_systems.append(system)
        return LLMTurn(text=self._reply_text)


def test_recalled_memories_are_injected_into_system_prompt():
    recalled = ["Customer previously mentioned a 2026-Q1 renewal deadline."]
    calls = []

    def fake_recall(session_id: str, query: str) -> list[str]:
        calls.append((session_id, query))
        return recalled

    llm_client = RecordingLLMClient("Sure, let's talk about your renewal timeline.")
    session = SessionState(session_id="sess-mem", mem0_user_id="sess-mem")

    reply = pipeline.run_turn(
        session,
        [TranscriptTurn(role="user", content="What were we discussing about timing?")],
        llm_client=llm_client,
        publisher=LoggingPublisher(),
        memory_recall=fake_recall,
        memory_write_back=lambda *a, **k: None,
    )

    assert reply == "Sure, let's talk about your renewal timeline."
    assert calls == [("sess-mem", "What were we discussing about timing?")]
    assert "2026-Q1 renewal deadline" in llm_client.received_systems[0]


def test_no_recalled_memories_leaves_system_prompt_unmodified():
    llm_client = RecordingLLMClient("Hi there!")
    session = SessionState(session_id="sess-mem2", mem0_user_id="sess-mem2")

    pipeline.run_turn(
        session,
        [TranscriptTurn(role="user", content="Hello")],
        llm_client=llm_client,
        publisher=LoggingPublisher(),
        memory_recall=lambda session_id, query: [],
        memory_write_back=lambda *a, **k: None,
    )

    # An untouched session adds no call-state or memory blocks - only the
    # date stamp build_system_prompt() always appends.
    system = llm_client.received_systems[0]
    assert system.startswith(pipeline.ARIA_SYSTEM_PROMPT)
    assert "Today is" in system
    assert "already established on this call" not in system
    assert "recalled from earlier" not in system


def test_write_back_receives_user_and_final_assistant_text():
    written = []

    def fake_write_back(session_id: str, user_text: str, assistant_text: str) -> None:
        written.append((session_id, user_text, assistant_text))

    llm_client = RecordingLLMClient("Got it, thanks!")
    session = SessionState(session_id="sess-mem3", mem0_user_id="sess-mem3")

    pipeline.run_turn(
        session,
        [TranscriptTurn(role="user", content="We need this live by March")],
        llm_client=llm_client,
        publisher=LoggingPublisher(),
        memory_recall=lambda session_id, query: [],
        memory_write_back=fake_write_back,
    )

    assert written == [("sess-mem3", "We need this live by March", "Got it, thanks!")]
