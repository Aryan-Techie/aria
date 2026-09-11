"""The join-link email: one message to the person taking over a call.

Sent the moment an escalation is recorded, so the rep is reading the brief
while Aria is still saying she will loop someone in. Short by design - it
is read on a phone, and the page behind the link carries the full brief.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.escalation.models import EscalationRecord
from app.notify import mailer

logger = logging.getLogger("aria.notify")


def _subject(record: EscalationRecord) -> str:
    lead = record.left_brain
    who = lead.company or "A customer"
    size = "" if not lead.user_count else ", 1 device" if lead.user_count == 1 else f", {lead.user_count} devices"
    return f"Customer waiting on the line - {who}{size}"


def _body(record: EscalationRecord, url: str, rep_name: str) -> str:
    lead, brief = record.left_brain, record.brief
    lines = [
        f"{rep_name},",
        "",
        "Aria has a customer on a live call who needs a person. Open this on your phone and tap Join:",
        "",
        url,
        "",
        f"Why: {record.reason}",
        f"Mood: {brief.sentiment}",
        f"Blocker: {brief.blocker}",
        f"Suggested: {brief.recommended_action}",
        "",
    ]
    if lead.company:
        lines.append(f"Company: {lead.company}")
    lines += [
        f"Devices: {lead.user_count or '-'}",
        f"Budget: {lead.budget_range or '-'}",
        f"Timeline: {lead.timeline or '-'}",
        "",
        "Aria will announce you and leave the call once your mic is on.",
    ]
    return "\n".join(lines)


def send_join_link(record: EscalationRecord, url: str, *, settings=None) -> bool:
    settings = settings or get_settings()
    to_email = settings.handoff_rep_email
    if not (settings.email_enabled and to_email):
        logger.info("handoff email off or no HANDOFF_REP_EMAIL; link not emailed")
        return False
    from_email = settings.email_from or settings.smtp_username
    message = mailer.build_message(
        subject=_subject(record),
        from_email=from_email,
        from_name=settings.email_from_name,
        to_email=to_email,
        to_name=settings.handoff_rep_name,
        text_body=_body(record, url, settings.handoff_rep_name),
        reply_to=settings.email_reply_to,
    )
    sent = mailer.send(message, settings=settings)
    logger.info("handoff email to %s: %s", to_email, "sent" if sent else "FAILED")
    return sent
