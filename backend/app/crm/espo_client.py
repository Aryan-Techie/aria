"""Thin HTTP client for EspoCRM's REST API.

Kept separate from the store so the store's mapping logic can be tested
without a socket, and so the two EspoCRM quirks that cost real debugging time
live in one place:

1. List filters go in the QUERY STRING as `where[0][type]` etc, not in a JSON
   body. A GET with a body is accepted and silently ignored, so a filtered
   lookup comes back as "every record" rather than as an error.
2. Datetimes are naive UTC strings, "YYYY-MM-DD HH:MM:SS" - not ISO 8601, no
   "T", no offset. Sending an ISO string is rejected as a validation failure.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger("aria")

ESPO_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class EspoCRMError(RuntimeError):
    """An EspoCRM call failed. Carries the X-Status-Reason header, which is
    where Espo puts the actual reason - the JSON body is only a translation
    label like {"label": "validationFailure"} and says nothing useful."""


def to_espo_datetime(value: datetime) -> str:
    """Naive-UTC string in Espo's format. Aware inputs are converted, not
    truncated, so a local-time slot does not silently shift by the offset."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime(ESPO_DATETIME_FORMAT)


def from_espo_datetime(value: str) -> datetime:
    """Espo hands back naive UTC; the rest of this codebase is aware-UTC."""
    return datetime.strptime(value, ESPO_DATETIME_FORMAT).replace(tzinfo=timezone.utc)


class EspoClient:
    """Synchronous because the tool executor is synchronous. The client is
    pooled and reused - building one per call also builds a new TLS/TCP
    connection per call, which is exactly the latency mistake already fixed
    once on the Anthropic path (see llm_client.py)."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 5.0) -> None:
        self._client = httpx.Client(
            base_url=f"{base_url.rstrip('/')}/api/v1",
            headers={"X-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            reason = exc.response.headers.get("X-Status-Reason", "")
            raise EspoCRMError(
                f"{method} {path} -> {exc.response.status_code} {reason}".strip()
            ) from exc
        except httpx.HTTPError as exc:
            raise EspoCRMError(f"{method} {path} -> {exc}") from exc

        return response.json() if response.content else None

    def create(self, entity: str, payload: dict) -> dict:
        """`X-Skip-Duplicate-Check` is not optional here.

        EspoCRM refuses a Lead that looks like one it already has with
        `409 duplicate` - and "looks like" includes matching on name alone.
        Two calls from the same company, or two callers with the same name,
        would each lose their CRM row to a 409. The duplicate warning exists
        for humans typing into a form who can be asked "did you mean this
        one?"; there is nobody to ask mid-call.
        """
        return self._request(
            "POST", f"/{entity}", json=payload, headers={"X-Skip-Duplicate-Check": "true"}
        )

    def update(self, entity: str, record_id: str, payload: dict) -> dict:
        return self._request("PUT", f"/{entity}/{record_id}", json=payload)

    def get(self, entity: str, record_id: str) -> dict:
        return self._request("GET", f"/{entity}/{record_id}")

    def list(self, entity: str, *, max_size: int = 50, **filters: str) -> list[dict]:
        """`filters` are field=value equality checks, ANDed together.

        Built as `where[N][...]` query params because that is the only form
        EspoCRM's list endpoint reads - see the module docstring.
        """
        params: dict[str, Any] = {"maxSize": max_size}
        for index, (field, value) in enumerate(filters.items()):
            params[f"where[{index}][type]"] = "equals"
            params[f"where[{index}][attribute]"] = field
            params[f"where[{index}][value]"] = value

        result = self._request("GET", f"/{entity}", params=params)
        return (result or {}).get("list", [])

    def find_one(self, entity: str, **filters: str) -> dict | None:
        rows = self.list(entity, max_size=1, **filters)
        return rows[0] if rows else None

    def close(self) -> None:
        self._client.close()
