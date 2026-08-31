"""Call start/end orchestration — what routes/call.py (frontend-facing)
calls into. Agora client + token builder are injectable so this is testable
without a real Agora project."""
import random
import uuid
from datetime import datetime, timezone
from typing import Protocol

from app.agora.client import AgoraRestClient, default_agora_client
from app.agora.join_payload import build_join_payload
from app.background import run_in_background
from app.config import Settings, get_settings
from app.crm import service as crm_service
from app.notify import service as notify_service
from app.sessions.models import SessionState
from app.sessions.store import SessionStore, session_store

AGENT_RTC_UID = 1  # fixed, distinct from the randomly generated browser uid


class TokenBuilder(Protocol):
    def __call__(self, app_id: str, app_certificate: str, channel_name: str, uid: int) -> str: ...


class RtmTokenBuilder(Protocol):
    def __call__(self, app_id: str, app_certificate: str, user_account: str) -> str: ...


def _default_token_builder(app_id: str, app_certificate: str, channel_name: str, uid: int) -> str:
    from app.agora.rtc_token import build_rtc_token

    return build_rtc_token(app_id, app_certificate, channel_name, uid)


def _default_rtm_token_builder(app_id: str, app_certificate: str, user_account: str) -> str:
    from app.agora.rtc_token import build_rtm_token

    return build_rtm_token(app_id, app_certificate, user_account)


def start_call(
    *,
    agora_client: AgoraRestClient | None = None,
    token_builder: TokenBuilder = _default_token_builder,
    rtm_token_builder: RtmTokenBuilder = _default_rtm_token_builder,
    settings: Settings | None = None,
    store: SessionStore = session_store,
) -> dict:
    settings = settings or get_settings()
    agora_client = agora_client or default_agora_client()

    session_id = uuid.uuid4().hex
    channel_name = f"aria-{session_id[:8]}"
    browser_uid = random.randint(100_000, 999_999_999)

    agent_token = token_builder(settings.agora_app_id, settings.agora_app_certificate, channel_name, AGENT_RTC_UID)
    browser_token = token_builder(settings.agora_app_id, settings.agora_app_certificate, channel_name, browser_uid)
    # RTM login also needs a token when the project has App Certificate
    # enabled — found live: without this, the browser's RTM login failed
    # with "DYNAMIC_ENABLED_BUT_STATIC_KEY" (Agora's way of saying "you're
    # connecting with no token on a project that requires one"). RTC audio
    # itself doesn't hit this because the RTC token above was always passed.
    browser_rtm_token = rtm_token_builder(settings.agora_app_id, settings.agora_app_certificate, str(browser_uid))

    llm_url = f"{settings.public_base_url}/agent/{session_id}/v1/chat/completions"
    payload = build_join_payload(
        session_id=session_id,
        channel_name=channel_name,
        agent_rtc_uid=AGENT_RTC_UID,
        browser_rtc_uid=browser_uid,
        agent_token=agent_token,
        llm_url=llm_url,
        settings=settings,
    )

    join_response = agora_client.join(payload)

    session = store.get_or_create(session_id)
    session.agora_channel = channel_name
    session.agent_id = join_response.get("agent_id")
    store.save(session)

    return {
        "session_id": session_id,
        "channel_name": channel_name,
        "app_id": settings.agora_app_id,
        "uid": browser_uid,
        "rtc_token": browser_token,
        "rtm_token": browser_rtm_token,
        "agent_id": session.agent_id,
    }


def _resolve_outcome(session: SessionState) -> str:
    """Precedence per the plan: meeting_booked > escalated > qualified/disqualified > follow_up.
    Recomputed from actual session state rather than trusting whichever tool
    call last wrote session.outcome mid-call, since e.g. an escalation firing
    after a meeting was already booked shouldn't downgrade the outcome."""
    if session.booking_id:
        return "meeting_booked"
    if session.status == "escalated":
        return "escalated"
    lead = crm_service.get_lead(session.session_id)
    if lead and lead.status in ("qualified", "disqualified"):
        return lead.status
    return "follow_up"


def end_call(
    session_id: str,
    *,
    agora_client: AgoraRestClient | None = None,
    store: SessionStore = session_store,
) -> dict:
    session = store.get(session_id)
    if session is None:
        raise ValueError(f"No such session: {session_id}")

    agora_client = agora_client or default_agora_client()
    if session.agent_id:
        agora_client.leave(session.agent_id)

    outcome = _resolve_outcome(session)
    session.outcome = outcome
    if session.status == "active":
        session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    store.save(session)

    crm_service.set_outcome(session_id, outcome)

    # Backstop for the send fired at booking time, and the only path that can
    # carry the call recap - the qualification record is not complete until
    # the call is over. A no-op when that send already succeeded, when nothing
    # was booked, or when email is off. Backgrounded because this endpoint is
    # what the browser's End Call button waits on.
    run_in_background(notify_service.on_call_end, session, store=store)

    return {"session_id": session_id, "status": session.status, "outcome": outcome}
