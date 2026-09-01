"""Who is speaking, and in what accent.

Two problems that turn out to be the same problem - the voice is fixed for the
whole call, and it should not be.

**Accent should follow the language.** `hinglish` pins a Hindi voice for the
session. That is right while the caller is speaking Hindi and wrong the moment
they switch to English, because a Hindi voice reading an English sentence is
an English sentence in a Hindi accent. It is not unusable, but it is
immediately noticeable, and on a call where the customer has just switched
language deliberately it reads as the agent not having noticed.

**Each layer should sound like a different person.** Aria is layer 1. When she
goes to the deal desk or the solutions engineer, a second agent really does
answer - its own prompt, its own model call, its own objective. Today the
customer hears all of it in Aria's voice, so the layering is invisible to the
person it was built for. Giving each one a voice makes the handoff audible:
"let me check with our deal desk" is followed by a different person answering,
because a different agent genuinely did.

Both are done by the same primitive - Agora's runtime `update`, which it
documents for exactly this case (a custom LLM deciding the voice should
change) - and both are governed by the same rule below.

Why this is deliberately conservative
-------------------------------------
A voice switch costs a REST round-trip on the turn path, and it lands at the
most dramatic moment of the call. So:

* It is **off unless asked for** (`VOICE_SWITCHING_ENABLED`), because the
  latency budget is ~800ms per turn and this spends some of it.
* It **never blocks the reply**. The update is dispatched in the background
  and the turn continues; a switch that arrives a beat late costs one sentence
  in the previous voice, where waiting on it costs every sentence.
* It **only fires on a real change**. Re-sending the voice already in force is
  a round-trip bought for nothing, so the current voice is tracked per session.
* A failure is logged and swallowed. A voice that did not change is a cosmetic
  disappointment; an exception raised mid-turn is a broken call.
"""
from __future__ import annotations

import json
import logging

from app.background import run_in_background
from app.language.profiles import LanguageProfile, get_profile

logger = logging.getLogger("aria.voice")

# Devanagari block. Script detection rather than a language classifier: it is
# exact, costs nothing, and needs no model call on the turn path. It answers
# the only question being asked here - "is this sentence going to be read by a
# Hindi voice or an English one".
_DEVANAGARI = ("ऀ", "ॿ")

# The share of letters that must be Devanagari before the reply counts as
# Hindi. Not a majority vote: Hinglish is mostly English nouns in a Hindi
# sentence ("कितने MacBook Pro चाहिए"), so a sentence with a quarter of its
# letters in Devanagari is a Hindi sentence and wants the Hindi voice.
HINDI_SCRIPT_THRESHOLD = 0.15


def script_language(text: str) -> str | None:
    """"hi", "en", or None when there is not enough text to tell.

    None matters: a two-word reply, or one made entirely of a product name, is
    not evidence of a language change, and switching voice on it would flap
    the accent back and forth mid-conversation.
    """
    letters = [ch for ch in (text or "") if ch.isalpha()]
    if len(letters) < 8:
        return None
    devanagari = sum(1 for ch in letters if _DEVANAGARI[0] <= ch <= _DEVANAGARI[1])
    return "hi" if devanagari / len(letters) >= HINDI_SCRIPT_THRESHOLD else "en"


def voice_for_language(profile: LanguageProfile, language: str | None) -> str:
    """The voice this profile should use for a reply in `language`.

    A single-language profile never switches - an English deployment that
    happens to quote a Hindi company name is not a reason to change voice, and
    only the mixed profile has a second voice to change to.
    """
    if language is None or not profile.alternate_voices:
        return profile.voice_id
    return profile.alternate_voices.get(language, profile.voice_id)


# Which layer speaks the concluding hop, keyed by the tool that ran in it.
# Only the two that genuinely are a second agent - the rest is Aria doing her
# own bookkeeping and lookups, and a voice change there would be theatre.
AGENT_BY_TOOL = {
    "negotiate_deal": "deal_desk",
    "ask_solutions_engineer": "solutions",
}


