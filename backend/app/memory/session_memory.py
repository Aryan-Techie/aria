"""Ties mem0 recall/write-back to a call session.

mem0 handles long-range recall beyond Agora's 32-turn history window and
free-text nuance that doesn't fit the LeftBrain/RightBrain schema cleanly —
the schema structs (app/memory/schema.py) remain the deterministic source of
truth the CRM/calendar tools read and write directly; mem0 is a supplementary
recall layer, not the record of truth. See the plan's Memory Schema section.

`safe_recall`/`safe_write_back` are what the orchestrator pipeline actually
calls: they no-op (zero network) whenever Voyage/Anthropic keys aren't
configured, and swallow any runtime failure, so a memory-layer problem never
breaks a live call — the call degrades to "no long-range recall this turn"
rather than failing outright.
"""
from app.background import run_in_background
from app.memory.client import get_memory


def is_configured(settings=None) -> bool:
    if settings is None:
        from app.config import get_settings

        settings = get_settings()
    # `memory_enabled` is a separate kill-switch from key presence. Found
    # live: the installed mem0ai + anthropic SDK versions are incompatible —
    # mem0's AnthropicLLM passes `temperature` in a way this anthropic
    # version rejects ("Messages.create() got an unexpected keyword argument
    # 'temperature'"). safe_recall/safe_write_back already catch this so it
    # never breaks a call, but every attempt is a doomed API round-trip —
    # real wasted latency on every single turn, a likely contributor to
    # Agora timing out and speaking its own failure_message. Disabled until
    # the mem0/anthropic version mismatch is fixed (pinning `anthropic`
    # older risks the SDK version our own tool-calling loop also depends on,
    # a much bigger blast radius than losing optional long-range recall).
    return settings.memory_enabled and bool(settings.anthropic_api_key and settings.voyage_api_key)


def recall(session_id: str, query: str, *, limit: int = 5) -> list[str]:
    memory = get_memory()
    results = memory.search(query=query, user_id=session_id, limit=limit)
    items = results.get("results", results) if isinstance(results, dict) else results
    return [item["memory"] for item in items if item.get("memory")]


def write_back(session_id: str, user_text: str, assistant_text: str) -> None:
    memory = get_memory()
    memory.add(
        messages=[
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ],
        user_id=session_id,
    )


def safe_recall(session_id: str, query: str, *, limit: int = 5) -> list[str]:
    if not query.strip() or not is_configured():
        return []
    try:
        return recall(session_id, query, limit=limit)
    except Exception:
        return []


def safe_write_back(session_id: str, user_text: str, assistant_text: str) -> None:
    """Fire-and-forget: memory write-back used to run inline, so its latency
    was charged to the reply the customer is waiting to hear. Nothing in the
    current turn reads what it writes, so it belongs off the response path.

    The `is_configured` guard stays synchronous so an unconfigured install is
    still a true zero-work, zero-thread no-op.
    """
    if not is_configured():
        return
    run_in_background(write_back, session_id, user_text, assistant_text)
