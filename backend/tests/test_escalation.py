from app.escalation import service, triggers
from app.escalation.inbox import Inbox
from app.escalation.models import TranscriptTurn
from app.escalation.notifier import format_slack_message, notify_slack
from app.escalation.summarizer import heuristic_brief
from app.memory.schema import LeftBrain, Objection, RightBrain


def test_frustration_streak_detects_two_consecutive_negative_turns():
    rb = RightBrain(sentiment_history=["neutral", "skeptical", "frustrated"])
    assert triggers.frustration_streak(rb) is True


def test_frustration_streak_not_triggered_by_single_bad_turn():
    rb = RightBrain(sentiment_history=["positive", "frustrated"])
    assert triggers.frustration_streak(rb) is False


def test_objection_retry_exceeded_flags_unresolved_repeat_objection():
    rb = RightBrain(
        objections=[
            Objection(topic="pricing", raised_text="too expensive", attempts=3, resolved=False)
        ]
    )
    result = triggers.objection_retry_exceeded(rb)
    assert result is not None
    assert result.topic == "pricing"


def test_objection_retry_ignores_resolved_objections():
    rb = RightBrain(
        objections=[
            Objection(
                topic="pricing", raised_text="too expensive", attempts=5, resolved=True
            )
        ]
    )
    assert triggers.objection_retry_exceeded(rb) is None


def test_check_triggers_precedence_frustration_before_low_confidence():
    rb = RightBrain(sentiment_history=["frustrated", "frustrated"])
    should_escalate, source = triggers.check_triggers(rb, last_rag_score=0.01)
    assert should_escalate is True
    assert source == "frustration_streak"


def test_check_triggers_low_confidence_only():
    rb = RightBrain()
    should_escalate, source = triggers.check_triggers(rb, last_rag_score=0.01)
    assert should_escalate is True
    assert source == "low_confidence"


def test_check_triggers_no_escalation_when_healthy():
    rb = RightBrain(sentiment_history=["positive", "neutral"])
    should_escalate, source = triggers.check_triggers(rb, last_rag_score=0.9)
    assert should_escalate is False
    assert source is None


def test_heuristic_brief_surfaces_unresolved_objection_as_blocker():
    rb = RightBrain(
        objections=[Objection(topic="trust", raised_text="not sure about security", attempts=3)]
    )
    transcript = [
        TranscriptTurn(role="user", content="I'm still worried about security"),
        TranscriptTurn(role="assistant", content="Let me explain our compliance process"),
    ]
    brief = heuristic_brief(transcript, LeftBrain(), rb, reason="objection loop")
    assert "security" in brief.blocker.lower()
    assert brief.issue == "I'm still worried about security"


def test_notify_slack_no_op_without_webhook_url():
    from app.escalation.models import EscalationRecord, EscalationBrief

    record = EscalationRecord(
        session_id="sess-1",
        reason="test",
        trigger_source="llm",
        brief=EscalationBrief(
            issue="x", blocker="y", sentiment="neutral", recommended_action="z"
        ),
        left_brain=LeftBrain(),
        right_brain=RightBrain(),
    )
    assert notify_slack(record, webhook_url="") is False


def test_format_slack_message_includes_brief_fields():
    from app.escalation.models import EscalationRecord, EscalationBrief

    record = EscalationRecord(
        session_id="sess-1",
        reason="test",
        trigger_source="objection_retry",
        brief=EscalationBrief(
            issue="pricing question",
            blocker="unresolved pricing objection",
            sentiment="skeptical",
            recommended_action="offer a discount call",
        ),
        left_brain=LeftBrain(),
        right_brain=RightBrain(),
    )
    message = format_slack_message(record)
    assert "pricing question" in message["text"]
    assert "offer a discount call" in message["text"]


class _FakeLLMClient:
    def __init__(self, response: str):
        self._response = response

    def complete(self, prompt: str) -> str:
        return self._response


def test_escalate_service_end_to_end_with_fake_llm_and_no_webhook():
    inbox = Inbox()
    fake_client = _FakeLLMClient(
        '{"issue": "wants enterprise pricing", "blocker": "no confirmed budget", '
        '"sentiment": "neutral", "recommended_action": "send custom quote"}'
    )
    transcript = [TranscriptTurn(role="user", content="What's your enterprise pricing?")]

    record, position = service.escalate(
        "sess-1",
        "customer asked for enterprise demo",
        "llm",
        transcript=transcript,
        left_brain=LeftBrain(company="Acme"),
        right_brain=RightBrain(),
        summarizer_client=fake_client,
        webhook_url="",  # no-op notifier, but must not raise
        store=inbox,
    )

    assert position == 1
    assert record.brief.issue == "wants enterprise pricing"
    assert inbox.all() == [record]


def test_escalate_service_falls_back_to_heuristic_on_bad_llm_output():
    inbox = Inbox()
    broken_client = _FakeLLMClient("not valid json")
    transcript = [TranscriptTurn(role="user", content="I keep asking about pricing")]

    record, _ = service.escalate(
        "sess-2",
        "objection loop",
        "objection_retry",
        transcript=transcript,
        left_brain=LeftBrain(),
        right_brain=RightBrain(
            objections=[Objection(topic="pricing", raised_text="too expensive", attempts=3)]
        ),
        summarizer_client=broken_client,
        webhook_url="",
        store=inbox,
    )

    assert "pricing" in record.brief.blocker.lower()
