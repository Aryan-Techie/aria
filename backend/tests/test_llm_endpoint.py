from fastapi.testclient import TestClient

from app.main import app
from app.orchestrator.llm_client import LLMTurn, ToolCall
from app.sessions.store import session_store

client = TestClient(app)


class ScriptedLLMClient:
    """Returns queued LLMTurns in order, one per create_turn() call — lets a
    test script exactly what the LLM does at each hop of the tool loop
    without any network call or API key."""

    def __init__(self, turns: list[LLMTurn]):
        self._turns = list(turns)
        self.calls: list[dict] = []

    def create_turn(self, *, system, messages, tools) -> LLMTurn:
        self.calls.append({"messages": messages, "tools": tools})
        if not self._turns:
            raise AssertionError("ScriptedLLMClient ran out of scripted turns")
        return self._turns.pop(0)


def _patch_llm_client(monkeypatch, turns: list[LLMTurn]) -> ScriptedLLMClient:
    fake = ScriptedLLMClient(turns)
    monkeypatch.setattr("app.orchestrator.pipeline.default_llm_client", lambda: fake)
    return fake


def _post(session_id: str, user_text: str, history: list[dict] | None = None) -> dict:
    messages = (history or []) + [{"role": "user", "content": user_text}]
    response = client.post(f"/agent/{session_id}/v1/chat/completions", json={"messages": messages})
    assert response.status_code == 200
    return response.json()


