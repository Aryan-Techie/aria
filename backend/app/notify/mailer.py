"""SMTP delivery for the booking confirmation.

stdlib `smtplib` + `email.message`, not an email API SDK: SMTP works against
Gmail, Outlook, Brevo, Mailgun and a local catcher with nothing but the four
credentials already in `.env`, so the demo does not depend on one vendor's
free tier still existing on the day.

The MIME shape is the part worth being careful about, because it is what
decides whether a mail client shows an RSVP card or a file nobody opens:

    multipart/mixed
      multipart/alternative
        text/plain                          <- read by a human
        text/calendar; method=REQUEST       <- Gmail renders the RSVP card
      text/calendar (attachment, invite.ics)<- Outlook/Apple Mail pick this up

Both copies of the invite are the same bytes. Clients differ on which one they
honour, and sending only one loses the add-to-calendar button on the others.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

logger = logging.getLogger("aria.notify")

_TIMEOUT_SECONDS = 15.0


def build_message(
    *,
    subject: str,
    from_email: str,
    from_name: str,
    to_email: str,
    to_name: str | None,
    text_body: str,
    ics_text: str | None = None,
    bcc: str = "",
    reply_to: str = "",
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name, from_email))
    message["To"] = formataddr((to_name or "", to_email))
    message["Message-ID"] = make_msgid(domain="aria.local")
    if reply_to:
        message["Reply-To"] = reply_to
    if bcc:
        # Kept as a header for send_message() to strip and route on; the rep's
        # copy must not be visible to the customer.
        message["Bcc"] = bcc

    message.set_content(text_body)

    if ics_text:
        message.add_alternative(
            ics_text,
            subtype="calendar",
            params={"method": "REQUEST", "charset": "UTF-8", "name": "invite.ics"},
        )
        message.add_attachment(
            ics_text.encode("utf-8"),
            maintype="text",
            subtype="calendar",
            filename="invite.ics",
        )

    return message


def send(message: EmailMessage, *, settings=None) -> bool:
    """Sends over SMTP. Returns False on any failure rather than raising.

    Every caller is either a background task or the call-end path, and neither
    should turn a mail server problem into a failed call - the meeting is
    already in the CRM by the time this runs, so a lost email is recoverable
    and a raised exception is not.
    """
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    host, port = settings.smtp_host, settings.smtp_port
    if not host:
        logger.warning("SMTP host not configured; not sending %r", message["Subject"])
        return False

    try:
        # 465 is implicit TLS (SMTPS) and must not be STARTTLS'd; 587 is the
        # submission port and must be. Branching on the port rather than
        # asking the operator to get a second flag right.
        if port == 465:
            smtp = smtplib.SMTP_SSL(host, port, timeout=_TIMEOUT_SECONDS)
        else:
            smtp = smtplib.SMTP(host, port, timeout=_TIMEOUT_SECONDS)

        with smtp:
            smtp.ehlo()
            if port != 465 and settings.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("SMTP send failed (%s): %s", type(exc).__name__, exc)
        return False

    logger.info("Sent %r to %s", message["Subject"], message["To"])
    return True
