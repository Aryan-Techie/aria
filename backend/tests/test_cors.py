"""Regression test for a real bug caught by manually running the app: the
frontend (localhost:3000) and backend (localhost:8000) are different origins,
and without CORS headers the browser blocks every fetch outright with
'Failed to fetch' — silently, with no server-side error to debug from."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_allowed_origin_gets_cors_header():
    response = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_preflight_request_is_allowed_for_configured_origin():
    response = client.options(
        "/api/call/start",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


def test_unhandled_exception_still_carries_cors_header():
    """Without the global exception handler in app/main.py, this response
    comes back from Starlette's ServerErrorMiddleware and silently drops the
    CORS header — the browser then reports a generic 'Failed to fetch' with
    no way to see the real 500 underneath. Caught by manually running the
    app: /api/call/start raises (no real Agora credentials in dev), and the
    frontend showed a CORS error instead of the actual failure reason."""
    # /api/call/start raises with no Agora credentials configured (default
    # empty Settings in the test environment) — that's the real bug repro.
    response = client.post("/api/call/start", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 500
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "error" in response.json()
