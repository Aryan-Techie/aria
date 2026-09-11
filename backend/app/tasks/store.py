import logging
import threading

from app.persistence import load_state, save_state
from app.tasks.models import Task

logger = logging.getLogger("aria")

_STATE_NAME = "tasks"


class TaskStore:
    """In-memory task store, snapshotted the same way calendar/store.py is -
    see the note there for why."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, Task] = {}
        self._restore()

    def _restore(self) -> None:
        snapshot = load_state(_STATE_NAME)
        if not snapshot:
            return
        try:
            self._tasks = {r["id"]: Task.model_validate(r) for r in snapshot["tasks"]}
        except Exception:
            pass

    def _persist(self) -> None:
        with self._lock:
            save_state(_STATE_NAME, {"tasks": [t.model_dump(mode="json") for t in self._tasks.values()]})

    def save(self, task: Task) -> Task:
        with self._lock:
            self._tasks[task.id] = task
            self._persist()
        return task

    def all(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def reset(self) -> None:
        with self._lock:
            self._tasks = {}
            self._persist()


def _build_store():
    """Mirrors calendar/store.py: EspoCRM when configured, in-memory
    otherwise, and in-memory as the fallback if it is selected but not
    usable."""
    from app.config import get_settings

    settings = get_settings()
    if settings.crm_backend != "espocrm":
        return TaskStore()

    if not (settings.espocrm_api_key and settings.espocrm_assigned_user_id):
        logger.warning("CRM_BACKEND=espocrm but ESPOCRM_API_KEY/ESPOCRM_ASSIGNED_USER_ID is empty - using in-memory tasks")
        return TaskStore()

    from app.crm.espo_client import EspoClient
    from app.tasks.espo_store import EspoTaskStore

    logger.info("Task backend: EspoCRM Tasks at %s", settings.espocrm_base_url)
    return EspoTaskStore(
        EspoClient(settings.espocrm_base_url, settings.espocrm_api_key),
        settings.espocrm_assigned_user_id,
    )


task_store = _build_store()
