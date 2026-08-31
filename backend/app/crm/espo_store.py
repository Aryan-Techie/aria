"""A LeadStore backed by a real EspoCRM instance.

Drop-in for the in-memory LeadStore: same four methods the service layer uses
(`get_by_session`, `save`, `all`, `get`), so `crm/service.py` is untouched and
the qualification logic it holds - "only non-None fields overwrite", the
pain-point merge - keeps working unchanged.

Field naming
------------
EspoCRM prefixes every custom field with "c", so the field provisioned as
`ariaUserCount` is addressed as `cAriaUserCount`. Writing the unprefixed name
is accepted with a 200 and silently discarded, which is a genuinely nasty
failure mode: the call looks like it worked and the value simply never
appears. `_CUSTOM` below is the single source of truth for those names.

Failure policy
--------------
A CRM write happens on the turn path, mid-call. If EspoCRM is down, slow, or
rejects a field, the customer must not hear dead air or an apology about a
CRM - so every failure is logged and swallowed, and the call continues. That
is a deliberate trade: a lost CRM row is recoverable, a broken call is not.
"""
from __future__ import annotations

import logging

from app.crm.espo_client import EspoClient, EspoCRMError
from app.crm.models import Lead

logger = logging.getLogger("aria")

_ENTITY = "Lead"

# our field -> EspoCRM custom field (see scripts/provision_crm.py)
_CUSTOM = {
    "session_id": "cAriaSessionId",
    "user_count": "cAriaUserCount",
    "budget_range": "cAriaBudgetRange",
    "timeline": "cAriaTimeline",
    "decision_stage": "cAriaDecisionStage",
    "outcome": "cAriaOutcome",
    "pain_points": "cAriaPainPoints",
}

# Our lifecycle -> EspoCRM's stock Lead status enum. Espo only accepts these
# six values, so this cannot be a passthrough.
_STATUS_TO_ESPO = {
    "new": "New",
    "qualified": "In Process",
    "meeting_booked": "Converted",
    "disqualified": "Dead",
    "escalated": "Assigned",
}
_STATUS_FROM_ESPO = {
    "New": "new",
    "Assigned": "escalated",
    "In Process": "qualified",
    "Converted": "meeting_booked",
    "Dead": "disqualified",
    "Recycled": "new",
}


def _to_espo(lead: Lead) -> dict:
    payload: dict = {
        # Espo requires a lastName on every Lead. The company is the useful
        # label on a B2B call where a name often never comes up at all.
        "lastName": lead.name or lead.company or "Unknown caller",
        "status": _STATUS_TO_ESPO.get(lead.status, "New"),
        _CUSTOM["session_id"]: lead.session_id,
    }
    if lead.company:
        payload["accountName"] = lead.company
    if lead.email:
        payload["emailAddress"] = lead.email
    if lead.phone:
        payload["phoneNumber"] = lead.phone
    if lead.user_count is not None:
        payload[_CUSTOM["user_count"]] = lead.user_count
    if lead.budget_range:
        payload[_CUSTOM["budget_range"]] = lead.budget_range
    if lead.timeline:
        payload[_CUSTOM["timeline"]] = lead.timeline
    if lead.decision_stage:
        payload[_CUSTOM["decision_stage"]] = lead.decision_stage
    if lead.outcome:
        payload[_CUSTOM["outcome"]] = lead.outcome
    if lead.pain_points:
        payload[_CUSTOM["pain_points"]] = "\n".join(f"- {p}" for p in lead.pain_points)
    if lead.notes:
        payload["description"] = "\n".join(lead.notes)
    return payload


def _from_espo(record: dict) -> Lead:
    pain_raw = record.get(_CUSTOM["pain_points"]) or ""
    notes_raw = record.get("description") or ""
    return Lead(
        id=record["id"],
        session_id=record.get(_CUSTOM["session_id"]),
        # NOT record["name"]: that is Espo's computed display field and it is
        # not consistent between responses - on a CREATE it comes back as the
        # ACCOUNT name, on a later GET as the person's name. Reading it made a
        # freshly created lead round-trip with the company as the contact.
        # firstName/lastName are what we actually wrote.
        name=" ".join(filter(None, [record.get("firstName"), record.get("lastName")])) or None,
        company=record.get("accountName"),
        email=record.get("emailAddress"),
        phone=record.get("phoneNumber"),
        user_count=record.get(_CUSTOM["user_count"]),
        budget_range=record.get(_CUSTOM["budget_range"]),
        timeline=record.get(_CUSTOM["timeline"]),
        decision_stage=record.get(_CUSTOM["decision_stage"]) or None,
        pain_points=[line.lstrip("- ").strip() for line in pain_raw.splitlines() if line.strip()],
        notes=[line for line in notes_raw.splitlines() if line.strip()],
        status=_STATUS_FROM_ESPO.get(record.get("status", "New"), "new"),
        outcome=record.get(_CUSTOM["outcome"]),
    )


class EspoLeadStore:
    """Same surface as LeadStore, talking to EspoCRM instead of a dict."""

    def __init__(self, client: EspoClient) -> None:
        self._client = client
        # session_id -> Espo record id. Purely a round-trip saver; a miss
        # falls back to querying by the session field, so a backend restart
        # mid-call still finds the row it created before the restart.
        self._session_to_record: dict[str, str] = {}

    def get_by_session(self, session_id: str) -> Lead | None:
        record_id = self._session_to_record.get(session_id)
        try:
            if record_id:
                return _from_espo(self._client.get(_ENTITY, record_id))
            found = self._client.find_one(_ENTITY, **{_CUSTOM["session_id"]: session_id})
        except EspoCRMError as exc:
            logger.warning("CRM lookup failed for session=%s: %s", session_id, exc)
            return None

        if not found:
            return None
        self._session_to_record[session_id] = found["id"]
        return _from_espo(found)

    def save(self, lead: Lead) -> Lead:
        payload = _to_espo(lead)
        record_id = self._session_to_record.get(lead.session_id or "")

        try:
            if record_id:
                record = self._client.update(_ENTITY, record_id, payload)
            else:
                record = self._client.create(_ENTITY, payload)
        except EspoCRMError as exc:
            # Never propagate: this runs mid-call, on the turn path.
            logger.error("CRM write failed for session=%s: %s", lead.session_id, exc)
            return lead

        if lead.session_id:
            self._session_to_record[lead.session_id] = record["id"]
        return _from_espo(record)

    def all(self) -> list[Lead]:
        try:
            return [_from_espo(r) for r in self._client.list(_ENTITY, max_size=50)]
        except EspoCRMError as exc:
            logger.warning("CRM list failed: %s", exc)
            return []

    def get(self, lead_id: str) -> Lead | None:
        try:
            return _from_espo(self._client.get(_ENTITY, lead_id))
        except EspoCRMError:
            return None

    def reset(self) -> None:
        """No-op. The in-memory store reseeds fixtures here; wiping a real
        CRM because a test asked for a clean slate is not an equivalent
        action, so this deliberately does nothing."""
        self._session_to_record.clear()
