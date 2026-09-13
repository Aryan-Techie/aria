from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.routes import admin


def _client() -> TestClient:
    # A fresh client per test - each gets its own cookie jar, so one test's
    # session can't leak into the next.
    return TestClient(app)


def test_no_password_required_when_unset():
    """Off until configured - a fresh checkout isn't locked out of its own
    dashboard, same posture as CRM_BACKEND/EMAIL_ENABLED."""
    resp = _client().get("/api/leads")
    assert resp.status_code == 200


def test_dashboard_endpoints_reject_missing_or_wrong_session(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(dashboard_password="letmein"))
    client = _client()

    no_cookie = client.get("/api/leads")
    assert no_cookie.status_code == 401

    login_wrong = client.post("/api/dashboard/login", json={"password": "nope"})
    assert login_wrong.status_code == 401
    # A failed login must not set a session cookie.
    assert admin._DASHBOARD_COOKIE not in client.cookies


def test_login_then_dashboard_endpoints_succeed(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(dashboard_password="letmein"))
    client = _client()

    login = client.post("/api/dashboard/login", json={"password": "letmein"})
    assert login.status_code == 200
    assert admin._DASHBOARD_COOKIE in client.cookies

    # The cookie rides along automatically on the client's later requests.
    resp = client.get("/api/leads")
    assert resp.status_code == 200


def test_a_stray_or_tampered_cookie_is_rejected(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(dashboard_password="letmein"))
    client = _client()
    client.cookies.set(admin._DASHBOARD_COOKIE, "not-a-real-token")
    assert client.get("/api/leads").status_code == 401


def test_capacity_and_calendar_never_need_a_session(monkeypatch):
    """The live console depends on these without ever knowing a dashboard
    password exists - locking them would break real calls, not just the
    dashboard."""
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(dashboard_password="letmein"))
    client = _client()

    assert client.get("/api/metrics/capacity").status_code == 200
    assert client.get("/api/calendar/slots").status_code == 200


def test_repeated_failed_logins_are_rate_limited(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(dashboard_password="letmein"))
    # Isolate this test's attempt history from any other test's IP bucket.
    admin._failed_attempts.clear()
    client = _client()

    for _ in range(admin._RATE_LIMIT_MAX_ATTEMPTS):
        resp = client.post("/api/dashboard/login", json={"password": "nope"})
        assert resp.status_code == 401

    limited = client.post("/api/dashboard/login", json={"password": "nope"})
    assert limited.status_code == 429

    # The right password doesn't bypass an active lockout.
    still_limited = client.post("/api/dashboard/login", json={"password": "letmein"})
    assert still_limited.status_code == 429


def test_a_successful_login_clears_the_failure_count(monkeypatch):
    monkeypatch.setattr(admin, "get_settings", lambda: Settings(dashboard_password="letmein"))
    admin._failed_attempts.clear()
    client = _client()

    client.post("/api/dashboard/login", json={"password": "nope"})
    client.post("/api/dashboard/login", json={"password": "nope"})
    ok = client.post("/api/dashboard/login", json={"password": "letmein"})
    assert ok.status_code == 200
    assert all(not v for v in admin._failed_attempts.values())
