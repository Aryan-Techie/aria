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
    # Kill-switch, separate from key presence - found live: the installed
    # mem0ai + anthropic SDK versions are incompatible (see the comment in
    # app/memory/session_memory.py::is_configured). Flip to True once fixed.
    memory_enabled: bool = False

    slack_webhook_url: str = ""
    # Off for now while premature-escalation behavior is tuned live - the
    # LLM's own (now last-resort-only) judgment is the sole escalation path.
    escalation_guardrails_enabled: bool = False

    # ASR/TTS vendor selection for the /join payload. "ares" under managed
    # mode failed live ("not available for the current SKU"), but deepgram
    # (ASR) and minimax (TTS) both confirmed WORKING under managed mode on
    # this same account - the SKU restriction was per (vendor, url/model)
    # combination, not a blanket ban on managed mode. Both need Agora's
    # documented public endpoint URL even under managed (Agora validates it
    # against its own allowlist, then injects its own key) - no external
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

    # Only used if TTS_VENDOR is switched to elevenlabs + TTS_CREDENTIAL_MODE to byok
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"
    elevenlabs_model_id: str = "eleven_flash_v2_5"

    # Shared secret Agora echoes back as llm.api_key on every call to our
    # /chat/completions webhook, validated in routes/llm.py. Set it: that
    # endpoint is reachable from the public internet through the tunnel.
    llm_shared_secret: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
