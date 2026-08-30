"""Deterministic escalation guardrails, checked every turn in the orchestrator
pipeline alongside the LLM's own `escalate_to_human` tool-call judgment — the
LLM's discretion is a signal, not the only path to escalation.
"""
from app.memory.schema import RightBrain

FRUSTRATION_STREAK_LEN = 2
OBJECTION_MAX_ATTEMPTS = 3
LOW_CONFIDENCE_THRESHOLD = 0.15  # TF-IDF score scale — recalibrate once real calls are logged


def frustration_streak(right_brain: RightBrain, streak_len: int = FRUSTRATION_STREAK_LEN) -> bool:
    history = right_brain.sentiment_history
    if len(history) < streak_len:
        return False
    recent = history[-streak_len:]
    return all(s in ("skeptical", "frustrated") for s in recent)


def objection_retry_exceeded(
    right_brain: RightBrain, max_attempts: int = OBJECTION_MAX_ATTEMPTS
):
    for objection in right_brain.objections:
        if not objection.resolved and objection.attempts >= max_attempts:
            return objection
    return None


def low_rag_confidence(score: float, threshold: float = LOW_CONFIDENCE_THRESHOLD) -> bool:
    return score < threshold


def check_triggers(
    right_brain: RightBrain, last_rag_score: float | None = None
) -> tuple[bool, str | None]:
    """Returns (should_escalate, trigger_source)."""
    if frustration_streak(right_brain):
        return True, "frustration_streak"

    objection = objection_retry_exceeded(right_brain)
    if objection is not None:
        return True, "objection_retry"

    if last_rag_score is not None and low_rag_confidence(last_rag_score):
        return True, "low_confidence"

    return False, None
