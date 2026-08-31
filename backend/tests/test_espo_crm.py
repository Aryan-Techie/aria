"""EspoCRM adapter tests.

Hermetic: httpx.MockTransport stands in for the server, so the suite never
needs Docker and never touches a real CRM. What is asserted is the mapping
and the failure policy - the two places this adapter can be wrong in a way
that only shows up mid-call.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.calendar.espo_store import EspoCalendarStore, slot_id_for
from app.calendar.models import Booking
from app.crm.espo_client import EspoClient, EspoCRMError, from_espo_datetime, to_espo_datetime
from app.crm.espo_store import EspoLeadStore
from app.crm.models import Lead


def _client(handler) -> EspoClient:
    client = EspoClient("http://espo.test", "key-123")
    client._client = httpx.Client(
        base_url="http://espo.test/api/v1",
        headers={"X-Api-Key": "key-123"},
        transport=httpx.MockTransport(handler),
    )
    return client


# --------------------------------------------------------------- datetimes

def test_datetimes_use_espos_naive_utc_format():
    """Espo rejects ISO 8601. It wants "YYYY-MM-DD HH:MM:SS", naive, UTC."""
    aware = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
    assert to_espo_datetime(aware) == "2026-09-02 10:00:00"
    assert "T" not in to_espo_datetime(aware)


def test_aware_datetimes_are_converted_not_truncated():
    """A +05:30 slot must land at 04:30 UTC, not at 10:00 with the offset
    thrown away - that would silently move every booking by the offset."""
    ist = timezone(timedelta(hours=5, minutes=30))
    assert to_espo_datetime(datetime(2026, 9, 2, 10, 0, tzinfo=ist)) == "2026-09-02 04:30:00"


def test_datetime_round_trip_comes_back_aware():
    """The rest of the codebase is aware-UTC; a naive value coming back out
    is what caused the original 'can't compare offset-naive and offset-aware'
    booking crash."""
    parsed = from_espo_datetime("2026-09-02 10:00:00")
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------- list filters

def test_list_filters_go_in_the_query_string():
    """Espo reads list filters from `where[N][...]` query params only. Sent as
    a JSON body they are accepted and ignored, and the lookup silently returns
    every record instead of the one asked for."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"total": 0, "list": []})

    _client(handler).find_one("Lead", cAriaSessionId="sess-1")

    assert "where%5B0%5D%5Btype%5D=equals" in seen["url"]
    assert "where%5B0%5D%5Battribute%5D=cAriaSessionId" in seen["url"]
    assert "sess-1" in seen["url"]


# ------------------------------------------------------------------- leads

def test_lead_writes_use_the_c_prefixed_custom_field_names():
    """EspoCRM renames custom fields with a leading "c". Writing the
    unprefixed name returns 200 and silently discards the value, so getting
    this wrong looks exactly like success."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.read() and __import__("json").loads(request.read()) or {})
        return httpx.Response(200, json={"id": "rec-1", "status": "New", **captured})

    store = EspoLeadStore(_client(handler))
    store.save(Lead(session_id="sess-1", company="Northwind", user_count=40, budget_range="50k"))

    assert captured["cAriaUserCount"] == 40
    assert captured["cAriaBudgetRange"] == "50k"
    assert captured["cAriaSessionId"] == "sess-1"
    assert "ariaUserCount" not in captured


def test_lead_status_maps_onto_espos_own_enum():
    """Espo's Lead.status accepts six fixed values; ours are different words,
    so this cannot be a passthrough."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.update(_json.loads(request.read()))
        return httpx.Response(200, json={"id": "rec-1", "status": captured["status"]})

    store = EspoLeadStore(_client(handler))
    store.save(Lead(session_id="s", status="meeting_booked"))
    assert captured["status"] == "Converted"


def test_lead_always_carries_a_last_name():
    """Espo rejects a Lead without lastName. On a B2B call the caller's name
    often never comes up, so the company stands in."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured.update(_json.loads(request.read()))
        return httpx.Response(200, json={"id": "r", "status": "New"})

    EspoLeadStore(_client(handler)).save(Lead(session_id="s", company="Northwind"))
    assert captured["lastName"] == "Northwind"


def test_crm_write_failure_never_propagates():
    """This runs on the turn path. A CRM outage must not become dead air or
    an apology about a CRM - the call has to continue."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, headers={"X-Status-Reason": "boom"}, json={})

    lead = Lead(session_id="sess-1", company="Northwind")
    returned = EspoLeadStore(_client(handler)).save(lead)

    assert returned.company == "Northwind"


def test_crm_lookup_failure_returns_none_rather_than_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    assert EspoLeadStore(_client(handler)).get_by_session("sess-1") is None


