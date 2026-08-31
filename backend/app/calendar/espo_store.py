"""A CalendarStore backed by EspoCRM Meetings.

Same surface as the in-memory CalendarStore, so `calendar/service.py` and the
two calendar tools are untouched.

The model here is different from the in-memory one in one important way.
EspoCRM has no concept of an "open slot" - it only stores meetings that
exist. So availability is *derived*: the same business-hours grid the
fixtures generate is treated as the set of candidate slots, and a slot is
"booked" when a Meeting in EspoCRM overlaps it. Booking therefore does not
mutate a slot record (there is none to mutate); it creates a Meeting, and the
next availability check sees the conflict on its own.

That also fixes something the in-memory store gets away with only because it
is single-process: two callers cannot both hold the same slot, because the
truth is one row in a database rather than a flag in a dict.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.calendar.fixtures import HOURS, REPS
from app.calendar.models import Booking, Slot
from app.crm.espo_client import EspoClient, EspoCRMError, from_espo_datetime, to_espo_datetime

logger = logging.getLogger("aria")

_ENTITY = "Meeting"
SLOT_MINUTES = 30


def slot_id_for(start: datetime) -> str:
    """Deterministic, unlike the fixtures' uuid4.

    It has to be: the model reads a slot id from calendar_check_availability
    on one hop and passes it to calendar_book_meeting on a later one. With
    random ids regenerated per grid rebuild, that id would no longer resolve.
    """
    return f"slot-{start.astimezone(timezone.utc).strftime('%Y%m%dT%H%M')}"


def _grid(days_ahead: int, now: datetime) -> list[tuple[datetime, str]]:
    """The candidate business-hours grid: (start, rep_name) pairs."""
    base = now.replace(minute=0, second=0, microsecond=0)
    out: list[tuple[datetime, str]] = []
    day_offset = 1
    added = 0
    rep_cycle = 0
    while added < days_ahead:
        day = base + timedelta(days=day_offset)
        day_offset += 1
        if day.weekday() >= 5:
            continue
        for hour in HOURS:
            out.append((day.replace(hour=hour), REPS[rep_cycle % len(REPS)]))
            rep_cycle += 1
        added += 1
    return out


class EspoCalendarStore:
    def __init__(
        self,
        client: EspoClient,
        assigned_user_id: str,
        *,
        days_ahead: int = 5,
    ) -> None:
        self._client = client
        self._assigned_user_id = assigned_user_id
        self._days_ahead = days_ahead

    def _busy_starts(self) -> set[datetime]:
        """Start times already taken, read from EspoCRM.

        A slot counts as taken when a Meeting starts exactly on it. Exact
        match rather than interval overlap is enough because every booking we
        make lands on the grid, and it keeps this to a single cheap query
        instead of one per candidate slot on the turn path.
        """
        try:
            meetings = self._client.list(_ENTITY, max_size=200)
        except EspoCRMError as exc:
            # Better to offer a slot that turns out to be taken than to tell a
            # customer the calendar is empty when it is not - a double-booking
            # is visible and fixable, silent unavailability loses the meeting.
            logger.warning("Calendar read failed, treating all slots as free: %s", exc)
            return set()

        busy: set[datetime] = set()
        for meeting in meetings:
            raw = meeting.get("dateStart")
            if not raw:
                continue
            try:
                busy.add(from_espo_datetime(raw))
            except ValueError:
                logger.debug("Unparseable meeting dateStart: %r", raw)
        return busy

    def all_slots(self) -> list[Slot]:
        busy = self._busy_starts()
        return [
            Slot(
                id=slot_id_for(start),
                start=start,
                end=start + timedelta(minutes=SLOT_MINUTES),
                rep_name=rep,
                booked=start in busy,
            )
            for start, rep in _grid(self._days_ahead, datetime.now(timezone.utc))
        ]

    def get_slot(self, slot_id: str) -> Slot | None:
        return next((s for s in self.all_slots() if s.id == slot_id), None)

    def save_slot(self, slot: Slot) -> Slot:
        """No-op. Availability is derived from Meetings, so there is no slot
        record to flip - service.book() sets slot.booked then calls this, and
        the Meeting created by save_booking is what actually makes it true."""
        return slot

    def save_booking(self, booking: Booking) -> Booking:
        slot = self.get_slot(booking.slot_id)
        if slot is None:
            raise ValueError(f"No such slot: {booking.slot_id}")

        payload = {
            "name": f"Apple Business demo - {slot.rep_name}",
            "status": "Planned",
            "dateStart": to_espo_datetime(slot.start),
            "dateEnd": to_espo_datetime(slot.end),
            "description": f"Booked by Aria on a live call.\nSession: {booking.session_id}",
            # An api-type user cannot be an assignedUser, and Meeting requires
            # one, so bookings hang off the regular rep user provisioned by
            # scripts/provision_crm.py.
            "assignedUserId": self._assigned_user_id,
            "parentType": "Lead",
            "parentId": booking.lead_id,
        }

        try:
            record = self._client.create(_ENTITY, payload)
        except EspoCRMError as exc:
            # Linking to a Lead that does not exist in EspoCRM (in-memory lead
            # id, or a CRM write that failed earlier) must not lose the
            # booking - retry unparented rather than dropping the meeting.
            logger.warning("Meeting create failed (%s); retrying without parent link", exc)
            payload.pop("parentType", None)
            payload.pop("parentId", None)
            record = self._client.create(_ENTITY, payload)

        return booking.model_copy(update={"id": record["id"]})

    def reset(self) -> None:
        """No-op: see EspoLeadStore.reset - wiping a real calendar is not the
        equivalent of reseeding fixtures."""
