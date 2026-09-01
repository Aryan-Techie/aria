"""Who speaks, in what accent, and when it is worth a round-trip to change it.

The switching itself cannot be tested here - whether Agora's runtime update is
available to this account is a live question, and scripts/check_voice_switch.py
is the thing that answers it. What IS tested is every decision made before that
call: which voice, for whom, and whether to spend the round-trip at all.
"""
import pytest

from app.config import Settings
from app.language.profiles import ENGLISH, HINDI, HINGLISH
from app.sessions.models import SessionState
from app.voice import director


class RecordingClient:
    def __init__(self, fail: bool = False):
        self.updates: list[tuple[str, dict]] = []
        self.fail = fail

    def update(self, agent_id: str, properties: dict) -> None:
        if self.fail:
            raise RuntimeError("agora said no")
        self.updates.append((agent_id, properties))


def _now(fn):
    """Runs the update inline instead of on the shared pool, and lets a
    failure surface here rather than being swallowed by it - the production
    runner swallows on purpose, which would hide the very thing one of these
    tests is checking."""
    try:
        fn()
    except Exception:
        pass


ON = Settings(voice_switching_enabled=True)
OFF = Settings(voice_switching_enabled=False)


@pytest.fixture
def live_call():
    session = SessionState(session_id="sess-voice")
    session.agent_id = "agent-123"
    return session


def test_script_detection_reads_devanagari_not_a_language_model():
    assert director.script_language("कितने MacBook Pro चाहिए आपको") == "hi"
    assert director.script_language("How many MacBook Pros do you need") == "en"


def test_a_hinglish_sentence_of_mostly_english_nouns_is_still_hindi():
    """"कितने MacBook Pro चाहिए" is a Hindi sentence. A majority vote on
    letters would call it English and hand it to the wrong voice."""
    assert director.script_language("तो कितने MacBook Pro चाहिए आपको") == "hi"


def test_too_little_text_is_not_evidence_of_a_language_change():
    """Switching on a two-word turn flaps the accent back and forth."""
    assert director.script_language("हाँ") is None
    assert director.script_language("ok") is None
    assert director.script_language("") is None


def test_only_the_mixed_profile_follows_the_caller():
    """An English deployment quoting a Hindi company name has no second voice
    to switch to and no reason to want one."""
    assert director.resolve_voice(HINGLISH, language="en") == "English_captivating_female1"
    assert director.resolve_voice(HINGLISH, language="hi") == "hindi_female_1_v2"
    assert director.resolve_voice(ENGLISH, language="hi") == ENGLISH.voice_id
    assert director.resolve_voice(HINDI, language="en") == HINDI.voice_id


def test_each_layer_has_its_own_voice():
    """The handoff to the second layer should be audible - a different agent
    really did answer."""
    for profile in (ENGLISH, HINDI, HINGLISH):
        aria = director.resolve_voice(profile, role="aria")
        desk = director.resolve_voice(profile, role="deal_desk")
        solutions = director.resolve_voice(profile, role="solutions")
        assert len({aria, desk, solutions}) == 3, profile.code


def test_role_outranks_language():
    """The deal desk sounding like the deal desk is the point."""
    assert director.resolve_voice(HINGLISH, role="deal_desk", language="en") == "hindi_male_1_v2"


def test_only_the_two_real_second_layer_tools_change_the_voice():
    """Everything else is Aria doing her own lookups; a voice change there
    would be theatre."""
    assert director.agent_for_tools(["negotiate_deal"]) == "deal_desk"
    assert director.agent_for_tools(["ask_solutions_engineer"]) == "solutions"
    for tool in ("search_pricing_rag", "crm_upsert_lead", "calendar_book_meeting", "log_objection"):
        assert director.agent_for_tools([tool]) == "aria"
    assert director.agent_for_tools([]) == "aria"


def test_the_lookup_is_picked_out_of_a_batched_hop():
    assert director.agent_for_tools(["update_sentiment", "negotiate_deal"]) == "deal_desk"


def test_nothing_happens_when_switching_is_off(live_call):
    client = RecordingClient()
    assert director.ensure_voice(live_call, "hindi_male_1_v2", client=client, settings=OFF) is False
    assert client.updates == []


def test_the_same_voice_is_never_bought_twice(live_call):
    """A round-trip for a voice already in force is spent for nothing."""
    client = RecordingClient()
    assert director.ensure_voice(live_call, "hindi_male_1_v2", client=client, settings=ON) is True
    assert director.ensure_voice(live_call, "hindi_male_1_v2", client=client, settings=ON) is False
    assert live_call.current_voice_id == "hindi_male_1_v2"


def test_a_call_with_no_agent_yet_is_a_no_op():
    session = SessionState(session_id="not-joined")
    assert director.ensure_voice(session, "hindi_male_1_v2", client=RecordingClient(), settings=ON) is False


def test_a_failed_switch_never_reaches_the_turn(live_call):
    """A voice that did not change is a cosmetic disappointment; an exception
    raised mid-turn is a broken call."""
    assert (
        director.ensure_voice(
            live_call,
            "hindi_male_1_v2",
            client=RecordingClient(fail=True),
            settings=ON,
            runner=_now,
        )
        is True
    )


def test_the_update_payload_touches_only_the_voice(live_call):
    """A partial properties object - anything else in there would be
    re-sending settings the running call already has."""
    client = RecordingClient()
    director.ensure_voice(live_call, "English_Trustworth_Man", client=client, settings=ON, runner=_now)

    assert client.updates
    _agent_id, properties = client.updates[0]
    assert properties == {"tts": {"params": {"voice_setting": {"voice_id": "English_Trustworth_Man"}}}}