def agent_for_tools(tool_names) -> str:
    """The layer whose answer this turn is about to relay."""
    for name in tool_names or ():
        role = AGENT_BY_TOOL.get(name)
        if role:
            return role
    return "aria"


def resolve_voice(profile: LanguageProfile, *, role: str = "aria", language: str | None = None) -> str:
    """The MiniMax voice that should be speaking, given who is talking and in
    what language. Role wins over language: the deal desk sounding like the
    deal desk is the point, and it has one voice per profile rather than one
    per language, which keeps this a lookup rather than a matrix."""
    if role != "aria":
        return profile.agent_voices.get(role) or profile.voice_id
    return voice_for_language(profile, language)


def resolve_sarvam_target(profile: LanguageProfile, *, role: str = "aria") -> dict:
    """The Sarvam speaker/language pair for whoever is talking.

    Unlike MiniMax's voice ids, Sarvam speakers are cross-lingual, so there is
    no per-language variant to pick between here - `language` doesn't factor
    in. `target_language_code` stays pinned to the profile's language for the
    whole call, same as MiniMax's own hinglish profile pins one voice by
    default; Sarvam has no per-utterance "auto" mode to switch on instead.
    """
    speaker = profile.sarvam_speaker
    if role != "aria":
        speaker = profile.sarvam_agent_speakers.get(role) or speaker
    return {"speaker": speaker, "target_language_code": profile.sarvam_language_code}


def ensure_voice(session, voice, *, client=None, settings=None, runner=run_in_background) -> bool:
    """Put `voice` in force for this call, if it is not already.

    `voice` is either a MiniMax voice id string (the shape every caller used
    before Sarvam existed) or a vendor-shaped tts.params dict such as the one
    resolve_sarvam_target() returns - Sarvam's identity is a (speaker,
    target_language_code) pair, not a single id, so a bare string can't carry
    it. Either way this treats it as opaque: build a params dict to send, and
    a string key to dedupe against the voice already in force.

    Returns whether an update was dispatched - False covers every no-op
    reason, and none of them raise. The update itself runs through `runner`,
    which is the shared background pool in production: a switch that lands a
    beat late costs one sentence in the previous voice, where waiting on it
    would cost every sentence a round-trip. Tests pass a direct-call runner so
    they can assert on the payload without touching that pool.
    """
    if settings is None:
        from app.config import get_settings

        settings = get_settings()

    if not settings.voice_switching_enabled or not voice:
        return False

    if isinstance(voice, str):
        params, cache_key = {"voice_setting": {"voice_id": voice}}, voice
    else:
        params, cache_key = voice, json.dumps(voice, sort_keys=True)

    if not session.agent_id or session.current_voice_id == cache_key:
        return False

    # Recorded before the update lands, deliberately. Two hops of one turn can
    # ask for the same switch, and a second round-trip buys nothing; a failed
    # update leaves the record optimistic, which costs the wrong voice rather
    # than a retry storm on a live call.
    session.current_voice_id = cache_key

    if client is None:
        from app.agora.client import default_agora_client

        client = default_agora_client()

    def _apply() -> None:
        try:
            client.update(session.agent_id, {"tts": {"params": params}})
            logger.info("voice -> %s (session %s)", cache_key, session.session_id)
        except Exception as exc:
            logger.warning("voice switch to %s failed: %s", cache_key, exc)

    runner(_apply)
    return True


def follow(session, *, role: str = "aria", spoken_language: str | None = None, **kwargs) -> bool:
    """One call from the pipeline: work out who should be speaking and make it
    so. `spoken_language` is read off the customer's own last turn rather than
    the reply, because the reply is still being generated and the switch has
    to be in flight before it is spoken."""
    from app.config import get_settings

    settings = get_settings()
    profile = get_profile(settings.agent_language)
    if settings.tts_vendor == "sarvam":
        voice = resolve_sarvam_target(profile, role=role)
    else:
        voice = resolve_voice(profile, role=role, language=spoken_language)
    return ensure_voice(session, voice, settings=settings, **kwargs)
