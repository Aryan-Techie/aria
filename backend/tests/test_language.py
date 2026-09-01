"""Language is five settings that have to agree, not one.

The regression at the top of this file is the whole reason the feature was
needed: `language` was being sent as a sibling of `asr.params` rather than
inside it, Agora drops properties it does not recognise, and so Deepgram ran
on its own English default no matter what ASR_LANGUAGE said. A caller speaking
Hindi came back as English-shaped nonsense and the model answered the
nonsense.
"""
import pytest

from app.agora.join_payload import build_join_payload, warn_on_language_overrides
from app.config import Settings
from app.language.profiles import ENGLISH, HINDI, HINGLISH, get_profile
from app.orchestrator import bridge_lines
from app.tools import prompts

LOOKUP_TOOLS = (
    "search_pricing_rag",
    "calendar_check_availability",
    "calendar_book_meeting",
    "negotiate_deal",
    "ask_solutions_engineer",
)


def _props(**overrides) -> dict:
    settings = Settings(agora_app_id="app123", **overrides)
    return build_join_payload(
        session_id="abcdef1234567890",
        channel_name="aria-abcdef12",
        agent_rtc_uid=1,
        browser_rtc_uid=5551234,
        agent_token="fake-agent-token",
        llm_url="https://example.com/agent/x/v1/chat/completions",
        settings=settings,
    )["properties"]


def test_the_asr_language_goes_inside_params_where_agora_reads_it():
    """Regression. Agora's schema puts `language` in asr.params; sent as a
    sibling of params it is silently dropped, along with every other property
    Agora does not recognise, and the recogniser stays on English."""
    asr = _props(agent_language="hi")["asr"]

    assert asr["params"]["language"] == "hi"
    assert "language" not in asr, "a sibling of params is a setting Agora throws away"


def test_english_stays_exactly_as_it_was():
    """The default must not move. Everything here is the behaviour that was
    already confirmed working on live calls."""
    props = _props()
    assert props["asr"]["params"]["language"] == "en"
    assert props["tts"]["params"]["voice_setting"]["voice_id"] == "English_captivating_female1"
    assert props["tts"]["params"]["voice_setting"]["english_normalization"] is True
    assert "Apple Park" in props["llm"]["greeting_message"]


def test_hindi_switches_the_recogniser_the_voice_and_the_boost_together():
    """Any one of these left English is enough to break the call on its own."""
    props = _props(agent_language="hi")

    assert props["asr"]["params"]["language"] == "hi"
    assert props["tts"]["params"]["voice_setting"]["voice_id"] == "hindi_female_1_v2"
    assert props["tts"]["params"]["language_boost"] == "Hindi"
    # MiniMax documents the normalisation pass as an English/Chinese feature.
    assert props["tts"]["params"]["voice_setting"]["english_normalization"] is False


def test_hinglish_uses_the_multilingual_recogniser_and_lets_minimax_detect():
    """A buyer discussing a device fleet switches language inside a sentence;
    a recogniser pinned to either one mangles the other half."""
    props = _props(agent_language="hinglish")

    assert props["asr"]["params"]["language"] == "multi"
    assert props["tts"]["params"]["language_boost"] == "auto"


def test_language_boost_is_top_level_in_the_minimax_params_not_in_voice_setting():
    """MiniMax puts language_boost at the top of the request body. Agora
    forwards what it does not validate straight through, so the nesting has to
    be MiniMax's, not a guess."""
    params = _props(agent_language="hi")["tts"]["params"]

    assert "language_boost" in params
    assert "language_boost" not in params["voice_setting"]


def test_the_greeting_is_the_thing_that_decides_which_language_they_answer_in():
    assert "स्वागत" in _props(agent_language="hi")["llm"]["greeting_message"]
    assert "माफ़" in _props(agent_language="hi")["llm"]["failure_message"]


def test_a_typo_in_the_language_costs_the_wrong_language_not_a_dead_call():
    """This is read while building the /join body for a live call."""
    props = _props(agent_language="klingon")
    assert props["asr"]["params"]["language"] == "en"
    assert get_profile("").code == "en"
    assert get_profile("HINDI ").code == "en"
    assert get_profile(" HI ").code == "hi"


