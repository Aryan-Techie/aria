"""Builds an RFC 5545 VEVENT for a booked meeting.

Hand-rolled rather than pulled from a library on purpose: the whole payload is
one event with a dozen properties, and a dependency here would be a new
install step on a machine that has to work on demo day. The parts that
actually matter to a real mail client are the ones that are easy to get wrong,
and they are handled explicitly below - CRLF line endings, 75-octet folding,
TEXT escaping, and UTC timestamps.

METHOD:REQUEST (rather than PUBLISH) is what makes Gmail and Outlook render
the invite as an RSVP card with an add-to-calendar action, instead of an inert
file attachment nobody clicks.
"""
from __future__ import annotations

from datetime import datetime, timezone

PRODID = "-//Aria//Apple Business Sales Agent//EN"
_MAX_OCTETS = 75


def _utc_stamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def escape_text(value: str) -> str:
    """Escapes a TEXT-typed property value (RFC 5545 section 3.3.11).

    Backslash first, or it would double-escape the ones added after it.
    """
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Folds one content line to 75 octets, continuations prefixed with a space.

    The limit is octets, not characters, so a company name with an accent in
    it can push a line over the limit while still looking short - and folding
    mid-codepoint produces a file some parsers reject outright. Chunking is
    therefore done on the encoded bytes, stepping back to a codepoint boundary.
    """
    raw = line.encode("utf-8")
    if len(raw) <= _MAX_OCTETS:
        return line

    chunks: list[str] = []
    limit = _MAX_OCTETS
    while raw:
        cut = min(limit, len(raw))
        # 0b10xxxxxx is a UTF-8 continuation byte: never cut in front of one.
        while 0 < cut < len(raw) and (raw[cut] & 0xC0) == 0x80:
            cut -= 1
        chunks.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
        limit = _MAX_OCTETS - 1  # the leading space on a continuation counts
    return "\r\n ".join(chunks)


def build_invite(
    *,
    uid: str,
    start: datetime,
    end: datetime,
    summary: str,
    description: str,
    location: str,
    organizer_email: str,
    organizer_name: str,
    attendee_email: str,
    attendee_name: str | None = None,
    now: datetime | None = None,
) -> str:
    stamp = _utc_stamp(now or datetime.now(timezone.utc))
    attendee_cn = escape_text(attendee_name) if attendee_name else attendee_email

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{_utc_stamp(start)}",
        f"DTEND:{_utc_stamp(end)}",
        "SEQUENCE:0",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        f"SUMMARY:{escape_text(summary)}",
        f"DESCRIPTION:{escape_text(description)}",
        f"LOCATION:{escape_text(location)}",
        f'ORGANIZER;CN="{escape_text(organizer_name)}":mailto:{organizer_email}',
        (
            f'ATTENDEE;CN="{attendee_cn}";ROLE=REQ-PARTICIPANT;'
            f"PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{attendee_email}"
        ),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(fold(line) for line in lines) + "\r\n"
