import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

LeadStatus = Literal["new", "qualified", "disqualified", "meeting_booked", "escalated"]
DecisionStage = Literal["discovery", "evaluating", "ready_to_buy", "not_a_fit"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str | None = None

    name: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None

    user_count: int | None = None
    budget_range: str | None = None
    timeline: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    decision_stage: DecisionStage | None = None

    status: LeadStatus = "new"
    outcome: str | None = None
    notes: list[str] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
