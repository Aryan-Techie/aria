from app.escalation.inbox import Inbox, inbox as default_inbox
from app.escalation.models import EscalationRecord, TranscriptTurn, TriggerSource
from app.escalation.notifier import notify_slack
from app.escalation.summarizer import LLMClient, summarize
from app.memory.schema import LeftBrain, RightBrain


def escalate(
    session_id: str,
    reason: str,
    trigger_source: TriggerSource,
    *,
    transcript: list[TranscriptTurn],
    left_brain: LeftBrain,
    right_brain: RightBrain,
    lead_id: str | None = None,
    summarizer_client: LLMClient | None = None,
    webhook_url: str | None = None,
    store: Inbox = default_inbox,
) -> tuple[EscalationRecord, int]:
    """Orchestrates the full escalation flow: summarize -> record -> notify.

    Returns (record, inbox_position). Notification failures (no webhook
    configured, or a delivery error) never block the escalation itself —
    the record is always created and returned so the caller can flip session
    state and reply to the customer regardless of Slack delivery outcome.
    """
    brief = summarize(transcript, left_brain, right_brain, reason, client=summarizer_client)

    record = EscalationRecord(
        session_id=session_id,
        lead_id=lead_id,
        reason=reason,
        trigger_source=trigger_source,
        brief=brief,
        transcript=transcript,
        left_brain=left_brain,
        right_brain=right_brain,
    )

    position = store.add(record)

    try:
        notify_slack(record, webhook_url=webhook_url)
    except Exception:
        pass  # Slack delivery is best-effort; the inbox record is the source of truth

    return record, position
