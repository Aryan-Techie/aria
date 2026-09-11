import pytest

from app.calendar import service
from app.calendar.models import BookingNotFoundError, SlotTakenError
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


def test_cancel_frees_the_slot_again():
    store = CalendarStore()
    slot = service.list_available(store=store)[0]
    booking = service.book(slot.id, lead_id="lead-1", session_id="sess-1", store=store)

    cancelled = service.cancel(booking.id, store=store)

    assert cancelled.cancelled_at is not None
    remaining = service.list_available(store=store)
    assert slot.id in [s.id for s in remaining]


def test_cancel_unknown_booking_raises():
    store = CalendarStore()
    with pytest.raises(BookingNotFoundError):
        service.cancel("does-not-exist", store=store)


def test_cancel_is_idempotent():
    store = CalendarStore()
    slot = service.list_available(store=store)[0]
    booking = service.book(slot.id, lead_id="lead-1", session_id="sess-1", store=store)

    first = service.cancel(booking.id, store=store)
    second = service.cancel(booking.id, store=store)

    assert first.cancelled_at == second.cancelled_at


def test_reschedule_frees_old_slot_and_books_new_one():
    store = CalendarStore()
    slots = service.list_available(store=store)
    old_slot, new_slot = slots[0], slots[1]
    booking = service.book(old_slot.id, lead_id="lead-1", session_id="sess-1", store=store)

    moved = service.reschedule(booking.id, new_slot.id, "lead-1", "sess-1", store=store)

    assert moved.slot_id == new_slot.id
    remaining_ids = [s.id for s in service.list_available(store=store)]
    assert old_slot.id in remaining_ids
    assert new_slot.id not in remaining_ids


def test_reschedule_to_taken_slot_raises_and_still_frees_old_one():
    store = CalendarStore()
    slots = service.list_available(store=store)
    old_slot, taken_slot = slots[0], slots[1]
    booking = service.book(old_slot.id, lead_id="lead-1", session_id="sess-1", store=store)
    service.book(taken_slot.id, lead_id="lead-2", session_id="sess-2", store=store)

    with pytest.raises(SlotTakenError):
        service.reschedule(booking.id, taken_slot.id, "lead-1", "sess-1", store=store)

    # The old slot is still freed - reschedule is cancel-then-book, and the
    # honest failure is "your old time is gone and the new one was taken",
    # not a silent no-op.
    remaining_ids = [s.id for s in service.list_available(store=store)]
    assert old_slot.id in remaining_ids
