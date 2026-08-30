from app.calendar.fixtures import seed_slots
from app.calendar.models import Booking, Slot
from app.persistence import load_state, save_state

_STATE_NAME = "calendar"


class CalendarStore:
    """In-memory calendar store, optionally snapshotted to JSON
    (app/persistence.py) so a restart does not un-book a booked meeting."""

    def __init__(self) -> None:
        self._slots: dict[str, Slot] = {s.id: s for s in seed_slots()}
        self._bookings: dict[str, Booking] = {}
        self._restore()

    def _restore(self) -> None:
        snapshot = load_state(_STATE_NAME)
        if not snapshot:
            return
        try:
            self._slots = {r["id"]: Slot.model_validate(r) for r in snapshot["slots"]}
            self._bookings = {r["id"]: Booking.model_validate(r) for r in snapshot["bookings"]}
        except Exception:
            pass

    def _persist(self) -> None:
        save_state(
            _STATE_NAME,
            {
                "slots": [s.model_dump(mode="json") for s in self._slots.values()],
                "bookings": [b.model_dump(mode="json") for b in self._bookings.values()],
            },
        )

    def all_slots(self) -> list[Slot]:
        return list(self._slots.values())

    def get_slot(self, slot_id: str) -> Slot | None:
        return self._slots.get(slot_id)

    def save_slot(self, slot: Slot) -> Slot:
        self._slots[slot.id] = slot
        self._persist()
        return slot

    def save_booking(self, booking: Booking) -> Booking:
        self._bookings[booking.id] = booking
        self._persist()
        return booking

    def reset(self) -> None:
        self._slots = {s.id: s for s in seed_slots()}
        self._bookings = {}
        self._persist()


calendar_store = CalendarStore()
