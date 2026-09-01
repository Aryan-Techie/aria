import threading
from datetime import datetime, timezone

from app.escalation.models import EscalationRecord
from app.persistence import load_state, save_state

_STATE_NAME = "inbox"


class Inbox:
    """The internal 'human inbox' record — a demo stand-in for a real ticketing
    queue, exposed via GET /api/inbox."""

    # Lock-guarded alongside the other in-memory stores: a discount
    # approval can be answered over HTTP while a call is appending its own
    # escalation, so add/resolve/persist must not interleave.
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: list[EscalationRecord] = []
        self._restore()

    def _restore(self) -> None:
        snapshot = load_state(_STATE_NAME)
        if not snapshot:
            return
        try:
            self._records = [EscalationRecord.model_validate(r) for r in snapshot]
        except Exception:
            pass

    def _persist(self) -> None:
        with self._lock:
            save_state(_STATE_NAME, [r.model_dump(mode="json") for r in self._records])

    def add(self, record: EscalationRecord) -> int:
        with self._lock:
            self._records.append(record)
            self._persist()
            return len(self._records)

    def all(self) -> list[EscalationRecord]:
        with self._lock:
            return list(self._records)

    def get(self, record_id: str) -> EscalationRecord | None:
        return next((r for r in self._records if r.id == record_id), None)

    def resolve_approval(self, record_id: str, approved_pct: float, approved_by: str):
        """Records a human's answer to a discount approval request.

        Kept on the inbox rather than on the session because this is the
        human's side of the exchange: the queue is what a person is looking
        at, and the record is what they answered. The session picks the answer
        up separately - see routes/admin.py::approve_discount.
        """
        with self._lock:
            record = self.get(record_id)
            if record is None:
                return None
            record.approved_pct = approved_pct
            record.approved_by = approved_by
            record.resolved_at = datetime.now(timezone.utc)
            self._persist()
            return record

    def reset(self) -> None:
        with self._lock:
            self._records = []
            self._persist()


inbox = Inbox()
