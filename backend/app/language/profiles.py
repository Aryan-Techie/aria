"""What language Aria hears, thinks in, and speaks - as one profile per call.

Language is not one setting. Getting a Hindi call right means five things
agreeing with each other, and any one of them left on its English default is
enough to break the call:

  1. **ASR** must be told the language, or Deepgram transcribes Hindi audio as
     English-shaped nonsense and the model answers the nonsense.
  2. **The voice** must match. MiniMax voice IDs are language-specific;
     `English_captivating_female1` reading Devanagari is not accented Hindi,
     it is unusable.
  3. **`language_boost`** biases MiniMax's own pronunciation. Left unset, a
     Hindi voice still mispronounces mixed English product names.
  4. **The prompt** has to say which language to reply in. The model will
     answer an English-transcribed question in English no matter what the
     audio was.
  5. **Everything we speak in code** - greeting, failure line, bridge lines -
     is written by us, not the model, so it stays English unless it is
     translated here. A Hindi call that suddenly says "let me pull that up
     for you" mid-turn is worse than an English one.

Hence a profile rather than a language code: the five move together or not at
all.

Vendor support, checked against the vendors' own documentation:

* Deepgram nova-3 lists `hi`, and a `multi` mode covering English, Spanish,
  French, German, Hindi, Russian, Portuguese, Japanese, Italian and Dutch.
  `multi` is what a real Indian B2B call needs - a buyer discussing device
  fleets code-switches between Hindi and English inside a single sentence, and
  a recogniser pinned to `hi` mangles the English half.
* MiniMax publishes three Hindi system voices and a top-level `language_boost`
  parameter that accepts "Hindi" or "auto".
* Agora forwards any parameter it does not itself validate straight to the
  vendor, which is what lets `language_boost` through at all.

None of this is confirmed on a live call yet - see the note in the README.
Agora validates vendor/model/url against its own allowlist under managed
credentials, and this account has already had one (vendor, model) combination
refused for its SKU, so a Hindi voice being available to us is a reasonable
expectation rather than a measured fact.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LanguageProfile(BaseModel):
    """One coherent set of the five settings above."""

    code: str
    label: str

    # Deepgram language code, sent as asr.params.language.
    asr_language: str
    # MiniMax system voice id, and its language_boost value ("auto" lets
    # MiniMax detect per utterance, which is what a mixed call needs).
    voice_id: str
    language_boost: str
    # MiniMax's digit/abbreviation expansion is an English/Chinese feature.
    # Leaving it on for a Hindi voice spends latency on a pass that does not
    # apply.
    english_normalization: bool
    # MiniMax voice_setting.speed. 0.96 reads as considered rather than rushed
    # in English; the Hindi voices already read slower, so the same value
    # there lands as sluggish. A dial rather than a finding - retune by ear.
    speech_speed: float = 0.96

    # Spoken by Agora, not the model - see the fields it feeds in
    # agora/join_payload.py.
    greeting: str
    failure_message: str
    filler_phrases: list[str] = Field(default_factory=list)

    # Appended to the system prompt. The persona itself stays in English:
    # translating a 2,000-word prompt would be a second thing to keep in sync
    # with every behaviour change, and instructing an output language works.
    prompt_instruction: str


ENGLISH = LanguageProfile(
    code="en",
    label="English",
    asr_language="en",
    voice_id="English_captivating_female1",
    language_boost="English",
    english_normalization=True,
    greeting=(
        "Thanks for calling Apple Business Sales, "
        "Apple Park, One Apple Park Way in Cupertino. <#0.25#> "
        "This is Aria speaking. <#0.2#> How can I help you today?"
    ),
    failure_message="(breath) Sorry — could you say that once more? I didn't quite catch it.",
    filler_phrases=[
        "Let me pull that up for you. <#0.3#> One second.",
        "Sure <#0.2#> give me just a second.",
        "(breath) Okay, let me check that.",
        "Mm, <#0.2#> one moment, I'm looking at it now.",
        "Let me get you the exact number on that. <#0.3#> Bear with me.",
        "Right, <#0.2#> just pulling that up.",
    ],
    prompt_instruction="",
)


# Devanagari throughout rather than transliteration: MiniMax's Hindi voices are
# trained on the script, and romanised Hindi ("aap kaise hain") is read as
# English words by a TTS engine.
HINDI = LanguageProfile(
    code="hi",
    label="Hindi",
    asr_language="hi",
    voice_id="hindi_female_1_v2",
    language_boost="Hindi",
    english_normalization=False,
    speech_speed=1.02,
    greeting=(
        "Apple Business Sales में आपका स्वागत है. <#0.25#> "
        "मैं Aria बोल रही हूँ. <#0.2#> मैं आपकी किस तरह मदद कर सकती हूँ?"
    ),
    failure_message="(breath) माफ़ कीजिए — क्या आप एक बार फिर कह सकते हैं? मैं ठीक से सुन नहीं पाई.",
    filler_phrases=[
        "एक सेकंड <#0.3#> मैं अभी देखती हूँ.",
        "जी <#0.2#> बस एक पल दीजिए.",
        "(breath) ठीक है, मैं चेक करती हूँ.",
        "एक मिनट <#0.25#> मैं अभी निकालती हूँ.",
    ],
    prompt_instruction=(
        "THE CALLER IS SPEAKING HINDI. Reply in Hindi, written in Devanagari script - "
        "your text is spoken aloud by a Hindi voice, and romanised Hindi gets read out as "
        "English words. Keep product names, model names and anything a tool handed you "
        "pre-formatted (meeting slot labels, price summaries) exactly as they were given "
        "to you, in English. That is not a compromise - it is how this conversation is "
        "actually held in an Indian office, and re-spelling 'MacBook Air' or a date in "
        "Devanagari makes you harder to understand, not easier."
    ),
)


# The one most Indian B2B calls actually need. A buyer discussing a device
# fleet switches between Hindi and English inside a single sentence, and a
# recogniser pinned to either one mangles the other half.
HINGLISH = LanguageProfile(
    code="hinglish",
    label="Hindi/English (code-switching)",
    asr_language="multi",
    voice_id="hindi_female_1_v2",
    language_boost="auto",
    english_normalization=False,
    speech_speed=1.02,
    greeting=(
        "Apple Business Sales में आपका स्वागत है. <#0.25#> "
        "This is Aria speaking. <#0.2#> मैं आपकी किस तरह मदद कर सकती हूँ?"
    ),
    failure_message="(breath) Sorry, माफ़ कीजिए — क्या आप एक बार फिर कह सकते हैं?",
    filler_phrases=[
        "एक सेकंड <#0.3#> मैं अभी देखती हूँ.",
        "Sure <#0.2#> बस एक पल दीजिए.",
        "(breath) ठीक है, let me check that.",
        "One moment <#0.25#> मैं अभी निकालती हूँ.",
    ],
    prompt_instruction=(
        "THE CALLER MAY SWITCH BETWEEN HINDI AND ENGLISH, OFTEN INSIDE ONE SENTENCE. "
        "Match them. Reply in whichever language they just used, and let the mix fall "
        "where it naturally does in an Indian office: Hindi for the conversation, English "
        "for product names, numbers, dates and technical terms. Write any Hindi in "
        "Devanagari script, never romanised - romanised Hindi is read out as English "
        "words by the voice engine. Anything a tool handed you pre-formatted - a meeting "
        "slot label, a price summary - is said exactly as given, in English. Do not "
        "translate it and do not recalculate it."
    ),
)


PROFILES: dict[str, LanguageProfile] = {
    ENGLISH.code: ENGLISH,
    HINDI.code: HINDI,
    HINGLISH.code: HINGLISH,
}


def get_profile(code: str) -> LanguageProfile:
    """Falls back to English on anything unrecognised rather than raising.

    This is read while building the /join payload for a live call. A typo in
    AGENT_LANGUAGE should cost the wrong language, not a call that cannot
    start.
    """
    return PROFILES.get((code or "").strip().lower(), ENGLISH)
