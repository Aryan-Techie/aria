"""Builds the /join request body, confirmed against docs.agora.io this
session: fields nest under "properties", not top-level as an earlier draft
of this plan assumed. Full schema verified via the join.md API reference.
"""
from app.config import Settings


DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
MINIMAX_WS_URL = "wss://api.minimax.io/ws/v1/t2a_v2"


def _build_asr_params(settings: Settings) -> dict:
    """"ares" under managed mode failed live against this account's SKU, but
    deepgram + managed mode is confirmed working — Agora validates the
    vendor's own public endpoint URL against its own allowlist, then injects
    its own key server-side, so no api_key is needed here in managed mode."""
    if settings.asr_vendor == "deepgram":
        params: dict = {"url": DEEPGRAM_WS_URL, "model": settings.deepgram_model}
        if settings.asr_credential_mode == "byok":
            params["api_key"] = settings.deepgram_api_key
        return params
    return {}


def _build_tts_params(settings: Settings) -> dict:
    """minimax + managed mode confirmed working the same way as deepgram
    above (real endpoint URL, no key needed). elevenlabs stays available as
    a byok fallback if the user switches TTS_VENDOR explicitly."""
    if settings.tts_vendor == "minimax":
        return {
            "url": MINIMAX_WS_URL,
            "model": settings.minimax_model,
            "voice_setting": {"voice_id": settings.minimax_voice_id, "speed": 1.0},
            "audio_setting": {"sample_rate": 44100},
        }
    if settings.tts_vendor == "elevenlabs":
        return {
            "base_url": "wss://api.elevenlabs.io/v1",
            "key": settings.elevenlabs_api_key,
            "model_id": settings.elevenlabs_model_id,
            "voice_id": settings.elevenlabs_voice_id,
            "sample_rate": 24000,
        }
    return {}


def build_join_payload(
    *,
    session_id: str,
    channel_name: str,
    agent_rtc_uid: int,
    browser_rtc_uid: int,
    agent_token: str,
    llm_url: str,
    settings: Settings,
) -> dict:
    return {
        "name": f"aria-{session_id[:8]}",
        "properties": {
            "channel": channel_name,
            "token": agent_token,
            "agent_rtc_uid": str(agent_rtc_uid),
            "remote_rtc_uids": [str(browser_rtc_uid)],
            "advanced_features": {
                # RTM channel is how we publish our own qualification_updated /
                # tool_call_started / escalation_triggered events (see rtm/publisher.py)
                "enable_rtm": True,
            },
            "asr": {
                "vendor": settings.asr_vendor,
                "language": settings.asr_language,
                "credential_mode": settings.asr_credential_mode,
                "params": _build_asr_params(settings),
            },
            "tts": {
                "vendor": settings.tts_vendor,
                "credential_mode": settings.tts_credential_mode,
                "params": _build_tts_params(settings),
            },
            "llm": {
                "url": llm_url,
                "vendor": "custom",
                "style": "openai",
                "api_key": settings.llm_shared_secret,
                "params": {"model": settings.anthropic_model},
                # Persona/instructions live in tools/prompts.py inside our own
                # backend, not here — avoids sending a duplicate system prompt.
                "system_messages": [],
                "max_history": 32,
                "greeting_message": "Hi, thanks for calling Apple Business — I'm Aria. What can I help you with today?",
                "failure_message": "Sorry, could you say that again? I didn't catch it.",
                # Deliberately empty: tool calls are handled inside our own
                # backend's loop, not delegated to Agora-routed MCP servers —
                # see the plan's tradeoff note on llm.mcp_servers.
                "mcp_servers": [],
            },
            "turn_detection": {
                "mode": "default",
                "config": {
                    "speech_threshold": 0.5,
                    "start_of_speech": {
                        "mode": "vad",
                        "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 800},
                    },
                    "end_of_speech": {
                        # tuned down from the 640ms default toward the 800ms
                        # turn-taking target; re-tune after real-call latency checks
                        "mode": "vad",
                        "vad_config": {"silence_duration_ms": 500},
                    },
                },
            },
            "interruption": {
                "enable": True,
                "mode": "start_of_speech",
            },
        },
    }
