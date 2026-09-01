import logging
import threading

from app.calendar.fixtures import seed_slots
from app.calendar.models import Booking, Slot
from app.persistence import load_state, save_state

logger = logging.getLogger("aria")

_STATE_NAME = "calendar"


class CalendarStore:
    """In-memory calendar store, optionally snapshotted to JSON
    (app/persistence.py) so a restart does not un-book a booked meeting."""

    # See the note in crm/store.py: same failure, same fix. A booking is the
    # worst place to lose a write, because the customer has already been told
    # the time out loud.
    def __init__(self) -> None:
        self._lock = threading.RLock()
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
        with self._lock:
            save_state(
                _STATE_NAME,
                {
                    "slots": [s.model_dump(mode="json") for s in self._slots.values()],
                    "bookings": [b.model_dump(mode="json") for b in self._bookings.values()],
                },
            )

    def all_slots(self) -> list[Slot]:
        with self._lock:
            return list(self._slots.values())

    def get_slot(self, slot_id: str) -> Slot | None:
        return self._slots.get(slot_id)

    def save_slot(self, slot: Slot) -> Slot:
        with self._lock:
            self._slots[slot.id] = slot
            self._persist()
        return slot

    def save_booking(self, booking: Booking) -> Booking:
        with self._lock:
            self._bookings[booking.id] = booking
            self._persist()
        return booking

    def reset(self) -> None:
        with self._lock:
            self._slots = {s.id: s for s in seed_slots()}
            self._bookings = {}
            self._persist()


def _build_store():
    """Mirrors crm/store.py: EspoCRM when configured, in-memory otherwise, and
    in-memory as the fallback if it is selected but not usable."""
    from app.config import get_settings

    settings = get_settings()
    if settings.crm_backend != "espocrm":
        return CalendarStore()

    if not (settings.espocrm_api_key and settings.espocrm_assigned_user_id):
        logger.warning(
            "CRM_BACKEND=espocrm but ESPOCRM_API_KEY/ESPOCRM_ASSIGNED_USER_ID is empty "
            "- using in-memory calendar"
        )
        return CalendarStore()

    from app.calendar.espo_store import EspoCalendarStore
    from app.crm.espo_client import EspoClient

    logger.info("Calendar backend: EspoCRM Meetings at %s", settings.espocrm_base_url)
    return EspoCalendarStore(
        EspoClient(settings.espocrm_base_url, settings.espocrm_api_key),
        settings.espocrm_assigned_user_id,
    )


calendar_store = _build_store()
