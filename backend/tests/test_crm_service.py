from app.crm import service
from app.crm.store import LeadStore


def test_upsert_lead_creates_new_lead():
    store = LeadStore()
    lead = service.upsert_lead("sess-1", company="Acme", user_count=10, store=store)
    assert lead.company == "Acme"
    assert lead.user_count == 10
    assert lead.session_id == "sess-1"
    assert store.get_by_session("sess-1").id == lead.id


def test_upsert_lead_overwrites_only_provided_fields():
    store = LeadStore()
    service.upsert_lead("sess-1", company="Acme", user_count=10, store=store)
    updated = service.upsert_lead("sess-1", user_count=50, store=store)

    assert updated.user_count == 50
    assert updated.company == "Acme"  # untouched field preserved


def test_upsert_lead_merges_pain_points_without_duplicates():
    store = LeadStore()
    service.upsert_lead("sess-1", pain_points=["slow onboarding"], store=store)
    updated = service.upsert_lead(
        "sess-1", pain_points=["slow onboarding", "no reporting"], store=store
    )
    assert updated.pain_points == ["slow onboarding", "no reporting"]


def test_qualify_lead_sets_status_and_note():
    store = LeadStore()
    service.upsert_lead("sess-1", company="Acme", store=store)
    lead = service.qualify_lead("sess-1", "qualified", "clear budget and timeline", store=store)
    assert lead.status == "qualified"
    assert "clear budget and timeline" in lead.notes


def test_list_leads_includes_seed_fixtures():
    store = LeadStore()
    leads = service.list_leads(store=store)
    assert len(leads) == 3
    assert any(lead.company == "Vantiq Health" for lead in leads)
