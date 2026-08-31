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


def _payload(**overrides):
    settings = Settings(agora_app_id="app123", **overrides)
    return build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )


def test_minimax_voice_setting_carries_delivery_controls():
    """Agora forwards tts.params to MiniMax verbatim, so the delivery knobs
    have to be inside voice_setting rather than alongside it."""
    voice = _payload()["properties"]["tts"]["params"]["voice_setting"]

    assert voice["emotion"] == "fluent"
    assert voice["english_normalization"] is True
    assert 0 < voice["speed"] <= 2
    assert 0 < voice["vol"] <= 10
    assert -12 <= voice["pitch"] <= 12


def test_agora_filler_words_off_by_default():
    """Agora's filler fires purely on elapsed webhook silence, and every turn
    here is silent for 0.9-2.6s because run_turn_stream buffers whole hops -
    so it fired on 100% of turns live. Bridge lines come from our own
    pipeline now (orchestrator/bridge_lines.py), which knows the tool names."""
    assert "filler_words" not in _payload()["properties"]


def test_filler_words_sends_both_config_spellings_when_enabled():
    """Kept switchable. Agora's docs disagree with themselves on the nested
    key - the join reference says fixed_time_config/static_config, the request
    examples say config - so both go, and Agora ignores the one it dislikes."""
    filler = _payload(filler_words_enabled=True)["properties"]["filler_words"]

    assert filler["enable"] is True
    assert filler["trigger"]["config"]["response_wait_ms"] == 800
    assert filler["trigger"]["fixed_time_config"] == filler["trigger"]["config"]
    assert filler["content"]["static_config"] == filler["content"]["config"]


def test_greeting_names_aria_and_the_business():
    greeting = _payload()["properties"]["llm"]["greeting_message"]

    assert "Aria" in greeting
    assert "Apple Park" in greeting
    assert "Cupertino" in greeting
    # Pause markers only render as audio on speech-2.8; a greeting that
    # shipped them to an older voice would read them out as text.
    assert "<#" in greeting
