import logging
import threading

from app.crm.fixtures import SEED_LEADS
from app.crm.models import Lead
from app.persistence import load_state, save_state

logger = logging.getLogger("aria")

_STATE_NAME = "crm"


class LeadStore:
    """In-memory CRM store, optionally snapshotted to JSON (app/persistence.py)
    so a backend restart does not lose leads captured on a live call."""

# One lock per store, held across every read and every write.
#
# Found by scripts/capacity_test.py, not by inspection: at 256 concurrent
# calls a handful of turns died with "dictionary changed size during
# iteration". _persist() walks the dict to build its snapshot while another
# call's save() is inserting into it. Every session is its own thread - Agora
# calls the webhook once per turn per call - so this was always reachable; it
# just needed enough calls at once to be hit. The critical sections are a dict
# write and a JSON dump, so an RLock costs nothing measurable and turns a
# once-in-a-thousand-turns crash into an impossibility.

    def __init__(self) -> None:
        self._lock = threading.RLock()
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
        with self._lock:
            save_state(
                _STATE_NAME,
                {
                    "leads": [lead.model_dump(mode="json") for lead in self._leads.values()],
                    "session_to_lead": dict(self._session_to_lead),
                },
            )

    def all(self) -> list[Lead]:
        with self._lock:
            return list(self._leads.values())

    def get(self, lead_id: str) -> Lead | None:
        return self._leads.get(lead_id)

    def get_by_session(self, session_id: str) -> Lead | None:
        lead_id = self._session_to_lead.get(session_id)
        return self._leads.get(lead_id) if lead_id else None

    def save(self, lead: Lead) -> Lead:
        with self._lock:
            self._leads[lead.id] = lead
            if lead.session_id:
                self._session_to_lead[lead.session_id] = lead.id
            self._persist()
        return lead

    def reset(self) -> None:
        with self._lock:
            self._leads = {lead.id: lead.model_copy() for lead in SEED_LEADS}
            self._session_to_lead = {}
            self._persist()


def _build_store():
    """Chosen once at import. The in-memory store is the default and the
    fallback: if EspoCRM is selected but unreachable or unconfigured, the app
    still boots on it rather than failing to start, because a backend that
    will not come up ten minutes before a demo is the worst outcome here.
    Every individual CRM call degrades the same way - see EspoLeadStore."""
    from app.config import get_settings

    settings = get_settings()
    if settings.crm_backend != "espocrm":
        return LeadStore()

    if not settings.espocrm_api_key:
        logger.warning("CRM_BACKEND=espocrm but ESPOCRM_API_KEY is empty - using in-memory store")
        return LeadStore()

    from app.crm.espo_client import EspoClient
    from app.crm.espo_store import EspoLeadStore

    logger.info("CRM backend: EspoCRM at %s", settings.espocrm_base_url)
    return EspoLeadStore(EspoClient(settings.espocrm_base_url, settings.espocrm_api_key))


lead_store = _build_store()
