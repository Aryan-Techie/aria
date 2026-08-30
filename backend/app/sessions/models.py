from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.escalation.models import TranscriptTurn
from app.memory.schema import LeftBrain, RightBrain

SessionStatus = Literal["active", "ended", "escalated"]
Outcome = Literal["meeting_booked", "escalated", "qualified", "disqualified", "follow_up"]


class SessionState(BaseModel):
    session_id: str
    agora_channel: str | None = None
    agent_id: str | None = None

    crm_lead_id: str | None = None
    booking_id: str | None = None
    mem0_user_id: str | None = None  # defaults to session_id once memory (Step 4) is wired in

    status: SessionStatus = "active"
    outcome: Outcome | None = None

    transcript: list[TranscriptTurn] = Field(default_factory=list)
    # Append-only log of the same envelopes published to RTM, so the browser
    # can poll for them over plain HTTP (GET /api/session/{id}/events). RTM
    # delivery to the UI proved unreliable; the panels are cosmetic, so they
    # get a transport we fully control rather than one we cannot debug.
    events: list[dict] = Field(default_factory=list)
    left_brain: LeftBrain = Field(default_factory=LeftBrain)
    right_brain: RightBrain = Field(default_factory=RightBrain)
    last_rag_score: float | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
