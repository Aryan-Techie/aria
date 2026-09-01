"""The wrap-up a human gets when a call ends.

Deliberately not the escalation brief. That one answers "why am I being pulled
into a live call"; this one answers "what happened on a call I was not on, and
what do I have to do about it" - and it is produced for *every* call, not only
the ones that went wrong. A qualified lead nobody was told about is the same
as no lead.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Urgency = Literal["now", "today", "this_week", "none"]


class CallSummary(BaseModel):
    session_id: str
    lead_id: str | None = None
    company: str | None = None
    contact: str | None = None
    outcome: str = "follow_up"

    # One line of narrative. The only part written by a model, and it is
    # allowed to fail - see builder.heuristic_headline.
    headline: str = ""
    recommended_action: str = ""
    urgency: Urgency = "this_week"

    # Everything below is read off the record rather than summarised out of
    # the transcript, so the wrap-up can only contain things that were really
    # captured. A rep acting on an invented detail is worse off than a rep
    # with a thin summary.
    facts: list[str] = Field(default_factory=list)
    agreed: list[str] = Field(default_factory=list)
    owed: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    duration_seconds: int = 0
    turn_count: int = 0
    minutes_saved: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def as_text(self) -> str:
        """Plain text, for an email body and for the CRM note. Kept here so
        Slack, email and the CRM cannot drift into three different accounts of
        the same call."""
        who = " / ".join(filter(None, [self.company, self.contact])) or "Unknown caller"
        lines = [
            f"{who} - {self.outcome.replace('_', ' ')}",
            "",
            self.headline,
            "",
            f"Do next ({self.urgency.replace('_', ' ')}): {self.recommended_action}",
        ]
        for title, items in (
            ("What they need", self.facts),
            ("What was agreed", self.agreed),
            ("What we owe them", self.owed),
            ("Watch out for", self.risks),
        ):
            if items:
                lines += ["", f"{title}:", *(f"- {item}" for item in items)]
        lines += [
            "",
            f"Call length {self.duration_seconds // 60}m {self.duration_seconds % 60}s, "
            f"{self.turn_count} turns, handled end to end by Aria.",
        ]
        return "\n".join(lines)