def test_blank_content_turns_are_dropped_not_sent_to_llm(monkeypatch):
    """Found live on a real call: Agora sent a message with empty content
    (an interim ASR slot), which Anthropic's API rejects outright
    ("messages.N: user messages must have non-empty content"), turning an
    ordinary turn into a hard 500. Blank turns must never reach the LLM."""
    fake = _patch_llm_client(monkeypatch, [LLMTurn(text="Got it.")])

    response = client.post(
        "/agent/sess-blank/v1/chat/completions",
        json={"messages": [{"role": "user", "content": "  "}, {"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Got it."
    # the blank turn never made it into what was sent to the LLM
    sent_messages = fake.calls[0]["messages"]
    assert all(m["content"] for m in sent_messages)


def test_all_blank_turns_skips_llm_entirely(monkeypatch):
    fake = _patch_llm_client(monkeypatch, [LLMTurn(text="should not be called")])

    response = client.post(
        "/agent/sess-allblank/v1/chat/completions",
        json={"messages": [{"role": "user", "content": ""}, {"role": "user", "content": "   "}]},
    )

    assert response.status_code == 200
    assert "didn't quite catch" in response.json()["choices"][0]["message"]["content"]
    assert fake.calls == []  # never called the LLM with an empty message list


def test_simple_reply_with_no_tool_use(monkeypatch):
    _patch_llm_client(monkeypatch, [LLMTurn(text="Hi, thanks for calling!")])

    body = _post("sess-simple", "Hello")

    assert body["choices"][0]["message"]["content"] == "Hi, thanks for calling!"
    assert body["choices"][0]["message"]["role"] == "assistant"


def test_pricing_question_triggers_rag_tool_call_and_grounded_answer(monkeypatch):
    _patch_llm_client(
        monkeypatch,
        [
            LLMTurn(
                text="",
                tool_calls=[ToolCall(id="tc1", name="search_pricing_rag", input={"query": "enterprise pricing"})],
                stop_reason="tool_use",
            ),
            LLMTurn(text="Our Enterprise tier is a custom quote based on usage."),
        ],
    )

    body = _post("sess-pricing", "What does the enterprise tier cost?")

    assert "Enterprise" in body["choices"][0]["message"]["content"]
    session = session_store.get("sess-pricing")
    assert session.last_rag_score is not None and session.last_rag_score > 0


def test_requirement_change_updates_same_lead_without_restart(monkeypatch):
    # Turn 1: customer states 10 users -> crm_upsert_lead(user_count=10)
    _patch_llm_client(
        monkeypatch,
        [
            LLMTurn(
                text="",
                tool_calls=[ToolCall(id="tc1", name="crm_upsert_lead", input={"user_count": 10, "company": "Acme"})],
                stop_reason="tool_use",
            ),
            LLMTurn(text="Got it, 10 users at Acme."),
        ],
    )
    body1 = _post("sess-reqchange", "We have 10 users at Acme")
    assert "10" in body1["choices"][0]["message"]["content"]
    session = session_store.get("sess-reqchange")
    lead_id_after_turn1 = session.crm_lead_id
    assert session.left_brain.user_count == 10

    # Turn 2: customer corrects to 50 users -> same lead, field overwritten, no restart
    _patch_llm_client(
        monkeypatch,
        [
            LLMTurn(
                text="",
                tool_calls=[ToolCall(id="tc2", name="crm_upsert_lead", input={"user_count": 50})],
                stop_reason="tool_use",
            ),
            LLMTurn(text="Updated to 50 users."),
        ],
    )
    history = [
        {"role": "user", "content": "We have 10 users at Acme"},
        {"role": "assistant", "content": "Got it, 10 users at Acme."},
    ]
    body2 = _post("sess-reqchange", "Actually it's 50 users", history=history)

    assert "50" in body2["choices"][0]["message"]["content"]
    session = session_store.get("sess-reqchange")
    assert session.crm_lead_id == lead_id_after_turn1  # same lead, not a new one
    assert session.left_brain.user_count == 50
    assert session.left_brain.company == "Acme"  # preserved from turn 1


def test_interrupted_then_resumed_history_is_trusted_over_local_state(monkeypatch):
    """Simulates a barge-in: the history Agora sends shows the agent's prior
    reply was cut short mid-sentence. The pipeline must treat that truncated
    text as ground truth rather than whatever we might have tracked locally."""
    _patch_llm_client(monkeypatch, [LLMTurn(text="Sure, let's compare on that.")])

    truncated_history = [
        {"role": "user", "content": "What's your pricing"},
        {"role": "assistant", "content": "Our Starter tier starts at $19 per se"},  # cut off
        {"role": "user", "content": "wait, how does that compare to Rivalio?"},
    ]
    body = _post("sess-interrupt", "wait, how does that compare to Rivalio?", history=truncated_history[:-1])

    session = session_store.get("sess-interrupt")
    assert session.transcript[1].content == "Our Starter tier starts at $19 per se"
    assert body["choices"][0]["message"]["content"] == "Sure, let's compare on that."


def test_forced_escalation_fires_when_llm_never_calls_the_tool(monkeypatch):
    # LLM keeps ending turns normally, never escalates on its own —
    # the frustration-streak guardrail should force it.
    # Guardrails are off by default (disabled live while premature-escalation
    # behavior was being tuned) — explicitly re-enable for this test, which
    # covers the guardrail logic itself.
    from app.config import Settings

    monkeypatch.setattr(
        "app.orchestrator.pipeline.get_settings",
        lambda: Settings(escalation_guardrails_enabled=True),
    )
    _patch_llm_client(monkeypatch, [LLMTurn(text="I understand your frustration.")])

    session = session_store.get_or_create("sess-guardrail")
    session.right_brain.sentiment_history = ["frustrated", "frustrated"]
    session_store.save(session)

    body = _post("sess-guardrail", "This still isn't working for me")

    assert session.status == "escalated"
    assert "specialist" in body["choices"][0]["message"]["content"].lower()


def test_guardrails_off_by_default_do_not_force_escalation(monkeypatch):
    # Default Settings() has escalation_guardrails_enabled=False — a
    # frustration streak that would otherwise force a handoff must NOT
    # escalate while the toggle is off.
    _patch_llm_client(monkeypatch, [LLMTurn(text="I understand your frustration.")])

    session = session_store.get_or_create("sess-guardrail-off")
    session.right_brain.sentiment_history = ["frustrated", "frustrated"]
    session_store.save(session)

    _post("sess-guardrail-off", "This still isn't working for me")

    assert session.status != "escalated"


def test_meeting_booking_end_to_end(monkeypatch):
    _patch_llm_client(
        monkeypatch,
        [
            LLMTurn(text="", tool_calls=[ToolCall(id="tc1", name="calendar_check_availability", input={})], stop_reason="tool_use"),
        ],
    )
    # First hop returns availability; script a second client for the booking hop
    # since we need the slot_id from the first tool result, which the fake
    # client can't see dynamically — so drive this in two separate requests
    # using the admin endpoint to discover a real slot_id instead.
    slots = client.get("/api/calendar/slots").json()
    slot_id = slots[0]["id"]

    _patch_llm_client(
        monkeypatch,
        [
            LLMTurn(
                text="",
                tool_calls=[ToolCall(id="tc2", name="calendar_book_meeting", input={"slot_id": slot_id})],
                stop_reason="tool_use",
            ),
            LLMTurn(text="You're booked for the demo."),
        ],
    )
    body = _post("sess-booking", "Book me that slot")

    assert "booked" in body["choices"][0]["message"]["content"].lower()
    session = session_store.get("sess-booking")
    assert session.outcome == "meeting_booked"
