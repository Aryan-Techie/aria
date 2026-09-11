from app.tasks import service
from app.tasks.store import TaskStore


def test_create_task_persists_note_and_due():
    store = TaskStore()
    task = service.create_task("sess-1", "call back after the CFO signs off", lead_id="lead-1", due="next Thursday", store=store)

    assert task.note == "call back after the CFO signs off"
    assert task.due == "next Thursday"
    assert task.lead_id == "lead-1"
    assert not task.completed
    assert [t.id for t in service.list_tasks(store=store)] == [task.id]


def test_due_is_optional():
    store = TaskStore()
    task = service.create_task("sess-1", "send the case study", store=store)
    assert task.due is None
    assert task.lead_id is None


def test_tasks_from_different_sessions_all_list_together():
    store = TaskStore()
    service.create_task("sess-1", "first", store=store)
    service.create_task("sess-2", "second", store=store)
    assert len(service.list_tasks(store=store)) == 2
