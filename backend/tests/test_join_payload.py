from app.agora.join_payload import build_join_payload
from app.config import Settings


def test_build_join_payload_shape():
    settings = Settings(agora_app_id="app123", anthropic_model="claude-sonnet-4-5")
    payload = build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/abcdef1234567890/v1/chat/completions",
        settings=settings,
    )

    props = payload["properties"]
    assert payload["name"] == "aria-abcdef12"
    assert props["channel"] == "aria-abcdef12"
    assert props["token"] == "fake-agent-token"
    assert props["agent_rtc_uid"] == "1"
    assert props["remote_rtc_uids"] == ["5551234"]
    assert props["advanced_features"]["enable_rtm"] is True

    assert props["llm"]["url"].endswith("/v1/chat/completions")
    assert props["llm"]["style"] == "openai"
    assert props["llm"]["vendor"] == "custom"
    assert props["llm"]["mcp_servers"] == []
    assert props["llm"]["system_messages"] == []

    assert props["interruption"]["enable"] is True
    assert props["interruption"]["mode"] == "start_of_speech"

    assert props["turn_detection"]["config"]["end_of_speech"]["mode"] == "vad"

    # Confirmed live against the real Agora API: managed mode works for
    # deepgram (ASR) and minimax (TTS) when using each vendor's real public
    # endpoint URL — Agora validates the URL against its own allowlist and
    # injects its own credentials, so no api_key/key is needed from us here.
    assert props["asr"]["vendor"] == "deepgram"
    assert props["asr"]["credential_mode"] == "managed"
    assert props["asr"]["params"]["url"] == "wss://api.deepgram.com/v1/listen"
    assert "api_key" not in props["asr"]["params"]

    assert props["tts"]["vendor"] == "minimax"
    assert props["tts"]["credential_mode"] == "managed"
    assert props["tts"]["params"]["url"] == "wss://api.minimax.io/ws/v1/t2a_v2"
    assert props["tts"]["params"]["voice_setting"]["voice_id"]


def test_build_join_payload_asr_byok_includes_api_key():
    settings = Settings(agora_app_id="app123", asr_credential_mode="byok", deepgram_api_key="dg-fake-key")
    payload = build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )
    assert payload["properties"]["asr"]["params"]["api_key"] == "dg-fake-key"


def test_build_join_payload_tts_elevenlabs_fallback():
    settings = Settings(agora_app_id="app123", tts_vendor="elevenlabs", elevenlabs_api_key="el-fake-key")
    payload = build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )
    assert payload["properties"]["tts"]["params"]["key"] == "el-fake-key"
    assert payload["properties"]["tts"]["params"]["voice_id"]
