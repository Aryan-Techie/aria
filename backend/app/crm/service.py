from datetime import datetime, timezone

from app.crm.models import DecisionStage, Lead, LeadStatus
from app.crm.store import LeadStore, lead_store


def _now() -> datetime:
    return datetime.now(timezone.utc)


def upsert_lead(
    session_id: str,
    *,
    company: str | None = None,
    user_count: int | None = None,
    budget_range: str | None = None,
    timeline: str | None = None,
    pain_points: list[str] | None = None,
    decision_stage: DecisionStage | None = None,
    name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    store: LeadStore = lead_store,
) -> Lead:
    """Create-or-update the lead tied to this call session.

    Only non-None fields overwrite existing values, so a later call with just
    `user_count=50` doesn't clobber previously captured fields — this is what
    makes "10 -> 50 users, re-derive pricing, no restart" a plain field
    overwrite rather than a rebuild of the whole record.
    """
    lead = store.get_by_session(session_id)
    if lead is None:
        lead = Lead(session_id=session_id)

    if company is not None:
        lead.company = company
    if user_count is not None:
        lead.user_count = user_count
    if budget_range is not None:
        lead.budget_range = budget_range
    if timeline is not None:
        lead.timeline = timeline
    if pain_points:
        # merge, de-duplicate, preserve order
        merged = lead.pain_points + [p for p in pain_points if p not in lead.pain_points]
        lead.pain_points = merged
    if decision_stage is not None:
        lead.decision_stage = decision_stage
    if name is not None:
        lead.name = name
    if email is not None:
        lead.email = email
    if phone is not None:
        lead.phone = phone

    lead.updated_at = _now()
    return store.save(lead)


def qualify_lead(
    session_id: str,
    status: LeadStatus,
    reason: str,
    *,
    store: LeadStore = lead_store,
) -> Lead:
    lead = store.get_by_session(session_id)
    if lead is None:
        lead = Lead(session_id=session_id)
    lead.status = status
    lead.notes.append(reason)
    lead.updated_at = _now()
    return store.save(lead)


def get_lead(session_id: str, *, store: LeadStore = lead_store) -> Lead | None:
    return store.get_by_session(session_id)


def list_leads(*, store: LeadStore = lead_store) -> list[Lead]:
    return store.all()


def set_outcome(session_id: str, outcome: str, *, store: LeadStore = lead_store) -> Lead | None:
    """Called at call-end time once the definitive outcome (with precedence
    resolved across booking/escalation/qualification) is known — see
    sessions/controller.py::_resolve_outcome."""
    lead = store.get_by_session(session_id)
    if lead is None:
        return None
    lead.outcome = outcome
    lead.updated_at = _now()
    return store.save(lead)
