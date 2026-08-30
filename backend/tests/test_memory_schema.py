from app.memory.schema import LeftBrain, Objection, RightBrain


def test_left_brain_defaults_are_empty():
    lb = LeftBrain()
    assert lb.company is None
    assert lb.pain_points == []
    assert lb.decision_stage is None


def test_right_brain_defaults_are_neutral():
    rb = RightBrain()
    assert rb.sentiment == "neutral"
    assert rb.objections == []
    assert rb.sentiment_history == []


def test_objection_requires_topic_and_raised_text():
    o = Objection(topic="pricing", raised_text="too expensive")
    assert o.resolved is False
    assert o.attempts == 1


def test_left_brain_round_trips_through_json():
    lb = LeftBrain(company="Acme", user_count=50, pain_points=["slow onboarding"], decision_stage="evaluating")
    restored = LeftBrain.model_validate_json(lb.model_dump_json())
    assert restored == lb
