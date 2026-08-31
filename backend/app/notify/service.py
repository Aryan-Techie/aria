"""Sends the customer their meeting confirmation, with a real calendar invite.

Deterministic, not a tool. The model does not decide whether this happens -
it fires from the booking path and, as a backstop, from call end. A ninth
tool would be one more thing for the model to forget on the one turn that
matters, and there is no judgement call to make here: a meeting was booked,
so the person it was booked with is told.

Two entry points, one email:

  * `on_booking`   - tools/executor.py, the moment calendar_book_meeting
                     succeeds. This is the one that normally fires.
  * `on_call_end`  - sessions/controller.py. Covers the case where the send
                     at booking time failed (mail server down, address
                     captured later in the call) and adds the call recap,
                     which does not exist yet at booking time.

`_send_lock` makes the check-and-set atomic across those two paths, so a call
that ends while the background send is still in flight produces one email, not
two.
"""
from __future__ import annotations

import logging
import threading

from app.calendar.labels import slot_label
from app.calendar.models import Slot
from app.crm import service as crm_service
from app.crm.models import Lead
from app.notify import ics, mailer
from app.sessions.models import SessionState

logger = logging.getLogger("aria.notify")

_send_lock = threading.Lock()

MEETING_LOCATION = "Video call - joining link follows from your specialist"


def _resolve_settings(settings):
    if settings is not None:
        return settings
    from app.config import get_settings

    return get_settings()


def _sender(settings) -> tuple[str, str]:
    """From-address, falling back to the SMTP account it authenticates as.

    Most providers reject a From that is not the authenticated mailbox, so the
    fallback is the working default rather than a convenience.
    """
    return (settings.email_from or settings.smtp_username, settings.email_from_name)


def _recap_lines(session: SessionState) -> list[str]:
    """What she and the customer actually established, for the call-end email.

    Read from LeftBrain/RightBrain rather than the transcript: these are the
    fields the tools wrote during the call, so the recap can only contain
    things that were really captured, never a summary the model invented
    after the fact.
    """
    left, right = session.left_brain, session.right_brain
    lines: list[str] = []
    if left.user_count:
        lines.append(f"- Fleet size: {left.user_count} devices")
    if left.budget_range:
        lines.append(f"- Budget: {left.budget_range}")
    if left.timeline:
        lines.append(f"- Timeline: {left.timeline}")
    if left.pain_points:
        lines.append(f"- What is driving it: {', '.join(left.pain_points)}")
    resolved = [o.raised_text for o in right.objections if o.resolved]
    if resolved:
        lines.append(f"- Covered on the call: {'; '.join(resolved)}")
    return lines


def _body(*, lead: Lead, slot: Slot, label: str, recap: list[str]) -> str:
    greeting = f"Hi {lead.name.split()[0]}," if lead.name else "Hi,"
    company = f" for {lead.company}" if lead.company else ""

    parts = [
        greeting,
        "",
        f"Thanks for your time just now. Your meeting{company} with {slot.rep_name} "
        f"from the Apple Business team is confirmed for {label}.",
        "",
        "The invitation is attached - accept it and it will drop straight into "
        "your calendar.",
    ]
    if recap:
        parts += ["", "What we covered:", *recap]
    parts += [
        "",
        "If that time stops working, reply to this email and we will move it.",
        "",
        "Aria",
        "Apple Business team",
    ]
    return "\n".join(parts)


def send_booking_confirmation(
    session: SessionState,
    slot: Slot,
    *,
    source: str,
    include_recap: bool = False,
    settings=None,
    store=None,
    send=mailer.send,
) -> bool:
    """Builds and sends the confirmation. Returns whether an email went out.

    False covers every no-op reason - disabled, no address, already sent,
    SMTP refused - and none of them raise. This runs off the back of a booking
    that has already been written to the CRM; the meeting exists whether or
    not the mail server cooperates, and neither caller can do anything useful
    with an exception.
    """
    settings = _resolve_settings(settings)
    if not settings.email_enabled:
        return False

    if store is None:
        from app.sessions.store import session_store as store

    with _send_lock:
        if session.confirmation_sent:
            return False

        lead = crm_service.get_lead(session.session_id)
        to_email = (lead.email or "").strip() if lead else ""
        if "@" not in to_email:
            # Not an error worth shouting about at booking time - she may not
            # have asked for the address yet, and the call-end pass retries.
            logger.info(
                "No usable email on lead for session %s; skipping confirmation (%s)",
                session.session_id,
                source,
            )
            return False

        from_email, from_name = _sender(settings)
        if not from_email:
            logger.warning("EMAIL_ENABLED=true but no EMAIL_FROM/SMTP_USERNAME set")
            return False

        label = slot_label(slot.start)
        recap = _recap_lines(session) if include_recap else []
        description = (
            f"Apple Business consultation with {slot.rep_name}.\n"
            f"Booked on a call with Aria, the Apple Business voice assistant.\n"
            f"Reference: {session.session_id}"
        )
        invite = ics.build_invite(
            # Deterministic and session-scoped: a client that receives the
            # booking-time email and the call-end one treats them as the same
            # event and updates it, rather than showing two meetings.
            uid=f"aria-{session.session_id}@aria.local",
            start=slot.start,
            end=slot.end,
            summary=f"Apple Business demo - {slot.rep_name}",
            description=description,
            location=MEETING_LOCATION,
            organizer_email=from_email,
            organizer_name=from_name,
            attendee_email=to_email,
            attendee_name=lead.name,
        )
        message = mailer.build_message(
            subject=f"Confirmed: your Apple Business demo, {label}",
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            to_name=lead.name,
            text_body=_body(lead=lead, slot=slot, label=label, recap=recap),
            ics_text=invite,
            bcc=settings.email_bcc,
            reply_to=settings.email_reply_to or from_email,
        )

        if not send(message, settings=settings):
            return False

        # Only marked after a send that actually succeeded, so a failure here
        # leaves the call-end backstop free to try again.
        session.confirmation_sent = True
        store.save(session)
        logger.info("Booking confirmation sent for session %s (%s)", session.session_id, source)
        return True


def on_booking(session: SessionState, slot: Slot) -> bool:
    """Booking-time send. Always called through background.run_in_background:
    an SMTP handshake is 1-3s and this sits on a live conversational turn."""
    return send_booking_confirmation(session, slot, source="booking")


def on_call_end(session: SessionState, *, store=None) -> bool:
    """Call-end backstop, with the recap the booking-time email cannot have.

    No booking means no email: a prospect who did not book never agreed to be
    contacted, and sending them something anyway is the kind of thing that
    gets a demo domain blocked.
    """
    if not session.booking_slot_id or session.confirmation_sent:
        return False

    from app.calendar import service as calendar_service

    slot = calendar_service.calendar_store.get_slot(session.booking_slot_id)
    if slot is None:
        logger.warning(
            "Session %s has booking slot %s that no longer resolves; no confirmation sent",
            session.session_id,
            session.booking_slot_id,
        )
        return False

    return send_booking_confirmation(
        session, slot, source="call_end", include_recap=True, store=store
    )
