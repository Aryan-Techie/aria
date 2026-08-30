from app.crm.fixtures import SEED_LEADS
from app.crm.models import Lead
from app.persistence import load_state, save_state

_STATE_NAME = "crm"


class LeadStore:
    """In-memory CRM store, optionally snapshotted to JSON (app/persistence.py)
    so a backend restart does not lose leads captured on a live call."""

    def __init__(self) -> None:
        self._leads: dict[str, Lead] = {lead.id: lead.model_copy() for lead in SEED_LEADS}
        self._session_to_lead: dict[str, str] = {}
        self._restore()

    def _restore(self) -> None:
        snapshot = load_state(_STATE_NAME)
        if not snapshot:
            return
        try:
            self._leads = {
                record["id"]: Lead.model_validate(record) for record in snapshot["leads"]
            }
            self._session_to_lead = dict(snapshot.get("session_to_lead", {}))
        except Exception:  # a stale snapshot must never stop the app booting
            pass

    def _persist(self) -> None:
        save_state(
            _STATE_NAME,
            {
                "leads": [lead.model_dump(mode="json") for lead in self._leads.values()],
                "session_to_lead": self._session_to_lead,
            },
        )

    def all(self) -> list[Lead]:
        return list(self._leads.values())

    def get(self, lead_id: str) -> Lead | None:
        return self._leads.get(lead_id)

    def get_by_session(self, session_id: str) -> Lead | None:
        lead_id = self._session_to_lead.get(session_id)
        return self._leads.get(lead_id) if lead_id else None

    def save(self, lead: Lead) -> Lead:
        self._leads[lead.id] = lead
        if lead.session_id:
            self._session_to_lead[lead.session_id] = lead.id
        self._persist()
        return lead

    def reset(self) -> None:
        self._leads = {lead.id: lead.model_copy() for lead in SEED_LEADS}
        self._session_to_lead = {}
        self._persist()


lead_store = LeadStore()
