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
_LINES: dict[str, tuple[str, ...]] = {
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
    # The two lines below cover a wait that is doing something the customer
    # would recognise: a second agent - the deal desk, or the solutions
    # engineer - is genuinely deciding or checking. Saying so is not a stall.
    # It is what a rep says when they go and ask someone, and the pause is
    # them asking.
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


def speakable_tool(tool_names: Sequence[str]) -> str | None:
    """The first tool in this hop the customer is genuinely waiting on.

    A hop often batches bookkeeping with a real lookup - one live hop called
    update_sentiment, log_objection AND search_pricing_rag together. The
    lookup is the reason for the pause, so it is what the line should match.
    """
    return next((name for name in tool_names if name in _LOOKUP_TOOLS), None)


def line_for(tool_name: str, *, rng: random.Random | None = None) -> str | None:
    """A bridge line for one tool, or None if that tool is silent bookkeeping."""
    options = _LINES.get(tool_name)
    if not options:
        return None
    return (rng or random).choice(options)