def test_an_explicit_setting_still_wins_over_the_profile():
    """Pinning `hi` instead of the code-switching `multi`, or choosing the
    male Hindi voice, are both real things to want."""
    props = _props(agent_language="hinglish", asr_language="hi", minimax_voice_id="hindi_male_1_v2")
    assert props["asr"]["params"]["language"] == "hi"
    assert props["tts"]["params"]["voice_setting"]["voice_id"] == "hindi_male_1_v2"


def test_a_leftover_english_pin_fighting_the_profile_says_so_loudly():
    """The failure this catches: an existing .env from when this only spoke
    English keeps ASR_LANGUAGE=en, so AGENT_LANGUAGE=hi switches the prompt and
    the greeting while the recogniser stays English. A call that half-switches
    is far worse to debug than one that does not switch at all."""
    warnings = warn_on_language_overrides(
        Settings(agent_language="hi", asr_language="en", minimax_voice_id="English_captivating_female1"),
        HINDI,
    )
    assert len(warnings) == 2
    assert any("ASR_LANGUAGE" in w and "blank it" in w for w in warnings)
    assert any("MINIMAX_VOICE_ID" in w for w in warnings)


def test_no_warning_when_nothing_is_pinned():
    assert warn_on_language_overrides(Settings(agent_language="hi"), HINDI) == []


def test_the_prompt_tells_her_which_language_to_reply_in(monkeypatch):
    """Without this she answers a Hindi question in English, because English
    is what the rest of her instructions are written in."""
    monkeypatch.setattr(prompts, "get_settings", lambda: Settings(agent_language="hi"))
    assert "Devanagari" in prompts.build_system_prompt()

    monkeypatch.setattr(prompts, "get_settings", lambda: Settings(agent_language="en"))
    assert "Devanagari" not in prompts.build_system_prompt()


def test_the_prompt_protects_the_preformatted_strings_from_translation():
    """Slot labels and price summaries are built in code precisely so the
    model does no arithmetic on them. Translating them would undo that."""
    for profile in (HINDI, HINGLISH):
        assert "pre-formatted" in profile.prompt_instruction
        assert "exactly as" in profile.prompt_instruction or "exactly as given" in profile.prompt_instruction


@pytest.mark.parametrize("language", ["en", "hi", "hinglish"])
def test_every_language_covers_every_tool_the_customer_waits_on(language):
    """A Hindi call that says "let me pull that up for you" mid-turn tells the
    caller the Hindi was a veneer."""
    for tool in LOOKUP_TOOLS:
        assert bridge_lines.line_for(tool, language=language)


def test_hindi_bridge_lines_are_devanagari_not_romanised():
    """MiniMax's Hindi voices are trained on the script; "ek second" in Latin
    letters is read out as English words."""
    for tool in LOOKUP_TOOLS:
        line = bridge_lines.line_for(tool, language="hi")
        assert any("ऀ" <= ch <= "ॿ" for ch in line), line


def test_bridge_lines_keep_the_speech_markup_in_every_language():
    """`<#x#>` and the interjection tags are speech-2.8 model features, not
    English ones."""
    for language in ("en", "hi", "hinglish"):
        assert any("<#" in bridge_lines.line_for(tool, language=language) for tool in LOOKUP_TOOLS)


def test_an_untranslated_tool_falls_back_to_english_rather_than_dead_air():
    """A line in the wrong language is jarring; several seconds of silence on
    a live call reads as the system having hung up."""
    assert bridge_lines.line_for("search_pricing_rag", language="klingon")
    assert bridge_lines.line_for("crm_upsert_lead", language="hi") is None


def test_agora_speaks_the_profiles_filler_phrases_not_the_english_ones():
    filler = _props(agent_language="hi", filler_words_enabled=True)["filler_words"]
    phrases = filler["content"]["config"]["phrases"]
    assert phrases == HINDI.filler_phrases
    assert all(any("ऀ" <= ch <= "ॿ" for ch in phrase) for phrase in phrases)


def test_every_profile_is_internally_complete():
    """A profile missing any one of the five is the bug this design exists to
    make impossible."""
    for profile in (ENGLISH, HINDI, HINGLISH):
        assert profile.asr_language
        assert profile.voice_id
        assert profile.language_boost
        assert profile.greeting
        assert profile.failure_message
        assert profile.filler_phrases
