import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.memory.schema import LeftBrain, RightBrain

TriggerSource = Literal["llm", "frustration_streak", "objection_retry", "low_confidence"]


class TranscriptTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class EscalationBrief(BaseModel):
    issue: str
    blocker: str
    sentiment: str
    recommended_action: str


class EscalationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    lead_id: str | None = None
    reason: str
    trigger_source: TriggerSource
    brief: EscalationBrief
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    left_brain: LeftBrain
    right_brain: RightBrain
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
