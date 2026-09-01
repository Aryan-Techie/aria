"""Short spoken lines that cover the silence while a tool runs.

Why this exists rather than Agora's own `filler_words`
------------------------------------------------------
Agora can speak a stall phrase itself, triggered purely on how long our
webhook has stayed quiet (`filler_words.trigger.fixed_time`). That mechanism
cannot express "speak when a tool fires", for two measured reasons:

1. `run_turn_stream` buffers each hop and only yields on the hop that
   concludes the turn, so time-to-first-byte is the whole hop - never near
   zero. Measured on this stack: 0.92s, 1.01s, 1.02s, 2.55s for turns that
   called NO tool at all.
2. Tool hops measure 1.4s-1.5s. That is inside the no-tool range, so no
   threshold exists that catches tool turns and misses the rest. Set low
   enough to catch tools, it fires on literally every turn - which is exactly
   what happened live.

Here we know the actual tool calls, so the line is chosen from the real
reason for the wait and fires only when there is a real wait.

Why the model does not write these itself
-----------------------------------------
It used to, and that is the "Aria said everything twice" bug: a model that
writes a bridge line AND calls a tool in the same hop then answers again once
the tool returns. These lines are emitted by us, in code, between hops, so
they cannot collide with the model's own output.

Why they are translated
-----------------------
For the same reason. These are the one part of what the customer hears that
the model does not write, so they stay in whatever language this file is
written in unless something translates them. A Hindi call that suddenly says
"let me pull those numbers up for you" in the middle of a turn is worse than
an English call - it tells the caller the Hindi was a veneer.
"""
from __future__ import annotations

import random
from collections.abc import Sequence

# Tools whose work the customer is actually waiting on. Everything else -
# crm_upsert_lead, crm_qualify_lead, log_objection, update_sentiment - is
# silent bookkeeping that happens to run mid-turn; narrating "let me pull
# that up" while recording a sentiment score is worse than saying nothing,
# because the customer then waits for information that was never coming.
_LOOKUP_TOOLS = {
    "search_pricing_rag",
    "calendar_check_availability",
    "calendar_book_meeting",
    "negotiate_deal",
    "ask_solutions_engineer",
}

# Per-tool, so the line matches the wait. `<#x#>` pauses and (breath) are
# MiniMax speech-2.8 markup - see SPEECH_STYLE_PROMPT in tools/prompts.py.
# They are model features rather than language features, so they work the same
# in every language below.
_ENGLISH: dict[str, tuple[str, ...]] = {
    "search_pricing_rag": (
        "Okay <#0.2#> let me pull those numbers up for you.",
        "Sure, <#0.2#> one second, I'm looking at the pricing now.",
        "Let me get you the exact figure on that. <#0.25#> Bear with me.",
        "(breath) Right, <#0.2#> checking that now.",
        "Good question <#0.2#> give me a second to get it right.",
    ),
    "calendar_check_availability": (
        "Let me pull up the calendar. <#0.25#> One second.",
        "Okay, <#0.2#> let me see what's actually open.",
        "Checking the diary now <#0.2#> just a moment.",
    ),
    "calendar_book_meeting": (
        "Perfect <#0.2#> let me lock that in.",
        "Great, <#0.2#> booking that in now.",
        "Okay, <#0.2#> putting that in the calendar.",
    ),
    # The two below cover a wait that is doing something the customer would
    # recognise: a second agent - the deal desk, or the solutions engineer -
    # is genuinely deciding or checking. Saying so is not a stall. It is what
    # a rep says when they go and ask someone, and the pause is them asking.
    "ask_solutions_engineer": (
        "Let me check that properly with one of our deployment engineers. <#0.3#> One second.",
        "(breath) Good question <#0.2#> I want to get that exactly right rather than guess.",
        "Let me pull the technical detail on that <#0.25#> bear with me.",
    ),
    "negotiate_deal": (
        "Let me see what I can do on that. <#0.3#> One second.",
        "(breath) Okay <#0.2#> let me check what I can get approved for you.",
        "Right <#0.2#> let me take that to our deal desk and see where we land.",
        "Give me a moment <#0.25#> I want to come back to you with a real number.",
    ),
}

