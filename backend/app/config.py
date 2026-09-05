from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolved from this file, not the cwd, so `uvicorn app.main:app` works from
# either the repo root or backend/. Repo-root .env is the shared one the
# frontend setup also documents; backend/.env, if present, wins over it.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_REPO_ROOT / ".env", _BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    agora_app_id: str = ""
    agora_app_certificate: str = ""
    agora_customer_key: str = ""
    agora_customer_secret: str = ""

    public_base_url: str = "http://localhost:8000"

    # Comma-separated list of origins the browser frontend is served from.
    cors_allowed_origins: str = "http://localhost:3000"

    # Primary reasoning LLM. "gemini" is a single-model path (no fallback
    # routing) - fewer moving parts than the groq/anthropic pair below, tried
    # here for lower latency off one vendor. "groq" keeps the
    # groq-then-anthropic-fallback behaviour those settings describe. Revert
    # to "groq" to go back to that.
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_api_key: str = ""
    # Chosen by measurement, not reputation - scripts/bench_llm.py runs
    # candidates against the real system prompt and the real tool schemas,
    # because a benchmark on a toy prompt says nothing when the fixed cost
    # of a hop is ~4,600 tokens. gpt-oss-20b: 0.74s to first token with the
    # right tool call. qwen3.8-27b, the previous default: 1.03s AND it
    # missed the tool call on the same turn.
    groq_model: str = "openai/gpt-oss-20b"
    # "none" keeps the reasoning model from spending latency thinking out loud
    # before it answers - measured no loss of tool-selection accuracy.
    # "none" is a qwen spelling; the gpt-oss models reject it outright with
    # a 400 and accept only low/medium/high. "low" is the nearest thing to
    # off and measured no loss of tool-selection accuracy.
    groq_reasoning_effort: str = "low"
    # Groq's free tier is ~6k tokens/minute. Our fixed per-hop cost (system
    # prompt + tool schemas) is ~2.2k, so a couple of hops exhausts the
    # window and further calls sit queued for the ~60s reset - measured at
    # 20-25s per hop, far worse than Anthropic. Rather than stall a live
    # call, give Groq a short leash and let the Anthropic fallback take over
    # the moment it cannot answer promptly.
    groq_timeout_seconds: float = 6.0

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    # The model that serves a turn when Groq cannot. Separate from
    # anthropic_model because the two jobs are not the same one: this sits on
    # the conversational path where the customer is waiting, and on a free
    # Groq tier it is not the rare safety net it was designed as - a single
    # hop is ~74% of the 6k-token minute, so the second hop of a turn is
    # routinely throttled and lands here. Measured: Sonnet serves a hop in
    # ~4-6s, which is the whole of the felt latency. Haiku is a weaker
    # negotiator and a fast answer beats a slow one on a live call; set this
    # to claude-sonnet-4-5 to trade back.
    anthropic_fallback_model: str = "claude-haiku-4-5-20251001"

    # When set, the CRM/calendar/inbox stores snapshot to JSON here so a
    # backend restart does not wipe a booked meeting mid-demo. Blank = pure
    # in-memory (the case under pytest, where conftest blanks env_file).
    state_dir: str = ""

    mem0_vector_store_path: str = "./data/mem0"
    voyage_api_key: str = ""
    # Kill-switch, separate from key presence — found live: the installed
    # mem0ai + anthropic SDK versions are incompatible (see the comment in
    # app/memory/session_memory.py::is_configured). Flip to True once fixed.
    memory_enabled: bool = False

    # Which CRM backs the crm_* tools. "memory" is the original in-process
    # store (fixtures + a JSON snapshot); "espocrm" talks to the real
    # EspoCRM in crm/docker-compose.yml. Default stays "memory" so the test
    # suite is hermetic and so a demo still runs if Docker will not start.
    crm_backend: str = "memory"
    espocrm_base_url: str = "http://localhost:8080"
    espocrm_api_key: str = ""
    # A Meeting must have an assignedUser and an api-type user cannot be one,
    # so bookings are assigned to a regular user. Printed by
    # scripts/provision_crm.py.
    espocrm_assigned_user_id: str = ""

    # Confirmation email + calendar invite, sent when a meeting is booked.
    # Off by default and a no-op when off: the code path is reachable from a
    # live call, and a half-configured mail server should cost nothing rather
    # than block a turn. Any SMTP provider works - Gmail with an App Password
    # (free, 500/day) is what this was developed against.
    email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587  # 587 = STARTTLS submission; 465 = implicit TLS
    smtp_starttls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""  # Gmail: an App Password, never the account password
    # Most providers reject a From that is not the authenticated mailbox, so
    # this falls back to SMTP_USERNAME when blank.
    email_from: str = ""
    email_from_name: str = "Aria - Apple Business team"
    email_reply_to: str = ""
    # Optional silent copy to the rep who owns the meeting.
    email_bcc: str = ""
    # Where the end-of-call wrap-up is emailed. Blank sends none - the
    # wrap-up still lands on the CRM record, which needs no configuration
    # at all and is where the rep already is.
    rep_summary_email: str = ""

    slack_webhook_url: str = ""
    # Off for now while premature-escalation behavior is tuned live — the
    # LLM's own (now last-resort-only) judgment is the sole escalation path.
    escalation_guardrails_enabled: bool = False

    # ASR/TTS vendor selection for the /join payload. "ares" under managed
    # mode failed live ("not available for the current SKU"), but deepgram
    # (ASR) and minimax (TTS) both confirmed WORKING under managed mode on
    # this same account — the SKU restriction was per (vendor, url/model)
    # combination, not a blanket ban on managed mode. Both need Agora's
    # documented public endpoint URL even under managed (Agora validates it
    # against its own allowlist, then injects its own key) — no external
    # vendor account or API key required for either default.
    # Which language profile the agent runs in: "en", "hi", or "hinglish".
    # One setting rather than five, because the ASR language, the TTS voice,
    # MiniMax's language_boost, the spoken greeting/filler lines and the
    # prompt's output-language rule all have to agree - see
    # app/language/profiles.py. Any of them left on an English default is on
    # its own enough to break a Hindi call.
    agent_language: str = "en"
    # Change the TTS voice mid-call: follow the caller when they switch
    # language, and give the second-layer agents a voice of their own.
    # Off by default - it spends a REST round-trip out of an ~800ms turn
    # budget, and it is unverified against a live Agora agent. See
    # app/voice/director.py and scripts/check_voice_switch.py.
    voice_switching_enabled: bool = False

    asr_vendor: str = "deepgram"
    # Overridden by the language profile unless explicitly set. Kept as its
    # own setting so a profile's ASR code can be swapped without editing the
    # profile - e.g. pinning "hi" instead of "multi" if code-switching
    # recognition turns out worse than single-language on real calls.
    asr_language: str = ""
    asr_credential_mode: str = "managed"
    deepgram_model: str = "nova-3"
    deepgram_api_key: str = ""  # only used if ASR_CREDENTIAL_MODE is switched to byok

    # sarvam is the default TTS vendor: it speaks the Indian languages this
    # app actually calls in natively, rather than as a secondary market.
    # Agora's docs (docs.agora.io/en/ai/models/tts/sarvam) show no managed
    # mode for it - the key travels inline in tts.params - so this is byok,
    # like elevenlabs below, not managed like minimax/deepgram.
    tts_vendor: str = "sarvam"
    tts_credential_mode: str = "byok"
    sarvam_api_key: str = ""
    # Sarvam deprecated bulbul:v2 - confirmed live, a direct call to Sarvam's
    # own REST API with no model field returns "Model 'bulbul:v2' has been
    # deprecated. Please use 'bulbul:v3' instead." Sent explicitly rather than
    # left to whatever Agora defaults to internally, since Agora's own sarvam
    # docs still describe v2's speaker names.
    sarvam_model: str = "bulbul:v3"
    # Blank takes the language profile's speaker. Unlike MiniMax, Sarvam
    # speakers are cross-lingual - the same speaker id works across
    # target_language_code values, so one speaker per persona covers every
    # language this app speaks rather than needing an English AND a Hindi id.
    sarvam_speaker: str = ""
    # [-0.75, 0.75] / [0.1, 3.0]. Confirmed live: bulbul:v3 rejects the whole
    # request if either is present at all ("Pitch and loudness parameters are
    # currently not supported for the Bulbul V3 model"), so join_payload.py
    # only sends these when sarvam_model isn't v3 - kept here for a future/
    # older model that does support them, not used by the current default.
    sarvam_pitch: float = 0.0
    sarvam_loudness: float = 1.0
    # [0.3, 3.0], per Sarvam's documented range. Still honoured on v3.
    sarvam_pace: float = 1.0
    # 8000 | 16000 | 22050 | 24000, per Sarvam's documented options.
    sarvam_sample_rate: int = 24000

    # Fallback vendor - swap TTS_VENDOR back to "minimax" (and
    # TTS_CREDENTIAL_MODE to "managed") if Sarvam has problems on a live call.
    # Confirmed working under managed mode on this account before the swap to
    # Sarvam: Agora validates minimax's real public endpoint URL against its
    # own allowlist, then injects its own key server-side, so no api_key is
    # needed here even though it stays selectable.
    minimax_model: str = "speech-2.8-turbo"
    # Blank takes the language profile's voice. MiniMax voice ids are
    # language-specific: an English voice reading Devanagari is not accented
    # Hindi, it is unusable.
    minimax_voice_id: str = ""
    # None takes the language profile's language_boost. Set to "" (empty
    # string, not unset) to omit the parameter entirely rather than send it
    # blank - e.g. to A/B a Hindi voice's pronunciation with vs without the
    # boost applied.
    minimax_language_boost: str | None = None

    # Delivery controls, all straight from MiniMax's t2a_v2 voice_setting.
    # Agora forwards tts.params to MiniMax verbatim, so anything MiniMax
    # accepts here works. Exposed as settings so the voice can be re-tuned
    # between demo takes without a code change.
    #   speed  - (0, 2]; slightly under 1 reads as considered rather than rushed
    #   vol    - (0, 10]
    #   pitch  - [-12, 12]
    #   emotion- happy | sad | angry | fearful | disgusted | surprised |
    #            calm | fluent | whisper. "fluent" is the conversational one;
    #            "happy" oversells and reads as a chirpy IVR on a sales call.
    # None follows the language profile's speed.
    minimax_speed: float | None = None
    minimax_vol: float = 1.0
    minimax_pitch: int = 0
    minimax_emotion: str = "fluent"
    # Expands "$999", "M3", "24/7" etc. into spoken form instead of letting
    # the model mangle them mid-sentence. Relevant here because nearly every
    # answer Aria gives contains a price.
    # None takes the language profile's answer. MiniMax documents this
    # expansion pass as an English/Chinese feature, so it is off for Hindi -
    # leaving it on spends latency on a pass that does not apply.
    minimax_english_normalization: bool | None = None

    # Agora can speak a stall phrase itself, triggered only on how long our
    # webhook has been silent. OFF, because that trigger cannot express "speak
    # when a tool fires": run_turn_stream buffers each hop, so even a turn
    # calling NO tool takes 0.9-2.6s to first byte, which overlaps the 1.4s a
    # tool hop takes. Set low enough to catch tool calls it fired on every
    # single turn - confirmed live. The bridge line is emitted from our own
    # pipeline instead, where the actual tool names are known:
    # see orchestrator/bridge_lines.py.
    filler_words_enabled: bool = False
    filler_response_wait_ms: int = 800

    # Only used if TTS_VENDOR is switched to elevenlabs + TTS_CREDENTIAL_MODE to byok
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"
    elevenlabs_model_id: str = "eleven_flash_v2_5"

    # Optional shared secret Agora echoes back as llm.api_key on every call to
    # our /chat/completions webhook — set this and check it in routes/llm.py
    # once ready to prevent unauthenticated calls to a publicly exposed endpoint.
    llm_shared_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
