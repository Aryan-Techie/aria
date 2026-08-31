"""Builds the /join request body, confirmed against docs.agora.io this
session: fields nest under "properties", not top-level as an earlier draft
of this plan assumed. Full schema verified via the join.md API reference.
"""
from app.config import Settings


DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
MINIMAX_WS_URL = "wss://api.minimax.io/ws/v1/t2a_v2"

# Apple's real, public head office. Used rather than an invented branch
# address so the agent is not stating a fabricated Apple location to a caller.
GREETING_MESSAGE = (
    "Thanks for calling Apple Business Sales, "
    "Apple Park, One Apple Park Way in Cupertino. <#0.25#> "
    "This is Aria speaking. <#0.2#> How can I help you today?"
)

# Kept short and low-commitment. Agora picks one at random the moment a turn
# stalls, with no idea what the model is about to do, so anything that
# promises a specific action ("I'll book that now") can contradict the answer
# that follows. These only buy time.
FILLER_PHRASES = [
    "Let me pull that up for you. <#0.3#> One second.",
    "Sure <#0.2#> give me just a second.",
    "(breath) Okay, let me check that.",
    "Mm, <#0.2#> one moment, I'm looking at it now.",
    "Let me get you the exact number on that. <#0.3#> Bear with me.",
    "Right, <#0.2#> just pulling that up.",
]


def _build_filler_words(settings: Settings) -> dict:
    """Agora's own stall-cover, keyed off how long our webhook stays silent.

    Both spellings of the nested config key appear in Agora's docs - the join
    API reference calls them `fixed_time_config`/`static_config`, the request
    examples call them both `config`. Sending both, with identical contents,
    so whichever one this deployment validates against is present; Agora
    ignores properties it does not recognise.
    """
    if not settings.filler_words_enabled:
        return {}

    trigger_config = {"response_wait_ms": settings.filler_response_wait_ms}
    static_config = {"phrases": FILLER_PHRASES, "selection_rule": "shuffle"}

    return {
        "filler_words": {
            "enable": True,
            "trigger": {
                "mode": "fixed_time",
                "config": trigger_config,
                "fixed_time_config": trigger_config,
            },
            "content": {
                "mode": "static",
                "config": static_config,
                "static_config": static_config,
            },
        }
    }


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
            "voice_setting": {
                "voice_id": settings.minimax_voice_id,
                "speed": settings.minimax_speed,
                "vol": settings.minimax_vol,
                "pitch": settings.minimax_pitch,
                "emotion": settings.minimax_emotion,
                "english_normalization": settings.minimax_english_normalization,
            },
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
                # Spoken verbatim by MiniMax, so it carries the same
                # delivery markup the model uses mid-call: `<#x#>` is a pause
                # of x seconds and `(...)` an interjection tag - both are
                # speech-2.8 features, see SPEECH_STYLE_PROMPT in
                # tools/prompts.py. Answered switchboard-style (org, location,
                # name, offer) because a bare "Hi, I'm Aria" gives the caller
                # nothing to confirm they reached the right place.
                "greeting_message": GREETING_MESSAGE,
                # What Agora's TTS says when our webhook times out, errors, or
                # returns something invalid - NOT the model. If this line
                # shows up mid-demo the backend is failing; read the log
                # before touching the prompt.
                "failure_message": "(breath) Sorry — could you say that once more? I didn't quite catch it.",
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
            # Agora speaks one of these on its own if our webhook has produced
            # no output for response_wait_ms. run_turn_stream buffers every
            # tool hop and only yields on the concluding hop, so a RAG lookup
            # or a calendar booking is several seconds of silence otherwise -
            # this is what makes Aria say "let me pull that up" while she is
            # genuinely pulling it up. The phrases carry `<#x#>` pause markers
            # and speech-2.8 interjection tags for the same reason the rest of
            # her speech does.
            **_build_filler_words(settings),
        },
    }
