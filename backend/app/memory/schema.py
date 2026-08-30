"""Dual-brain qualification/objection schema.

LeftBrain = deterministic, CRM-shaped facts (mirrors app.crm.models.Lead's
qualification fields — the source of truth the tools write to directly).
RightBrain = softer signals (objections, sentiment, competitor mentions) that
drive escalation guardrails and demo-panel color, not the CRM record itself.
"""
from typing import Literal

from pydantic import BaseModel, Field

from app.crm.models import DecisionStage

Sentiment = Literal["positive", "neutral", "skeptical", "frustrated"]
ObjectionTopic = Literal["pricing", "trust", "product"]


class LeftBrain(BaseModel):
    company: str | None = None
    user_count: int | None = None
    budget_range: str | None = None
    timeline: str | None = None
    pain_points: list[str] = Field(default_factory=list)
    decision_stage: DecisionStage | None = None


class Objection(BaseModel):
    topic: ObjectionTopic
    raised_text: str
    resolution_text: str | None = None
    resolved: bool = False
    attempts: int = 1


class RightBrain(BaseModel):
    objections: list[Objection] = Field(default_factory=list)
    sentiment: Sentiment = "neutral"
    sentiment_history: list[Sentiment] = Field(default_factory=list)
    competitor_mentions: list[str] = Field(default_factory=list)
