"""Covers the confirmation email end to end without an SMTP server.

`send` is injected everywhere a message would leave the process, so these
tests assert on the built MIME message and the ICS text itself - the two
things a mail client actually reads, and the two that were wrong in every
draft of this before it worked.
"""
from datetime import datetime, timedelta, timezone

from app.calendar.models import Slot
from app.config import Settings
from app.crm import service as crm_service
from app.notify import ics, service as notify_service
from app.sessions.models import SessionState
from app.sessions.store import SessionStore

START = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)


def _settings(**overrides) -> Settings:
    base = {
        "email_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_username": "aria@example.com",
        "smtp_password": "app-password",
        "email_from_name": "Aria - Apple Business team",
    }
    base.update(overrides)
    return Settings(**base)


def _slot() -> Slot:
    return Slot(id="slot-1", start=START, end=START + timedelta(minutes=30), rep_name="Dana Whitfield")


class Recorder:
    """Stands in for mailer.send."""

    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.messages = []

    def __call__(self, message, *, settings=None) -> bool:
        self.messages.append(message)
        return self.result


def _session_with_lead(session_id="s1", *, email="priya@boltframe.io", store=None):
    store = store or SessionStore()
    session = store.get_or_create(session_id)
    crm_service.upsert_lead(session_id, name="Priya Nair", company="Boltframe Logistics", email=email)
    return session, store


# --- ICS ------------------------------------------------------------------


def test_invite_is_a_request_with_utc_times_and_crlf():
    text = ics.build_invite(
        uid="aria-s1@aria.local",
        start=START,
        end=START + timedelta(minutes=30),
        summary="Apple Business demo",
        description="ref",
        location="Video call",
        organizer_email="aria@example.com",
        organizer_name="Aria",
        attendee_email="priya@boltframe.io",
        attendee_name="Priya Nair",
    )

    # METHOD:REQUEST is what makes Gmail render an RSVP card rather than an
    # inert attachment - the whole point of sending the invite at all.
    assert "METHOD:REQUEST" in text
    assert "DTSTART:20260902T100000Z" in text
    assert "DTEND:20260902T103000Z" in text
    assert "ATTENDEE" in text and "mailto:priya@boltframe.io" in text
    # RFC 5545 requires CRLF; a bare LF file is rejected outright by Outlook.
    assert "\n" in text and text.replace("\r\n", "").count("\n") == 0


def test_invite_escapes_text_values():
    text = ics.build_invite(
        uid="u",
        start=START,
        end=START,
        summary="Demo, with Dana; part 2",
        description="line one\nline two",
        location="Video call",
        organizer_email="a@b.c",
        organizer_name="Aria",
        attendee_email="p@q.io",
    )
    assert "SUMMARY:Demo\\, with Dana\\; part 2" in text
    assert "DESCRIPTION:line one\\nline two" in text


def test_long_lines_fold_without_splitting_a_codepoint():
    company = "Bolt" + "é" * 60  # long, and multibyte
    text = ics.build_invite(
        uid="u",
        start=START,
        end=START,
        summary=company,
        description="d",
        location="l",
        organizer_email="a@b.c",
        organizer_name="Aria",
        attendee_email="p@q.io",
    )
    for line in text.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75
    # Unfolding must give the original value back byte for byte.
    unfolded = text.replace("\r\n ", "")
    assert f"SUMMARY:{company}" in unfolded


# --- message shape --------------------------------------------------------


