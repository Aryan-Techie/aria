"""A TaskStore backed by EspoCRM's stock Task entity.

Same surface as the in-memory TaskStore. Task is a genuine stock EspoCRM
entity - no custom-field provisioning needed, same tier as Lead.title/
Lead.industry - so this is a straight field mapping, not a new entity build.
"""
from __future__ import annotations

import logging

from app.crm.espo_client import EspoClient, EspoCRMError
from app.tasks.models import Task

logger = logging.getLogger("aria")

_ENTITY = "Task"


def _to_espo(task: Task, assigned_user_id: str) -> dict:
    payload: dict = {
        "name": task.note[:100],
        "description": task.note,
        "status": "Completed" if task.completed else "Not Started",
        "assignedUserId": assigned_user_id,
    }
    if task.due:
        payload["dateEnd"] = task.due
    if task.lead_id:
        payload["parentType"] = "Lead"
        payload["parentId"] = task.lead_id
    return payload


def _from_espo(record: dict, session_id: str) -> Task:
    return Task(
        id=record["id"],
        session_id=session_id,
        lead_id=record.get("parentId"),
        note=record.get("description") or record.get("name") or "",
        due=record.get("dateEnd"),
        completed=record.get("status") == "Completed",
    )


class EspoTaskStore:
    def __init__(self, client: EspoClient, assigned_user_id: str) -> None:
        self._client = client
        self._assigned_user_id = assigned_user_id

    def save(self, task: Task) -> Task:
        payload = _to_espo(task, self._assigned_user_id)
        try:
            record = self._client.create(_ENTITY, payload)
        except EspoCRMError as exc:
            # Same policy as everywhere else on the turn path: a lost
            # follow-up task is recoverable, a broken call is not.
            logger.error("Task create failed for session=%s: %s", task.session_id, exc)
            return task
        return task.model_copy(update={"id": record["id"]})

    def all(self) -> list[Task]:
        try:
            records = self._client.list(_ENTITY, max_size=200)
        except EspoCRMError as exc:
            logger.warning("Task list failed: %s", exc)
            return []
        return [_from_espo(r, session_id="") for r in records]

    def reset(self) -> None:
        """No-op - see EspoLeadStore.reset."""
