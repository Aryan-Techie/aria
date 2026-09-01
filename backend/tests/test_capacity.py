"""How many conversations this handles, and whether the number is honest.

Includes the regression test for the bug scripts/capacity_test.py found: the
in-memory stores walked their own dict to build a persistence snapshot while
another live call was writing into it.
"""
import threading
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.calendar.store import calendar_store
from app.crm.models import Lead
from app.crm.store import lead_store
from app.main import app
from app.metrics import capacity
from app.sessions.models import SessionState
from app.sessions.store import session_store

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _call(session_id: str, start_min: int, end_min: int | None, **kwargs) -> SessionState:
    session = SessionState(session_id=session_id, **kwargs)
    session.created_at = NOW + timedelta(minutes=start_min)
    session.ended_at = None if end_min is None else NOW + timedelta(minutes=end_min)
    return session


def test_peak_concurrency_is_the_most_calls_actually_overlapping():
    """Not "calls today". Three calls that never overlap is a peak of one."""
    sequential = [_call("a", 0, 5), _call("b", 6, 10), _call("c", 11, 15)]
    assert capacity.peak_concurrency(sequential, NOW + timedelta(minutes=20)) == 1

    overlapping = [_call("a", 0, 10), _call("b", 2, 12), _call("c", 3, 4)]
    assert capacity.peak_concurrency(overlapping, NOW + timedelta(minutes=20)) == 3


def test_a_call_ending_exactly_as_another_starts_is_not_an_overlap():
    touching = [_call("a", 0, 5), _call("b", 5, 10)]
    assert capacity.peak_concurrency(touching, NOW + timedelta(minutes=20)) == 1


def test_a_still_running_call_counts_up_to_now():
    live = [_call("a", 0, None), _call("b", 1, None)]
    assert capacity.peak_concurrency(live, NOW + timedelta(minutes=5)) == 2


def test_containment_counts_an_escalated_call_against_the_agent():
    """A call that ended with a person being pulled in is not a call the agent
    handled."""
    sessions = [
        _call("a", 0, 5, outcome="meeting_booked"),
        _call("b", 0, 5, outcome="qualified"),
        _call("c", 0, 5, status="escalated", outcome="escalated"),
        _call("d", 0, 5, outcome="follow_up"),
    ]
    snapshot = capacity.snapshot(sessions, NOW + timedelta(minutes=10))
    assert snapshot["escalated_to_human"] == 1
    assert snapshot["containment_rate"] == 0.75


def test_peak_concurrency_is_the_headcount_comparison():
    sessions = [_call(str(i), 0, 5) for i in range(7)]
    snapshot = capacity.snapshot(sessions, NOW + timedelta(minutes=10))
    assert snapshot["peak_concurrent_calls"] == 7
    # A person holds exactly one voice conversation at a time. That is the
    # whole comparison.
    assert snapshot["reps_needed_for_peak"] == 7


def test_talk_time_and_admin_are_reported_apart_not_merged():
    session = _call("a", 0, 30)
    session.tool_calls = ["crm_upsert_lead", "calendar_book_meeting"]
    snapshot = capacity.snapshot([session], NOW + timedelta(minutes=40))
    minutes = snapshot["human_minutes"]
    assert minutes["talk_time"] == 30.0
    assert minutes["post_call_admin"] == 14.0
    assert minutes["total"] == 44.0
    assert snapshot["rep_days_saved"] == round(44.0 / 480, 2)


def test_the_assumptions_are_returned_with_the_numbers():
    """A derived figure whose assumptions are hidden is one a judge is right
    to distrust."""
    snapshot = capacity.snapshot([_call("a", 0, 5)], NOW)
    assert snapshot["assumptions"]["rep_minutes_per_day"] == 480
    assert snapshot["assumptions"]["human_concurrent_calls"] == 1
    assert "crm_upsert_lead" in snapshot["assumptions"]["baseline_minutes_per_action"]


def test_an_empty_deployment_reports_zeros_rather_than_dividing_by_zero():
    snapshot = capacity.snapshot([], NOW)
    assert snapshot["calls_total"] == 0
    assert snapshot["containment_rate"] == 0.0
    assert snapshot["peak_concurrent_calls"] == 0


def test_capacity_is_readable_over_http():
    session_store.save(_call("live-1", 0, None))
    body = TestClient(app).get("/api/metrics/capacity").json()
    assert body["calls_total"] == 1
    assert "assumptions" in body


def _hammer(store_write, store_read, iterations: int = 400) -> list[Exception]:
    """Writes and reads a store from two threads at once and collects whatever
    it throws."""
    errors: list[Exception] = []
    stop = threading.Event()

    def writer():
        for i in range(iterations):
            try:
                store_write(i)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)
        stop.set()

    def reader():
        while not stop.is_set():
            try:
                store_read()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return errors


def test_concurrent_calls_do_not_corrupt_the_lead_store():
    """Regression: scripts/capacity_test.py at 256 concurrent calls hit
    "dictionary changed size during iteration" - _persist walked the dict to
    build its snapshot while another call's save() inserted into it. Every
    live call is its own thread, so this was always reachable; it just needed
    enough calls at once to be hit."""
    errors = _hammer(
        lambda i: lead_store.save(Lead(session_id=f"race-{i}")),
        lead_store.all,
    )
    assert errors == []


def test_concurrent_calls_do_not_corrupt_the_session_store():
    errors = _hammer(
        lambda i: session_store.save(SessionState(session_id=f"race-{i}")),
        session_store.all,
    )
    assert errors == []


def test_concurrent_calls_do_not_corrupt_the_calendar_store():
    slot = calendar_store.all_slots()[0]
    errors = _hammer(lambda i: calendar_store.save_slot(slot), calendar_store.all_slots)
    assert errors == []
