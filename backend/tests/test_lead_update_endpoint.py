from fastapi.testclient import TestClient

from app.main import app
from app.sessions.store import session_store

client = TestClient(app)


def test_manual_edit_writes_the_crm_and_the_live_session():
    session = session_store.get_or_create("sess-manual-1")

    resp = client.patch(
        "/api/session/sess-manual-1/lead",
        json={"name": "Priya", "email": "priya@northwind.example", "industry": "Logistics"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["lead"]["name"] == "Priya"
    assert body["lead"]["email"] == "priya@northwind.example"

    # The point of the endpoint: Aria's own next-turn view already has it.
    assert session.left_brain.name == "Priya"
    assert session.left_brain.email == "priya@northwind.example"
    assert session.left_brain.industry == "Logistics"


def test_partial_edit_does_not_clobber_existing_fields():
    session = session_store.get_or_create("sess-manual-2")
    client.patch("/api/session/sess-manual-2/lead", json={"name": "Sam", "company": "Acme"})

    client.patch("/api/session/sess-manual-2/lead", json={"phone": "555-0100"})

    assert session.left_brain.name == "Sam"
    assert session.left_brain.company == "Acme"
    assert session.left_brain.phone == "555-0100"


def test_unknown_session_is_404():
    resp = client.patch("/api/session/does-not-exist/lead", json={"name": "Priya"})
    assert resp.status_code == 404
