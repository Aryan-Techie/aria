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

    # Primary reasoning LLM. Groq serves a tool-calling hop in well under a
    # second where Anthropic took ~4s, which is the difference between a reply
    # that lands inside Agora's timeout window and one that does not. Anthropic
    # stays wired as the automatic fallback if Groq errors or is unset.
    llm_provider: str = "groq"
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"
    # "none" keeps the reasoning model from spending latency thinking out loud
    # before it answers - measured no loss of tool-selection accuracy.
    groq_reasoning_effort: str = "none"
    # Groq's free tier is ~6k tokens/minute. Our fixed per-hop cost (system
    # prompt + tool schemas) is ~2.2k, so a couple of hops exhausts the
    # window and further calls sit queued for the ~60s reset - measured at
    # 20-25s per hop, far worse than Anthropic. Rather than stall a live
    # call, give Groq a short leash and let the Anthropic fallback take over
    # the moment it cannot answer promptly.
    groq_timeout_seconds: float = 6.0

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

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
    asr_vendor: str = "deepgram"
    asr_language: str = "en"
    asr_credential_mode: str = "managed"
    deepgram_model: str = "nova-3"
    deepgram_api_key: str = ""  # only used if ASR_CREDENTIAL_MODE is switched to byok

    tts_vendor: str = "minimax"
    tts_credential_mode: str = "managed"
    minimax_model: str = "speech-2.8-turbo"
    minimax_voice_id: str = "English_captivating_female1"

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
    minimax_speed: float = 0.96
    minimax_vol: float = 1.0
    minimax_pitch: int = 0
    minimax_emotion: str = "fluent"
    # Expands "$999", "M3", "24/7" etc. into spoken form instead of letting
    # the model mangle them mid-sentence. Relevant here because nearly every
    # answer Aria gives contains a price.
    minimax_english_normalization: bool = True

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
