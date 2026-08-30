from datetime import datetime, timezone

from app.calendar.models import Booking, Slot, SlotTakenError
from app.calendar.store import CalendarStore, calendar_store


def _as_utc(value: datetime | None) -> datetime | None:
    """Second line of defence for the naive/aware mismatch also handled in
    tools/executor._dt - this function is reachable from other callers."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def list_available(
    date_range_start: datetime | None = None,
    date_range_end: datetime | None = None,
    *,
    store: CalendarStore = calendar_store,
) -> list[Slot]:
    slots = [s for s in store.all_slots() if not s.booked]
    date_range_start = _as_utc(date_range_start)
    date_range_end = _as_utc(date_range_end)
    if date_range_start is not None:
        slots = [s for s in slots if s.start >= date_range_start]
    if date_range_end is not None:
        slots = [s for s in slots if s.start <= date_range_end]
    return sorted(slots, key=lambda s: s.start)


def book(
    slot_id: str,
    lead_id: str,
    session_id: str,
    *,
    store: CalendarStore = calendar_store,
) -> Booking:
    slot = store.get_slot(slot_id)
    if slot is None:
        raise ValueError(f"No such slot: {slot_id}")
    if slot.booked:
        raise SlotTakenError(f"Slot {slot_id} is already booked")

    slot.booked = True
    store.save_slot(slot)

    booking = Booking(slot_id=slot_id, lead_id=lead_id, session_id=session_id)
    return store.save_booking(booking)
