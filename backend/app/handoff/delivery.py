"""Puts the wrap-up in front of a human, by every route that is configured.

Three, deliberately, in decreasing order of how much setup they need:

  * **The CRM record** - always, and with no configuration at all. It is where
    the rep already is, and a summary that needs a Slack workspace to exist is
    a summary that does not exist on a fresh machine.
  * **Slack** - when a webhook is set, because it is the one that arrives
    while the lead is still worth calling back.
  * **Email** - when SMTP is configured and a rep address is set.

Every one is best effort and independent: a Slack outage must not cost the
CRM note, and none of them may raise, because this runs off the back of a call
that has already ended and there is nothing left to abort.
"""
from __future__ import annotations

import logging

from app.handoff.models import CallSummary

logger = logging.getLogger("aria.handoff")


def _settings(settings):
    if settings is not None:
        return settings
    from app.config import get_settings

    return get_settings()


def to_crm(summary: CallSummary) -> bool:
    from app.crm import service as crm_service

    try:
        crm_service.add_note(summary.session_id, "Call wrap-up\n" + summary.as_text())
        return True
    except Exception:
        logger.warning("could not write the wrap-up to the CRM", exc_info=True)
        return False


def to_slack(summary: CallSummary, *, webhook_url: str | None = None, settings=None) -> bool:
    import httpx

    url = webhook_url if webhook_url is not None else _settings(settings).slack_webhook_url
    if not url:
        return False

    urgency_icon = {"now": ":red_circle:", "today": ":large_orange_circle:"}.get(
        summary.urgency, ":white_circle:"
    )
    who = " / ".join(filter(None, [summary.company, summary.contact])) or "Unknown caller"
    text = (
        f"{urgency_icon} *Call wrap-up - {who}* (`{summary.outcome}`)\n"
        f"{summary.headline}\n"
        f"*Do next:* {summary.recommended_action}\n"
    )
    if summary.agreed:
        text += "*Already agreed:* " + "; ".join(summary.agreed[:3]) + "\n"
    if summary.risks:
        text += "*Watch out:* " + "; ".join(summary.risks[:3]) + "\n"
    text += (
        f"_{summary.duration_seconds // 60}m call, {summary.turn_count} turns, "
        f"~{summary.minutes_saved:g} minutes of rep time it stands in for._"
    )

    try:
        return httpx.post(url, json={"text": text}, timeout=5.0).status_code == 200
    except Exception:
        logger.warning("Slack wrap-up delivery failed", exc_info=True)
        return False


def to_email(summary: CallSummary, *, settings=None, send=None) -> bool:
    settings = _settings(settings)
    if not settings.email_enabled or not settings.rep_summary_email:
        return False

    from app.notify import mailer

    send = send or mailer.send
    from_email = settings.email_from or settings.smtp_username
    if not from_email:
        return False

    who = " / ".join(filter(None, [summary.company, summary.contact])) or "Unknown caller"
    try:
        message = mailer.build_message(
            subject=f"Call wrap-up: {who} - {summary.outcome.replace('_', ' ')}",
            from_email=from_email,
            from_name=settings.email_from_name,
            to_email=settings.rep_summary_email,
            to_name=None,
            text_body=summary.as_text(),
            reply_to=settings.email_reply_to or from_email,
        )
        return bool(send(message, settings=settings))
    except Exception:
        logger.warning("email wrap-up delivery failed", exc_info=True)
        return False


def deliver(summary: CallSummary, *, settings=None) -> dict:
    """Fan out, and report which routes actually took it. The return value is
    what makes "the rep was told" checkable rather than assumed."""
    delivered = {
        "crm": to_crm(summary),
        "slack": to_slack(summary, settings=settings),
        "email": to_email(summary, settings=settings),
    }
    logger.info("wrap-up for session %s delivered via %s", summary.session_id, delivered)
    return delivered
