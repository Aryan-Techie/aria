"""RTM side-channel publisher.

`LoggingPublisher` is an in-memory stand-in (used by default in tests and
whenever Agora credentials aren't configured — mirrors the safe/no-op
pattern in app/memory/session_memory.py). `AgoraRtmPublisher` is the real
implementation: it posts our custom JSON envelope to Agora's RTM REST API
so the browser's raw `rtmClient.addEventListener("message", ...)` picks it
up on the call's own RTM channel — confirmed against docs.agora.io's
Signaling channel-message REST reference (POST .../rtm/users/{user_id}/channel_messages,
Basic auth with the same customer key/secret already used for the
Conversational AI REST API).
"""
import base64
import json
from datetime import datetime, timezone
from typing import Protocol

import httpx

from app.background import run_in_background
from pydantic import BaseModel


class RtmEvent(BaseModel):
    type: str
    session_id: str
    ts: datetime
    payload: dict


class RtmPublisher(Protocol):
    def publish(self, session_id: str, event_type: str, payload: dict) -> None: ...


class LoggingPublisher:
    def __init__(self) -> None:
        self.events: list[RtmEvent] = []

    def publish(self, session_id: str, event_type: str, payload: dict) -> None:
        self.events.append(
            RtmEvent(
                type=event_type,
                session_id=session_id,
                ts=datetime.now(timezone.utc),
                payload=payload,
            )
        )


class AgoraRtmPublisher:
    """Posts to Agora's RTM channel-message REST API — a one-off HTTP POST,
    no persistent RTM connection needed from the backend. Best-effort: a
    failed publish is swallowed rather than breaking the call, since these
    events only drive UI panels, never call-critical logic."""

    def __init__(self, app_id: str, customer_key: str, customer_secret: str, backend_user_id: str = "aria-backend"):
        self._app_id = app_id
        self._backend_user_id = backend_user_id
        credentials = base64.b64encode(f"{customer_key}:{customer_secret}".encode()).decode()
        self._headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}

    def publish(self, session_id: str, event_type: str, payload: dict) -> None:
        from app.sessions.store import session_store  # local import avoids a circular import

        session = session_store.get(session_id)
        channel_name = session.agora_channel if session and session.agora_channel else session_id

        envelope = {
            "type": event_type,
            "session_id": session_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }
        url = f"https://api.agora.io/dev/v2/project/{self._app_id}/rtm/users/{self._backend_user_id}/channel_messages"
        body = {"channel_name": channel_name, "payload": json.dumps(envelope, default=str)}
        # Fire-and-forget: these events only drive UI panels, so the customer
        # must never wait on them. Sent inline this was up to five blocking
        # 5s-timeout POSTs per turn, stacked on top of the Anthropic calls.
        run_in_background(self._post, url, body)

    def _post(self, url: str, body: dict) -> None:
        httpx.post(url, headers=self._headers, json=body, timeout=5.0)


class SessionEventRecorder:
    """Appends every published envelope onto the session itself.

    The browser polls these over HTTP instead of relying on RTM delivery,
    which was publishing successfully (200 from Agora) without the events
    ever reaching the page. These panels are cosmetic, never call-critical,
    so a transport we own end-to-end beats one we cannot observe.
    """

    def publish(self, session_id: str, event_type: str, payload: dict) -> None:
        from app.sessions.store import session_store

        session = session_store.get(session_id)
        if session is None:
            return
        session.events.append(
            {
                "type": event_type,
                "payload": payload,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        session_store.save(session)


class CompositePublisher:
    """Fans one publish out to several publishers; one failing never stops
    the others."""

    def __init__(self, *publishers: RtmPublisher):
        self._publishers = publishers

    def publish(self, session_id: str, event_type: str, payload: dict) -> None:
        for publisher in self._publishers:
            try:
                publisher.publish(session_id, event_type, payload)
            except Exception:
                pass


default_publisher = LoggingPublisher()


def default_rtm_publisher() -> RtmPublisher:
    """Returns the real Agora-backed publisher once credentials are
    configured, otherwise the in-memory stand-in — keeps the test suite
    hermetic (blank Settings in tests) without needing special-casing."""
    from app.config import get_settings

    settings = get_settings()
    recorder = SessionEventRecorder()
    if settings.agora_app_id and settings.agora_customer_key and settings.agora_customer_secret:
        return CompositePublisher(
            recorder,
            AgoraRtmPublisher(settings.agora_app_id, settings.agora_customer_key, settings.agora_customer_secret),
        )
    return default_publisher
