import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Task(BaseModel):
    """A follow-up for a rep to act on later - distinct from a Meeting,
    which is a real calendar hold. "Send the case study Thursday" or "call
    back after they've talked to their CFO" aren't meetings; without this
    they had nowhere to live except a lead note nobody reads."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    lead_id: str | None = None
    note: str
    due: str | None = None
    completed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
