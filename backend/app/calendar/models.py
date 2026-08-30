import uuid
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class Slot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start: datetime
    end: datetime
    rep_name: str
    booked: bool = False


class Booking(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    slot_id: str
    lead_id: str
    session_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SlotTakenError(Exception):
    pass