# Devanagari, not romanised: MiniMax's Hindi voices are trained on the script,
# and "ek second" written in Latin letters is read out as English words.
# Product and business nouns stay in English because that is how they are
# actually said in an Indian office - "deal desk", not a translation of it.
_HINDI: dict[str, tuple[str, ...]] = {
    "search_pricing_rag": (
        "ठीक है <#0.2#> मैं आपके लिए अभी pricing निकालती हूँ.",
        "जी, <#0.2#> एक सेकंड, मैं अभी देख रही हूँ.",
        "मैं आपको exact figure बताती हूँ. <#0.25#> बस एक पल.",
        "(breath) अच्छा सवाल है <#0.2#> मुझे एक सेकंड दीजिए.",
    ),
    "calendar_check_availability": (
        "मैं calendar देखती हूँ. <#0.25#> एक सेकंड.",
        "ठीक है, <#0.2#> देखती हूँ कौन सा time खाली है.",
        "अभी diary check कर रही हूँ <#0.2#> एक पल.",
    ),
    "calendar_book_meeting": (
        "बढ़िया <#0.2#> मैं इसे अभी book कर देती हूँ.",
        "ठीक है, <#0.2#> calendar में डाल रही हूँ.",
    ),
    "ask_solutions_engineer": (
        "मैं ये हमारे deployment engineer से confirm कर लेती हूँ. <#0.3#> एक सेकंड.",
        "(breath) अच्छा सवाल <#0.2#> मैं अंदाज़े से नहीं बताना चाहती, सही जानकारी लेती हूँ.",
    ),
    "negotiate_deal": (
        "देखती हूँ मैं इसमें क्या कर सकती हूँ. <#0.3#> एक सेकंड.",
        "(breath) ठीक है <#0.2#> मैं देखती हूँ कितना approve करा सकती हूँ.",
        "एक पल दीजिए <#0.25#> मैं आपको सही number बताना चाहती हूँ.",
    ),
}

# The mix an Indian B2B call actually runs on. Deliberately not a third set of
# translations - it is the Hindi set with more English left standing, because
# that is what the code-switching profile's caller is already doing.
_HINGLISH: dict[str, tuple[str, ...]] = {
    "search_pricing_rag": (
        "Sure <#0.2#> एक सेकंड, मैं pricing निकालती हूँ.",
        "ठीक है <#0.2#> let me pull that up for you.",
        "मैं आपको exact figure बताती हूँ <#0.25#> one moment.",
    ),
    "calendar_check_availability": (
        "Let me check the calendar <#0.25#> एक सेकंड.",
        "ठीक है, <#0.2#> देखती हूँ क्या available है.",
    ),
    "calendar_book_meeting": (
        "Perfect <#0.2#> मैं अभी book कर देती हूँ.",
        "ठीक है, <#0.2#> putting that in the calendar.",
    ),
    "ask_solutions_engineer": (
        "मैं ये deployment engineer से confirm कर लेती हूँ <#0.3#> one second.",
        "(breath) Good question <#0.2#> मैं अंदाज़े से नहीं बताऊँगी.",
    ),
    "negotiate_deal": (
        "Let me see what I can do <#0.3#> एक सेकंड.",
        "(breath) ठीक है <#0.2#> मैं देखती हूँ कितना approve हो सकता है.",
    ),
}

_BY_LANGUAGE: dict[str, dict[str, tuple[str, ...]]] = {
    "en": _ENGLISH,
    "hi": _HINDI,
    "hinglish": _HINGLISH,
}


def speakable_tool(tool_names: Sequence[str]) -> str | None:
    """The first tool in this hop the customer is genuinely waiting on.

    A hop often batches bookkeeping with a real lookup - one live hop called
    update_sentiment, log_objection AND search_pricing_rag together. The
    lookup is the reason for the pause, so it is what the line should match.
    """
    return next((name for name in tool_names if name in _LOOKUP_TOOLS), None)


def line_for(
    tool_name: str, *, language: str | None = None, rng: random.Random | None = None
) -> str | None:
    """A bridge line for one tool, or None if that tool is silent bookkeeping.

    Falls back to the English line when a language has none for this tool.
    That is the lesser of two bad options: a line in the wrong language is
    jarring, but several seconds of dead air on a live call reads as the
    system having hung up.
    """
    if language is None:
        from app.config import get_settings

        language = get_settings().agent_language

    lines = _BY_LANGUAGE.get((language or "en").strip().lower(), _ENGLISH)
    options = lines.get(tool_name) or _ENGLISH.get(tool_name)
    if not options:
        return None
    return (rng or random).choice(options)
