"""The bridge line is what covers a tool's runtime out loud.

Regression guard for the live failure that motivated it: Agora's own
filler_words, triggered on elapsed silence alone, spoke "let me pull that up
for you" on every single turn - including turns that called no tool.
"""
import random

from app.orchestrator import bridge_lines


def test_lookup_tools_get_a_line():
    for tool in ("search_pricing_rag", "calendar_check_availability", "calendar_book_meeting"):
        assert bridge_lines.line_for(tool)


def test_bookkeeping_tools_stay_silent():
    """Narrating "let me pull that up" while recording a sentiment score makes
    the customer wait for information that is never coming."""
    for tool in ("crm_upsert_lead", "crm_qualify_lead", "log_objection", "update_sentiment"):
        assert bridge_lines.line_for(tool) is None
        assert bridge_lines.speakable_tool([tool]) is None


def test_escalation_is_never_bridged():
    assert bridge_lines.line_for("escalate_to_human") is None


def test_speakable_tool_picks_the_lookup_out_of_a_batched_hop():
    """One live hop called update_sentiment, log_objection and
    search_pricing_rag together - the lookup is the reason for the pause."""
    batch = ["update_sentiment", "log_objection", "search_pricing_rag"]
    assert bridge_lines.speakable_tool(batch) == "search_pricing_rag"


def test_speakable_tool_none_when_nothing_is_worth_narrating():
    assert bridge_lines.speakable_tool(["update_sentiment", "crm_upsert_lead"]) is None
    assert bridge_lines.speakable_tool([]) is None


def test_lines_vary_so_the_agent_does_not_repeat_one_phrase():
    """The complaint was hearing the identical phrase every time."""
    rng = random.Random(0)
    seen = {bridge_lines.line_for("search_pricing_rag", rng=rng) for _ in range(60)}
    assert len(seen) >= 3


def test_lines_are_short_and_free_of_markdown():
    """Everything here is spoken aloud, so markdown would be read out. `#` is
    exempt - it is the delimiter of MiniMax's `<#x#>` pause marker."""
    for tool in ("search_pricing_rag", "calendar_check_availability", "calendar_book_meeting"):
        for _ in range(20):
            line = bridge_lines.line_for(tool)
            assert len(line) < 80, line
            assert not any(ch in line for ch in "*_|`"), line
            assert not line.endswith("<#0.2#>")
