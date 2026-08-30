from app.config import Settings
from app.sessions import controller
from app.sessions.store import SessionStore
from app.tools import executor


class FakeAgoraClient:
    def __init__(self):
        self.joined_payloads = []
        self.left_agent_ids = []

    def join(self, payload: dict) -> dict:
        self.joined_payloads.append(payload)
        return {"agent_id": "fake-agent-id", "status": "RUNNING"}

    def leave(self, agent_id: str) -> None:
        self.left_agent_ids.append(agent_id)


def _fake_token_builder(app_id, app_certificate, channel_name, uid):
    return f"token-for-{uid}"


def _settings():
    return Settings(agora_app_id="app123", agora_app_certificate="cert123", public_base_url="https://demo.example.com")


def test_start_call_joins_agora_and_creates_session():
    store = SessionStore()
    agora = FakeAgoraClient()

    result = controller.start_call(
        agora_client=agora, token_builder=_fake_token_builder, settings=_settings(), store=store
    )

    assert result["rtc_token"] == f"token-for-{result['uid']}"
    assert result["agent_id"] == "fake-agent-id"
    assert len(agora.joined_payloads) == 1

    # Found live: RTM login without a token fails with
    # "DYNAMIC_ENABLED_BUT_STATIC_KEY" on a project with App Certificate
    # enabled — the response must always carry an rtm_token for the frontend.
    assert result["rtm_token"]

    session = store.get(result["session_id"])
    assert session is not None
    assert session.agora_channel == result["channel_name"]
    assert session.agent_id == "fake-agent-id"

    llm_url = agora.joined_payloads[0]["properties"]["llm"]["url"]
    assert llm_url == f"https://demo.example.com/agent/{result['session_id']}/v1/chat/completions"


def test_end_call_leaves_agora_and_resolves_follow_up_outcome():
    store = SessionStore()
    agora = FakeAgoraClient()
    started = controller.start_call(
        agora_client=agora, token_builder=_fake_token_builder, settings=_settings(), store=store
    )

    result = controller.end_call(started["session_id"], agora_client=agora, store=store)

    assert agora.left_agent_ids == ["fake-agent-id"]
    assert result["outcome"] == "follow_up"
    assert result["status"] == "ended"


def test_end_call_outcome_precedence_meeting_booked_over_qualified():
    store = SessionStore()
    agora = FakeAgoraClient()
    started = controller.start_call(
        agora_client=agora, token_builder=_fake_token_builder, settings=_settings(), store=store
    )
    session = store.get(started["session_id"])

    executor.dispatch("crm_qualify_lead", {"status": "qualified", "reason": "good fit"}, session)
    avail = executor.dispatch("calendar_check_availability", {}, session)
    executor.dispatch("calendar_book_meeting", {"slot_id": avail["slots"][0]["id"]}, session)

    result = controller.end_call(started["session_id"], agora_client=agora, store=store)
    assert result["outcome"] == "meeting_booked"


def test_end_call_unknown_session_raises():
    store = SessionStore()
    agora = FakeAgoraClient()
    try:
        controller.end_call("does-not-exist", agora_client=agora, store=store)
        assert False, "expected ValueError"
    except ValueError:
        pass
