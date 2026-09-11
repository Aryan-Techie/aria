from fastapi.testclient import TestClient

from app.main import app
from app.tasks import service as tasks_service

client = TestClient(app)


def test_tasks_endpoint_lists_a_created_followup():
    task = tasks_service.create_task(
        "sess-task-1",
        "Send the case study Thursday",
        lead_id="lead-xyz",
        due="2026-09-15",
    )

    resp = client.get("/api/tasks")

    assert resp.status_code == 200
    body = resp.json()
    ids = [t["id"] for t in body]
    assert task.id in ids

    match = next(t for t in body if t["id"] == task.id)
    assert match["note"] == "Send the case study Thursday"
    assert match["session_id"] == "sess-task-1"
    assert match["lead_id"] == "lead-xyz"
    assert match["due"] == "2026-09-15"
    assert match["completed"] is False
