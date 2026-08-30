import pytest

from app.calendar import service
from app.calendar.models import SlotTakenError
from app.calendar.store import CalendarStore


def test_seed_slots_are_all_available_and_on_weekdays():
    store = CalendarStore()
    slots = service.list_available(store=store)
    assert len(slots) == 15  # 5 business days x 3 slots/day
    assert all(not s.booked for s in slots)
    assert all(s.start.weekday() < 5 for s in slots)


def test_book_marks_slot_unavailable():
    store = CalendarStore()
    slot = service.list_available(store=store)[0]

    booking = service.book(slot.id, lead_id="lead-1", session_id="sess-1", store=store)

    assert booking.slot_id == slot.id
    remaining = service.list_available(store=store)
    assert slot.id not in [s.id for s in remaining]


def test_double_booking_raises():
    store = CalendarStore()
    slot = service.list_available(store=store)[0]
    service.book(slot.id, lead_id="lead-1", session_id="sess-1", store=store)

    with pytest.raises(SlotTakenError):
        service.book(slot.id, lead_id="lead-2", session_id="sess-2", store=store)


def test_book_unknown_slot_raises():
    store = CalendarStore()
    with pytest.raises(ValueError):
        service.book("does-not-exist", lead_id="lead-1", session_id="sess-1", store=store)
