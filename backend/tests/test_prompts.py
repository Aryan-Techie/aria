

def test_speech_markup_block_gated_on_speech_2_8():
    """<#x#> and (breath) are speech-2.8-only MiniMax features. On any other
    voice they get spoken aloud as literal text, so the instruction must not
    ship unless the configured engine can actually render them. Sarvam, the
    default vendor, has no documented markup feature either."""
    from app.config import Settings
    from app.tools.prompts import supports_speech_markup

    assert supports_speech_markup(Settings()) is False
    assert supports_speech_markup(Settings(tts_vendor="minimax")) is True
    assert supports_speech_markup(Settings(tts_vendor="minimax", minimax_model="speech-02-turbo")) is False
    assert supports_speech_markup(Settings(tts_vendor="elevenlabs")) is False


def test_build_system_prompt_omits_speech_style_by_default():
    """Sarvam is the default vendor and has no delivery-markup feature, so the
    instruction that teaches <#x#>/(breath) markup must not ship for it."""
    from app.tools.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "HOW YOU SOUND" not in prompt
    # The persona and the date stamp must survive regardless.
    assert "You are Aria" in prompt
    assert "Today is" in prompt


def test_build_system_prompt_includes_speech_style_on_minimax(monkeypatch):
    from app.config import Settings
    from app.tools import prompts
    from app.tools.prompts import build_system_prompt

    monkeypatch.setattr(prompts, "get_settings", lambda: Settings(tts_vendor="minimax"))
    prompt = build_system_prompt()
    assert "HOW YOU SOUND" in prompt
    assert "(sighs)" in prompt


def test_a_misheard_turn_is_never_a_dead_end():
    """Found on a live call. Handed a garbled transcript the model improvised
    a refusal - "sorry, I can't help with you" - because nothing in the prompt
    told it what to do with a turn it did not understand. Phone audio drops
    words in every language, so this is not a Hindi problem."""
    from app.tools.prompts import ARIA_SYSTEM_PROMPT

    prompt = ARIA_SYSTEM_PROMPT

    assert "WHEN YOU DID NOT UNDERSTAND" in prompt
    assert "say it again" in prompt
    assert "never blame the caller" in prompt
    assert "never end the conversation over one" in prompt


def test_she_may_never_tell_a_caller_their_language_is_unsupported():
    """Also found live: spoken to in Hindi, she answered that she only
    understands English. That is not her decision, she cannot check it, and on
    that call it was factually wrong - the recogniser was simply pinned to the
    wrong language."""
    from app.tools.prompts import ARIA_SYSTEM_PROMPT

    prompt = ARIA_SYSTEM_PROMPT

    assert "never tell anyone you do not support their language" in prompt
    assert "rudest thing" in prompt
