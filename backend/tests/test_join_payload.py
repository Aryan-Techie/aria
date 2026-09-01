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
    assert props["parameters"]["data_channel"] == "rtm"

    assert props["llm"]["url"].endswith("/v1/chat/completions")
    assert props["llm"]["style"] == "openai"
    assert props["llm"]["vendor"] == "custom"
    assert props["llm"]["mcp_servers"] == []
    assert props["llm"]["system_messages"] == []

    assert props["interruption"]["enable"] is True
    assert props["interruption"]["mode"] == "start_of_speech"

    assert props["turn_detection"]["config"]["end_of_speech"]["mode"] == "vad"

    # Confirmed live against the real Agora API: managed mode works for
    # deepgram (ASR) when using its real public endpoint URL — Agora
    # validates the URL against its own allowlist and injects its own
    # credentials, so no api_key is needed from us here.
    assert props["asr"]["vendor"] == "deepgram"
    assert props["asr"]["credential_mode"] == "managed"
    assert props["asr"]["params"]["url"] == "wss://api.deepgram.com/v1/listen"
    assert "api_key" not in props["asr"]["params"]

    # sarvam is the default TTS vendor now — see test_build_join_payload_tts_sarvam
    # and test_build_join_payload_tts_minimax_fallback for the vendor-specific shape.
    assert props["tts"]["vendor"] == "sarvam"
    assert props["tts"]["credential_mode"] == "byok"
    assert props["tts"]["params"]["speaker"]
    assert props["tts"]["params"]["target_language_code"]


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


def test_build_join_payload_tts_sarvam():
    settings = Settings(agora_app_id="app123", sarvam_api_key="sv-fake-key")
    payload = build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )
    params = payload["properties"]["tts"]["params"]
    assert params["api_subscription_key"] == "sv-fake-key"
    assert params["model"] == "bulbul:v3"
    assert params["speaker"] == "priya"
    assert params["target_language_code"] == "en-IN"
    assert 0.3 <= params["pace"] <= 3.0
    assert params["sample_rate"] in (8000, 16000, 22050, 24000)
    # Confirmed live: bulbul:v3 400s outright if pitch/loudness are present
    # at all, even at neutral defaults - they must not be sent for v3.
    assert "pitch" not in params
    assert "loudness" not in params


def test_sarvam_pitch_and_loudness_survive_for_a_non_v3_model():
    """The 400 is v3-specific - a future/older model that does support these
    knobs should still get them."""
    settings = Settings(agora_app_id="app123", sarvam_model="bulbul:v2.5", sarvam_pitch=0.2, sarvam_loudness=1.5)
    payload = build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )
    params = payload["properties"]["tts"]["params"]
    assert params["pitch"] == 0.2
    assert params["loudness"] == 1.5

    # Sarvam has no documented delivery-markup feature — the greeting/failure
    # lines must not carry MiniMax's <#x#>/(breath) markup as literal text.
    assert "<#" not in payload["properties"]["llm"]["greeting_message"]
    assert "(breath)" not in payload["properties"]["llm"]["failure_message"]


def test_build_join_payload_tts_minimax_fallback():
    """MiniMax stays selectable via TTS_VENDOR — the default swapped to
    Sarvam, but this is the vendor to fall back to if Sarvam has problems on
    a live call."""
    settings = Settings(agora_app_id="app123", tts_vendor="minimax", tts_credential_mode="managed")
    payload = build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )
    props = payload["properties"]
    assert props["tts"]["vendor"] == "minimax"
    assert props["tts"]["credential_mode"] == "managed"
    assert props["tts"]["params"]["url"] == "wss://api.minimax.io/ws/v1/t2a_v2"
    assert props["tts"]["params"]["voice_setting"]["voice_id"]
    # MiniMax speech-2.8 does render the markup, so it must survive here.
    assert "<#" in props["llm"]["greeting_message"]


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
    voice = _payload(tts_vendor="minimax")["properties"]["tts"]["params"]["voice_setting"]

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
    # Sarvam (the default) has no delivery-markup feature, so the pause
    # markers must be stripped by the time they reach it.
    assert "<#" not in greeting

    # On minimax speech-2.8, which does render them, the markers survive.
    minimax_greeting = _payload(tts_vendor="minimax")["properties"]["llm"]["greeting_message"]
    assert "<#" in minimax_greeting
