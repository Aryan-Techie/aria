"""Delivers the escalation brief to a real Slack Incoming Webhook — the one
external side-effect in this build that's genuinely live rather than mocked,
alongside the CRM/calendar's dummy data.
"""
import httpx

from app.escalation.models import EscalationRecord


def format_slack_message(record: EscalationRecord) -> dict:
    brief = record.brief
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
