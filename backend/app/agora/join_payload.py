"""Builds the /join request body, confirmed against docs.agora.io this
session: fields nest under "properties", not top-level as an earlier draft
of this plan assumed. Full schema verified via the join.md API reference.

Language is chosen by a profile rather than field by field - see
app/language/profiles.py for why the ASR code, the voice, MiniMax's
language_boost, the lines Agora speaks itself and the prompt's output-language
rule cannot be set independently of one another.
"""
import logging

from app.config import Settings
from app.language.profiles import LanguageProfile, get_profile

logger = logging.getLogger("aria")

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"
MINIMAX_WS_URL = "wss://api.minimax.io/ws/v1/t2a_v2"


def profile_for(settings: Settings) -> LanguageProfile:
    return get_profile(settings.agent_language)


def warn_on_language_overrides(settings: Settings, profile: LanguageProfile) -> list[str]:
    """Say so, loudly, when a pinned setting is fighting the language profile.

    ASR_LANGUAGE and MINIMAX_VOICE_ID are legitimate overrides - pinning
    `hi` instead of the code-switching `multi`, or picking the male Hindi
    voice, are both real things to want. But they are also the two lines most
    likely to be left over in an existing .env from when this only spoke
    English, and in that state setting AGENT_LANGUAGE=hi changes the prompt
    and the greeting while the recogniser and the voice stay English. The call
    half-switches, which is far more confusing to debug than not switching at
    all. Returns the warnings as well as logging them so a test can assert on
    them.
    """
    warnings: list[str] = []
    if settings.asr_language and settings.asr_language != profile.asr_language:
        warnings.append(
            f"ASR_LANGUAGE={settings.asr_language!r} overrides the {profile.code!r} profile's "
            f"{profile.asr_language!r}; blank it in .env to follow AGENT_LANGUAGE."
        )
    if settings.minimax_voice_id and settings.minimax_voice_id != profile.voice_id:
        warnings.append(
            f"MINIMAX_VOICE_ID={settings.minimax_voice_id!r} overrides the {profile.code!r} "
            f"profile's {profile.voice_id!r}; blank it in .env to follow AGENT_LANGUAGE."
        )
    for warning in warnings:
        logger.warning("language override: %s", warning)
    return warnings


def _build_filler_words(settings: Settings, profile: LanguageProfile) -> dict:
    """Agora's own stall-cover, keyed off how long our webhook stays silent.

    Both spellings of the nested config key appear in Agora's docs - the join
    API reference calls them `fixed_time_config`/`static_config`, the request
    examples call them both `config`. Sending both, with identical contents,
    so whichever one this deployment validates against is present; Agora
    ignores properties it does not recognise.

    The phrases come from the language profile: these are spoken by Agora
    rather than written by the model, so they are English until translated
    here, and an English stall line dropped into a Hindi call is worse than
    no stall line at all.
    """
    if not settings.filler_words_enabled:
        return {}

    trigger_config = {"response_wait_ms": settings.filler_response_wait_ms}
    static_config = {"phrases": profile.filler_phrases, "selection_rule": "shuffle"}

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


def _build_asr_params(settings: Settings, profile: LanguageProfile) -> dict:
    """"ares" under managed mode failed live against this account's SKU, but
    deepgram + managed mode is confirmed working — Agora validates the
    vendor's own public endpoint URL against its own allowlist, then injects
    its own key server-side, so no api_key is needed here in managed mode.

    `language` belongs in here, NOT as a sibling of `params`. It used to sit
    on the asr object itself, which Agora silently ignores along with every
    other property it does not recognise - so the language setting had no
    effect at all and Deepgram ran on its own English default. A caller
    speaking Hindi was transcribed as English-shaped nonsense, and the model
    answered the nonsense: that is where "sorry, English only" came from.
    """
    if settings.asr_vendor == "deepgram":
        params: dict = {
            "url": DEEPGRAM_WS_URL,
            "model": settings.deepgram_model,
            "language": settings.asr_language or profile.asr_language,
        }
        if settings.asr_credential_mode == "byok":
            params["api_key"] = settings.deepgram_api_key
        return params
    return {}


def _build_tts_params(settings: Settings, profile: LanguageProfile) -> dict:
    """minimax + managed mode confirmed working the same way as deepgram
    above (real endpoint URL, no key needed). elevenlabs stays available as
    a byok fallback if the user switches TTS_VENDOR explicitly.

    `language_boost` is a top-level MiniMax parameter, not part of
    voice_setting, and Agora does not validate it - its docs state that any
    parameter it does not recognise is forwarded to the vendor untouched,
    which is the only reason it can be set from here at all.
    """
    if settings.tts_vendor == "minimax":
        normalization = settings.minimax_english_normalization
        if normalization is None:
            normalization = profile.english_normalization
        return {
            "url": MINIMAX_WS_URL,
            "model": settings.minimax_model,
            "language_boost": profile.language_boost,
            "voice_setting": {
                "voice_id": settings.minimax_voice_id or profile.voice_id,
                "speed": settings.minimax_speed,
                "vol": settings.minimax_vol,
                "pitch": settings.minimax_pitch,
                "emotion": settings.minimax_emotion,
                "english_normalization": normalization,
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
    profile = profile_for(settings)
    warn_on_language_overrides(settings, profile)

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
                "credential_mode": settings.asr_credential_mode,
                "params": _build_asr_params(settings, profile),
            },
            "tts": {
                "vendor": settings.tts_vendor,
                "credential_mode": settings.tts_credential_mode,
                "params": _build_tts_params(settings, profile),
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
                # nothing to confirm they reached the right place. Comes from
                # the language profile: this is the first thing the caller
                # hears, so it decides which language they answer in.
                "greeting_message": profile.greeting,
                # What Agora's TTS says when our webhook times out, errors, or
                # returns something invalid - NOT the model. If this line
                # shows up mid-demo the backend is failing; read the log
                # before touching the prompt.
                "failure_message": profile.failure_message,
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
            **_build_filler_words(settings, profile),
        },
    }