def test_second_save_updates_in_place_instead_of_creating_a_duplicate():
    """The "25 devices -> 50 devices" moment must overwrite one row, not
    leave two leads for one call."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        return httpx.Response(200, json={"id": "rec-1", "status": "New"})

    store = EspoLeadStore(_client(handler))
    store.save(Lead(session_id="sess-1", user_count=25))
    store.save(Lead(session_id="sess-1", user_count=50))

    assert calls[0][0] == "POST"
    assert calls[1] == ("PUT", "/api/v1/Lead/rec-1")


# ---------------------------------------------------------------- calendar

def test_slot_ids_are_deterministic():
    """The model reads a slot id on one hop and books it on a later one, so a
    uuid regenerated per grid rebuild would no longer resolve."""
    start = datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc)
    assert slot_id_for(start) == slot_id_for(start) == "slot-20260902T1000"


def test_availability_marks_slots_taken_by_existing_meetings():
    grid_probe = EspoCalendarStore(_client(lambda r: httpx.Response(200, json={"list": []})), "u1")
    free = grid_probe.all_slots()
    assert free and not any(s.booked for s in free)

    taken_start = free[0].start

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"list": [{"id": "m1", "dateStart": to_espo_datetime(taken_start)}]}
        )

    slots = EspoCalendarStore(_client(handler), "u1").all_slots()
    assert [s.booked for s in slots if s.start == taken_start] == [True]
    assert sum(1 for s in slots if s.booked) == 1


def test_booking_creates_a_meeting_with_an_assignee():
    """A Meeting requires assignedUser and an api-type user cannot be one -
    without this Espo answers 400 'field: assignedUser, type: required'."""
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET":
            return httpx.Response(200, json={"list": []})
        captured.update(_json.loads(request.read()))
        return httpx.Response(200, json={"id": "meet-9"})

    store = EspoCalendarStore(_client(handler), "user-42")
    slot = store.all_slots()[0]
    booking = store.save_booking(Booking(slot_id=slot.id, lead_id="lead-1", session_id="s1"))

    assert captured["assignedUserId"] == "user-42"
    assert captured["dateStart"] == to_espo_datetime(slot.start)
    assert booking.id == "meet-9"


def test_booking_retries_unparented_when_the_lead_link_is_rejected():
    """The lead id may be an in-memory one, or the CRM write may have failed
    earlier. Losing the meeting over a broken link is the wrong trade."""
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        if request.method == "GET":
            return httpx.Response(200, json={"list": []})
        body = _json.loads(request.read())
        attempts.append(body)
        if "parentId" in body:
            return httpx.Response(403, headers={"X-Status-Reason": "no access"}, json={})
        return httpx.Response(200, json={"id": "meet-10"})

    store = EspoCalendarStore(_client(handler), "user-42")
    slot = store.all_slots()[0]
    booking = store.save_booking(Booking(slot_id=slot.id, lead_id="ghost", session_id="s1"))

    assert len(attempts) == 2
    assert "parentId" not in attempts[1]
    assert booking.id == "meet-10"


def test_calendar_read_failure_does_not_claim_the_week_is_full():
    """Offering a slot that turns out to be taken is recoverable; telling a
    customer there is no availability loses the meeting outright."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={})

    slots = EspoCalendarStore(_client(handler), "u1").all_slots()
    assert slots
    assert not any(s.booked for s in slots)


def test_booking_an_unknown_slot_is_an_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"list": []})

    store = EspoCalendarStore(_client(handler), "u1")
    with pytest.raises(ValueError):
        store.save_booking(Booking(slot_id="slot-nope", lead_id="l", session_id="s"))


def test_client_surfaces_the_status_reason_header():
    """Espo's JSON body is only a translation label; the real reason is in
    X-Status-Reason, so it has to make it into the exception message."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            headers={"X-Status-Reason": "Field validation failure; field: assignedUser"},
            json={"messageTranslation": {"label": "validationFailure"}},
        )

    with pytest.raises(EspoCRMError, match="assignedUser"):
        _client(handler).create("Meeting", {})


def test_create_response_name_field_is_not_trusted():
    """Espo's computed `name` is the ACCOUNT name on a create response and the
    person's name on a later GET. Preferring it made a new lead round-trip
    with the company sitting in the contact-name field."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "rec-1",
                "name": "Northwind Logistics",   # <- account name, on create
                "lastName": "Priya",
                "accountName": "Northwind Logistics",
                "status": "New",
            },
        )

    saved = EspoLeadStore(_client(handler)).save(Lead(session_id="s", name="Priya"))
    assert saved.name == "Priya"
    assert saved.company == "Northwind Logistics"


def test_create_skips_espos_duplicate_check():
    """Espo answers 409 for a Lead resembling an existing one - matching on
    name alone is enough. Mid-call there is nobody to answer "did you mean
    this one?", so a second caller from the same company would lose their row."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["skip"] = request.headers.get("X-Skip-Duplicate-Check")
        return httpx.Response(200, json={"id": "rec-1", "status": "New"})

    _client(handler).create("Lead", {"lastName": "Priya"})
    assert seen["skip"] == "true"
