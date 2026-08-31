from app.sessions.models import SessionState
from app.tools import executor


def _session(session_id: str = "sess-exec") -> SessionState:
    return SessionState(session_id=session_id, mem0_user_id=session_id)


def test_search_pricing_rag_sets_last_rag_score():
    session = _session()
    result = executor.dispatch("search_pricing_rag", {"query": "enterprise pricing"}, session)
    assert result["chunks"]
    assert session.last_rag_score is not None and session.last_rag_score > 0


def test_crm_upsert_lead_updates_left_brain_and_session_lead_id():
    session = _session()
    result = executor.dispatch(
        "crm_upsert_lead", {"company": "Acme", "user_count": 10}, session
    )
    assert session.crm_lead_id == result["lead_id"]
    assert session.left_brain.company == "Acme"
    assert session.left_brain.user_count == 10

    # requirement change: 10 -> 50, no restart, same lead_id
    result2 = executor.dispatch("crm_upsert_lead", {"user_count": 50}, session)
    assert result2["lead_id"] == result["lead_id"]
    assert session.left_brain.user_count == 50
    assert session.left_brain.company == "Acme"  # untouched field preserved


def test_calendar_book_meeting_sets_outcome_and_booking_id():
    session = _session()
    avail = executor.dispatch("calendar_check_availability", {}, session)
    slot_id = avail["slots"][0]["id"]

    result = executor.dispatch("calendar_book_meeting", {"slot_id": slot_id}, session)

    assert "error" not in result
    assert session.outcome == "meeting_booked"
    assert session.booking_id == result["booking_id"]
    assert session.crm_lead_id is not None


def test_calendar_book_meeting_creates_lead_if_none_exists_yet():
    session = _session()
    assert session.crm_lead_id is None
    avail = executor.dispatch("calendar_check_availability", {}, session)
    slot_id = avail["slots"][0]["id"]

    result = executor.dispatch("calendar_book_meeting", {"slot_id": slot_id}, session)
    assert "error" not in result
    assert session.crm_lead_id is not None


def test_calendar_book_meeting_double_booked_returns_error_not_exception():
    session_a = _session("sess-a")
    session_b = _session("sess-b")
    avail = executor.dispatch("calendar_check_availability", {}, session_a)
    slot_id = avail["slots"][0]["id"]

    executor.dispatch("calendar_book_meeting", {"slot_id": slot_id}, session_a)
    result = executor.dispatch("calendar_book_meeting", {"slot_id": slot_id}, session_b)

    assert "error" in result


def test_escalate_to_human_sets_session_status_and_outcome():
    session = _session()
    result = executor.dispatch(
        "escalate_to_human", {"reason": "wants a human"}, session, trigger_source="llm"
    )
    assert session.status == "escalated"
    assert session.outcome == "escalated"
    assert "escalation_id" in result


def test_log_objection_creates_then_increments_attempts():
    session = _session()
    first = executor.dispatch(
        "log_objection", {"topic": "pricing", "raised_text": "too expensive"}, session
    )
    assert first["attempts"] == 1
    second = executor.dispatch(
        "log_objection", {"topic": "pricing", "raised_text": "still too expensive"}, session
    )
    assert second["attempts"] == 2
    assert len(session.right_brain.objections) == 1  # same unresolved objection, not duplicated


def test_log_objection_resolved_stops_incrementing_new_unresolved_entry():
    session = _session()
    executor.dispatch("log_objection", {"topic": "trust", "raised_text": "worried about security"}, session)
    executor.dispatch(
        "log_objection",
        {"topic": "trust", "raised_text": "worried about security", "resolved": True, "resolution_text": "explained SOC2"},
        session,
    )
    assert session.right_brain.objections[0].resolved is True

    # a fresh trust objection after the prior one is resolved should create a new entry
    executor.dispatch("log_objection", {"topic": "trust", "raised_text": "new trust concern"}, session)
    assert len(session.right_brain.objections) == 2


def test_update_sentiment_appends_history():
    session = _session()
    executor.dispatch("update_sentiment", {"sentiment": "skeptical"}, session)
    executor.dispatch("update_sentiment", {"sentiment": "frustrated"}, session)
    assert session.right_brain.sentiment == "frustrated"
    assert session.right_brain.sentiment_history == ["skeptical", "frustrated"]


def test_unknown_tool_returns_error_dict_not_exception():
    session = _session()
    result = executor.dispatch("not_a_real_tool", {}, session)
    assert "error" in result


def test_availability_slots_carry_a_preformatted_label():
    """Stamping today's date into the system prompt was not enough: asked for
    Monday 7 September 2026 the model said "Sunday the seventh", and called
    1 September "the second". Handing it the finished phrase removes the
    arithmetic rather than asking it to be careful."""
    from datetime import datetime

    from app.sessions.models import SessionState
    from app.tools import executor

    session = SessionState(session_id="s", channel_name="c")
    result = executor.dispatch("calendar_check_availability", {}, session)

    assert result["slots"], "expected seeded slots"
    for slot in result["slots"]:
        start = datetime.fromisoformat(slot["start"].replace("Z", "+00:00"))
        assert slot["label"].startswith(start.strftime("%A")), slot["label"]
        # The platform-specific no-padding flag must not leak through as text.
        assert "%" not in slot["label"]
        assert "-" not in slot["label"]
