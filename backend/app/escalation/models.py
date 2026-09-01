import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.memory.schema import LeftBrain, RightBrain

TriggerSource = Literal[
    "llm", "frustration_streak", "objection_retry", "low_confidence", "deal_approval"
]

# A handoff ends the call; an approval request does not. The customer stays
# with Aria while a human answers one question about margin, so the two share
# the inbox and the brief but not the session lifecycle - see
# tools/executor.py::_negotiate_deal.
EscalationKind = Literal["handoff", "deal_approval"]


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
    kind: EscalationKind = "handoff"
    # Set on a deal_approval once a person has answered it.
    resolved_at: datetime | None = None
    approved_pct: float | None = None
    approved_by: str | None = None
    brief: EscalationBrief
    transcript: list[TranscriptTurn] = Field(default_factory=list)
    left_brain: LeftBrain
    right_brain: RightBrain
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
