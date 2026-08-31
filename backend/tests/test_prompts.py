

def test_speech_markup_block_gated_on_speech_2_8():
    """<#x#> and (breath) are speech-2.8-only MiniMax features. On any other
    voice they get spoken aloud as literal text, so the instruction must not
    ship unless the configured engine can actually render them."""
    from app.config import Settings
    from app.tools.prompts import supports_speech_markup

    assert supports_speech_markup(Settings()) is True
    assert supports_speech_markup(Settings(minimax_model="speech-02-turbo")) is False
    assert supports_speech_markup(Settings(tts_vendor="elevenlabs")) is False


def test_build_system_prompt_includes_speech_style_by_default():
    from app.tools.prompts import build_system_prompt

    prompt = build_system_prompt()
    assert "HOW YOU SOUND" in prompt
    assert "(sighs)" in prompt
    # The persona and the date stamp must survive alongside it.
    assert "You are Aria" in prompt
    assert "Today is" in prompt
