"""Delivers the escalation brief to a real Slack Incoming Webhook — the one
external side-effect in this build that's genuinely live rather than mocked,
alongside the CRM/calendar's dummy data.
"""
import httpx

from app.escalation.models import EscalationRecord


def format_slack_message(record: EscalationRecord) -> dict:
    """Two shapes, because they ask the human for two different things.

    A handoff says "take this call over". An approval says "answer one
    question, the call is still running" — and the difference matters, since
    the second is a person being interrupted for fifteen seconds while a
    customer waits on the line.
    """
    brief = record.brief
    if record.kind == "deal_approval":
        return {
            "text": (
                f":moneybag: *Discount approval needed — the call is still live* "
                f"(session `{record.session_id}`)\n"
                f"*Ask:* {brief.issue}\n"
                f"*Why the desk cannot sign it:* {brief.blocker}\n"
                f"*Sentiment:* {brief.sentiment}\n"
                f"*Recommended:* {brief.recommended_action}\n"
                f"Approve: `POST /api/inbox/{record.id}/approve`"
            )
        }

    text = (
        f":rotating_light: *Call escalated* (session `{record.session_id}`, "
        f"trigger: `{record.trigger_source}`)\n"
        f"*Issue:* {brief.issue}\n"
        f"*Blocker:* {brief.blocker}\n"
        f"*Sentiment:* {brief.sentiment}\n"
        f"*Recommended action:* {brief.recommended_action}"
    )
    return {"text": text}


def notify_slack(record: EscalationRecord, *, webhook_url: str | None = None) -> bool:
    """Posts the brief to Slack. Returns False (no-op, not an error) if no
    webhook URL is configured — lets escalation still work end-to-end in dev
    before a real Slack webhook is set up."""
    url = webhook_url
    if url is None:
        from app.config import get_settings

        url = get_settings().slack_webhook_url

    if not url:
        return False

    payload = format_slack_message(record)
    response = httpx.post(url, json=payload, timeout=5.0)
    return response.status_code == 200
