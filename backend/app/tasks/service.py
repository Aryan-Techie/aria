from app.tasks.models import Task
from app.tasks.store import TaskStore, task_store


def create_task(
    session_id: str,
    note: str,
    *,
    lead_id: str | None = None,
    due: str | None = None,
    store: TaskStore = task_store,
) -> Task:
    task = Task(session_id=session_id, lead_id=lead_id, note=note, due=due)
    return store.save(task)


def list_tasks(*, store: TaskStore = task_store) -> list[Task]:
    return store.all()
