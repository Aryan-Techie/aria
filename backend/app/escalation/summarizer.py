"""Turns a call snapshot into a structured handoff brief for a human rep —
{issue, blocker, sentiment, recommended_action} — mirroring how tools like
Intercom Fin / Zendesk hand off, instead of dumping a raw transcript.

Uses one Anthropic call by default (`AnthropicSummarizerClient`), but the LLM
client is injectable so tests never need a real API key or network call —
and `heuristic_brief` gives a deterministic fallback if the LLM call fails
or returns something unparseable, so escalation can never silently no-op.
"""
import json
from typing import Protocol

from app.escalation.models import EscalationBrief, TranscriptTurn
from app.memory.schema import LeftBrain, RightBrain

SUMMARIZER_SYSTEM_PROMPT = """You write a short handoff brief for a human sales rep taking over a live call from an AI agent. Given the transcript and the qualification state gathered so far, respond with ONLY a JSON object with exactly these keys: "issue" (what the customer is asking about/needs, one sentence), "blocker" (what the AI agent couldn't resolve, one sentence), "sentiment" (one or two words), "recommended_action" (what the human should do first, one sentence). No prose outside the JSON."""


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


class AnthropicSummarizerClient:
    def __init__(self, api_key: str, model: str):
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        response = client.messages.create(
            model=self._model,
            max_tokens=300,
            system=SUMMARIZER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )


def _default_client() -> LLMClient:
    from app.config import get_settings

    settings = get_settings()
    return AnthropicSummarizerClient(api_key=settings.anthropic_api_key, model=settings.anthropic_model)


def _build_prompt(
    transcript: list[TranscriptTurn], left_brain: LeftBrain, right_brain: RightBrain, reason: str
) -> str:
    transcript_text = "\n".join(f"{t.role}: {t.content}" for t in transcript[-20:])
    return (
        f"Escalation reason: {reason}\n\n"
        f"Qualification so far: {left_brain.model_dump_json()}\n"
        f"Objections/sentiment so far: {right_brain.model_dump_json()}\n\n"
        f"Transcript (most recent turns):\n{transcript_text}"
    )


def heuristic_brief(
    transcript: list[TranscriptTurn], left_brain: LeftBrain, right_brain: RightBrain, reason: str
) -> EscalationBrief:
    """Deterministic, no-LLM fallback — used when the LLM call fails/is unavailable,
    and directly by tests that don't want to exercise the LLM path."""
    unresolved = [o for o in right_brain.objections if not o.resolved]
    blocker = (
        f"Unresolved {unresolved[0].topic} objection: {unresolved[0].raised_text}"
        if unresolved
        else reason
    )
    last_user_line = next((t.content for t in reversed(transcript) if t.role == "user"), reason)
    return EscalationBrief(
        issue=last_user_line,
        blocker=blocker,
        sentiment=right_brain.sentiment,
        recommended_action="Review qualification details and continue the conversation live.",
    )


def summarize(
    transcript: list[TranscriptTurn],
    left_brain: LeftBrain,
    right_brain: RightBrain,
    reason: str,
    *,
    client: LLMClient | None = None,
) -> EscalationBrief:
    active_client = client or _default_client()
    prompt = _build_prompt(transcript, left_brain, right_brain, reason)
    try:
        raw = active_client.complete(prompt)
        data = json.loads(raw)
        return EscalationBrief(**data)
    except Exception:
        return heuristic_brief(transcript, left_brain, right_brain, reason)