def test_confirmation_carries_both_inline_invite_and_attachment():
    session, store = _session_with_lead()
    send = Recorder()

    assert notify_service.send_booking_confirmation(
        session, _slot(), source="test", settings=_settings(), store=store, send=send
    )

    message = send.messages[0]
    types = [part.get_content_type() for part in message.walk()]
    # Gmail honours the inline text/calendar alternative; Outlook and Apple
    # Mail take the attachment. Sending one loses the button on the others.
    assert types.count("text/calendar") == 2
    assert "multipart/alternative" in types

    inline = next(p for p in message.walk() if p.get_content_type() == "text/calendar")
    assert inline.get_param("method") == "REQUEST"
    # The subject reuses calendar.labels.slot_label, so the customer reads the
    # same phrase she spoke on the call.
    assert message["Subject"] == "Confirmed: your Apple Business demo, Wednesday 2 September at 10:00 AM"
    assert "priya@boltframe.io" in message["To"]
    assert "Dana Whitfield" in message.get_body(("plain",)).get_content()


def test_recap_only_on_the_call_end_send():
    session, store = _session_with_lead()
    session.left_brain.user_count = 50
    session.left_brain.timeline = "Q4"
    send = Recorder()

    notify_service.send_booking_confirmation(
        session, _slot(), source="booking", settings=_settings(), store=store, send=send
    )
    body = send.messages[0].get_body(("plain",)).get_content()
    assert "50 devices" not in body

    session.confirmation_sent = False
    notify_service.send_booking_confirmation(
        session,
        _slot(),
        source="call_end",
        include_recap=True,
        settings=_settings(),
        store=store,
        send=send,
    )
    body = send.messages[1].get_body(("plain",)).get_content()
    assert "50 devices" in body and "Q4" in body


# --- when it must not send ------------------------------------------------


def test_disabled_sends_nothing():
    session, store = _session_with_lead()
    send = Recorder()
    assert not notify_service.send_booking_confirmation(
        session, _slot(), source="test", settings=_settings(email_enabled=False), store=store, send=send
    )
    assert send.messages == []


def test_missing_or_malformed_address_sends_nothing():
    for address in (None, "", "not-an-address"):
        session, store = _session_with_lead(session_id=f"s-{address}", email=address)
        send = Recorder()
        assert not notify_service.send_booking_confirmation(
            session, _slot(), source="test", settings=_settings(), store=store, send=send
        )
        assert send.messages == []
        assert session.confirmation_sent is False


def test_sends_once_across_both_hooks():
    session, store = _session_with_lead()
    session.booking_slot_id = "slot-1"
    send = Recorder()

    assert notify_service.send_booking_confirmation(
        session, _slot(), source="booking", settings=_settings(), store=store, send=send
    )
    # Second call is the call-end backstop arriving after a successful send.
    assert not notify_service.send_booking_confirmation(
        session, _slot(), source="call_end", settings=_settings(), store=store, send=send
    )
    assert len(send.messages) == 1


def test_failed_send_leaves_the_backstop_free_to_retry():
    session, store = _session_with_lead()
    failing, succeeding = Recorder(result=False), Recorder(result=True)

    assert not notify_service.send_booking_confirmation(
        session, _slot(), source="booking", settings=_settings(), store=store, send=failing
    )
    assert session.confirmation_sent is False

    assert notify_service.send_booking_confirmation(
        session, _slot(), source="call_end", settings=_settings(), store=store, send=succeeding
    )
    assert session.confirmation_sent is True


def test_call_end_hook_needs_a_booking():
    store = SessionStore()
    session = store.get_or_create("no-booking")
    assert notify_service.on_call_end(session, store=store) is False


def test_call_end_hook_survives_an_unresolvable_slot():
    session, store = _session_with_lead()
    session.booking_slot_id = "slot-that-does-not-exist"
    assert notify_service.on_call_end(session, store=store) is False


def test_booking_records_the_slot_id_for_the_call_end_hook():
    """The two hooks are only connected by this field - the calendar stores
    cannot look a booking back up by id, so losing it silently disables the
    backstop."""
    from app.tools import executor

    session = SessionState(session_id="s-book")
    available = executor.dispatch("calendar_check_availability", {}, session)
    slot_id = available["slots"][0]["id"]
    executor.dispatch("calendar_book_meeting", {"slot_id": slot_id}, session)

    assert session.booking_slot_id == slot_id
