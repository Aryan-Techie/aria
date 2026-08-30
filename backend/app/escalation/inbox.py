from app.escalation.models import EscalationRecord
from app.persistence import load_state, save_state

_STATE_NAME = "inbox"


class Inbox:
    """The internal 'human inbox' record — a demo stand-in for a real ticketing
    queue, exposed via GET /api/inbox."""

    def __init__(self) -> None:
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
        save_state(_STATE_NAME, [r.model_dump(mode="json") for r in self._records])

    def add(self, record: EscalationRecord) -> int:
        self._records.append(record)
        self._persist()
        return len(self._records)

    def all(self) -> list[EscalationRecord]:
        return list(self._records)

    def reset(self) -> None:
        self._records = []
        self._persist()


inbox = Inbox()
