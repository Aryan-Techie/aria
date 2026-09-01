"""The core per-turn loop invoked by routes/llm.py (the endpoint Agora calls).

Memory recall/write-back (mem0) is wired in via app.memory.session_memory's
safe_recall/safe_write_back — both no-op with zero network calls whenever
Voyage/Anthropic keys aren't configured (the default in tests/dev without a
.env), so this stays hermetic to test without any extra mocking.
"""
import json
import logging
import time
from typing import Callable, Iterator

from app.config import get_settings
from app.escalation import triggers
from app.escalation.models import TranscriptTurn
from app.memory.session_memory import safe_recall, safe_write_back
from app.orchestrator import bridge_lines
from app.orchestrator.llm_client import (
    ChatLLMClient,
    LLMTurn,
    StreamingChatLLMClient,
    default_llm_client,
)
from app.rtm.publisher import RtmPublisher, default_rtm_publisher
from app.sessions.models import SessionState
from app.tools import definitions, executor
from app.tools.prompts import ARIA_SYSTEM_PROMPT, build_system_prompt

logger = logging.getLogger("aria")

# 4 was not enough for the booking flow: check_availability -> book ->
# confirm burned every hop and the turn fell through to the fallback string
# with the confirmation unsaid. Most turns use 1-2 hops, so a higher ceiling
# costs nothing on the common path and only spends time when genuinely needed.
MAX_TOOL_HOPS = 6

QUALIFICATION_TOOLS = {"crm_upsert_lead", "crm_qualify_lead"}

MemoryRecallFn = Callable[[str, str], list[str]]
MemoryWriteBackFn = Callable[[str, str, str], None]


def _render_call_state(session: SessionState) -> str:
    """Renders LeftBrain/RightBrain into a compact block for the system prompt.

    The tools write these every single turn, but until now nothing ever read
    them back - the model only ever saw raw transcript. Re-injecting them is
    what lets Aria hold on to a detail given twenty turns ago and notice when
    the customer *changes* one (the 25 -> 50 device-count case in the demo
    scenario), without paying a network round-trip to a memory service.

    Returns "" when nothing has been captured yet, so an untouched session
    leaves the system prompt byte-identical to ARIA_SYSTEM_PROMPT.
    """
    left, right = session.left_brain, session.right_brain
    sections: list[str] = []

    facts: list[str] = []
    if left.company:
        facts.append(f"Company: {left.company}")
    if left.user_count is not None:
        facts.append(f"Devices/users needed: {left.user_count}")
    if left.budget_range:
        facts.append(f"Budget: {left.budget_range}")
    if left.timeline:
        facts.append(f"Timeline: {left.timeline}")
    if left.pain_points:
        facts.append("Pain points: " + "; ".join(left.pain_points))
    if left.decision_stage:
        facts.append(f"Decision stage: {left.decision_stage}")

    if facts:
        sections.append(
            "What you have already established on this call - treat it as fact "
            "and do NOT ask for it again. If the customer changes any of it, "
            "call crm_upsert_lead so this record updates:\n"
            + "\n".join(f"- {f}" for f in facts)
        )

    signals: list[str] = []
    for objection in right.objections:
        state = "resolved" if objection.resolved else "STILL UNRESOLVED"
        repeat = f", raised {objection.attempts} times" if objection.attempts > 1 else ""
        signals.append(f'- {objection.topic} ({state}{repeat}): "{objection.raised_text}"')
    if right.competitor_mentions:
        signals.append("- Competitors they have brought up: " + ", ".join(right.competitor_mentions))
    if right.sentiment != "neutral":
        signals.append(f"- Current read on their tone: {right.sentiment}")

    if signals:
        sections.append(
            "Objections raised and how they are feeling - an unresolved objection "
            "raised more than once needs a genuinely different answer, not a "
            "reworded one:\n" + "\n".join(signals)
        )

    negotiation = _render_negotiation(session)
    if negotiation:
        sections.append(negotiation)

    return "\n\n".join(sections)


def _render_negotiation(session: SessionState) -> str:
    """What she has already put on the table, and what she may still say.

    Without this she re-opens every round from zero: the tool result from two
    turns ago has scrolled out of the useful part of the history, and a
    negotiator who forgets her own last offer either repeats it as if it were
    new or, worse, contradicts it. The authorised figure is restated every
    hop, from the record rather than from the transcript, so what she believes
    she offered and what the business actually authorised cannot drift apart.
    """
    negotiation = session.negotiation
    offer = negotiation.last_offer
    if offer is None:
        return ""

    lines = [
        f"- You have already offered {negotiation.granted_discount_pct:g}% off list "
        f"(round {negotiation.round_count}, authorised by {offer.authorised_by}). "
        "That number stands - never go below it, and never present it again as if it were new.",
        f"- The numbers you gave, verbatim: {offer.price_summary}",
    ]
    if offer.commitments:
        lines.append(
            "- You asked for this in return, so hold them to it: "
            + "; ".join(c.detail for c in offer.commitments)
        )
    if negotiation.human_approved_pct is not None:
        lines.append(
            f"- Your sales manager has now approved {negotiation.human_approved_pct:g}%. "
            "You may offer that in your very next reply - lead with it, they have been waiting on it."
        )
    elif negotiation.pending_human_approval:
        lines.append(
            "- A sales manager is being asked about a larger discount right now. Say it is with "
            "your manager and you will confirm before the call ends. Do NOT state it as agreed."
        )
    lines.append(
        "- If they push again, call negotiate_deal again rather than moving on your own. "
        "Each round the desk allows less than the last, and that is deliberate."
    )
    return "Where the negotiation stands:\n" + "\n".join(lines)


def _build_system_prompt(session: SessionState, memories: list[str]) -> str:
    blocks = [build_system_prompt()]

    call_state = _render_call_state(session)
    if call_state:
        blocks.append(call_state)

    if memories:
        memory_block = "\n".join(f"- {m}" for m in memories)
        blocks.append(
            "Relevant details recalled from earlier in this relationship/call "
            "(may be from beyond the visible recent history - use if relevant, "
            f"don't repeat back verbatim):\n{memory_block}"
        )

    return "\n\n".join(blocks)


def _history_to_anthropic_messages(session: SessionState) -> list[dict]:
    return [{"role": t.role, "content": t.content} for t in session.transcript]


def _turn_to_assistant_content(turn: LLMTurn) -> list[dict]:
    content: list[dict] = []
    if turn.text:
        content.append({"type": "text", "text": turn.text})
    for call in turn.tool_calls:
        content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.input})
    return content


def _execute_tool_calls(
    turn: LLMTurn,
    session: SessionState,
    publisher: RtmPublisher,
    messages: list[dict],
) -> bool:
    """Runs one hop's tool calls, appends the assistant + tool_result messages,
    publishes the matching RTM events, and reports whether escalation fired.

    Shared by run_turn and run_turn_stream so the streaming path can never
    drift from the blocking one.
    """
    escalate_called = False
    messages.append({"role": "assistant", "content": _turn_to_assistant_content(turn)})
    tool_result_blocks = []

    for call in turn.tool_calls:
        publisher.publish(session.session_id, "tool_call_started", {"tool_name": call.name, "args": call.input})
        result = executor.dispatch(call.name, call.input, session)
        publisher.publish(
            session.session_id,
            "tool_call_finished",
            {"tool_name": call.name, "result_summary": json.dumps(result, default=str)[:300]},
        )

        if call.name == "escalate_to_human":
            escalate_called = True
            publisher.publish(session.session_id, "escalation_triggered", {"trigger_source": "llm", **result})
        elif call.name in QUALIFICATION_TOOLS:
            publisher.publish(session.session_id, "qualification_updated", session.left_brain.model_dump(mode="json"))
        elif call.name == "log_objection":
            publisher.publish(session.session_id, "objection_logged", result)
        elif call.name == "calendar_book_meeting" and "error" not in result:
            publisher.publish(session.session_id, "call_outcome_set", {"outcome": "meeting_booked", **result})
        elif call.name == "negotiate_deal" and "error" not in result:
            offer = session.negotiation.last_offer
            publisher.publish(
                session.session_id,
                "deal_offer_made",
                {
                    "round": offer.round if offer else session.negotiation.round_count,
                    "requested_pct": offer.requested_discount_pct if offer else None,
                    "granted_pct": result.get("granted_discount_pct"),
                    "authorised_by": result.get("authorised_by"),
                    # The audit line: what the desk wanted, and what stopped it.
                    # Nothing else in the UI can show that a limit was enforced
                    # rather than merely respected.
                    "clamped": offer.clamped if offer else False,
                    "clamp_reason": offer.clamp_reason if offer else None,
                    "asked_in_return": result.get("ask_for_in_return", []),
                },
            )
            if result.get("awaiting_human_approval"):
                publisher.publish(
                    session.session_id,
                    "deal_approval_requested",
                    {
                        "escalation_id": session.negotiation.approval_escalation_id,
                        "requested_pct": offer.requested_discount_pct if offer else None,
                    },
                )

        tool_result_blocks.append(
            {"type": "tool_result", "tool_use_id": call.id, "content": json.dumps(result, default=str)}
        )

    messages.append({"role": "user", "content": tool_result_blocks})
    return escalate_called


def run_turn(
    session: SessionState,
    history: list[TranscriptTurn],
    *,
    llm_client: ChatLLMClient | None = None,
    publisher: RtmPublisher | None = None,
    memory_recall: MemoryRecallFn = safe_recall,
    memory_write_back: MemoryWriteBackFn = safe_write_back,
    max_hops: int = MAX_TOOL_HOPS,
) -> str:
    """`history` is the full user/assistant turn history for this call, as
    provided by the caller for this request (Agora, in production). This is
    treated as the source of truth and overwrites session.transcript wholesale
    rather than being appended to our own locally-tracked copy — that's what
    correctly handles a barge-in: if the customer interrupted Aria mid-reply,
    Agora's next request reflects the truncated version of what was actually
    said, not what Aria intended to say.
    """
    llm_client = llm_client or default_llm_client()
    publisher = publisher or default_rtm_publisher()

    session.transcript = list(history)
    messages = _history_to_anthropic_messages(session)

    latest_user_message = next(
        (t.content for t in reversed(session.transcript) if t.role == "user"), ""
    )
    recalled_memories = memory_recall(session.session_id, latest_user_message)

    escalate_called = False
    final_text = ""
    turn: LLMTurn | None = None

    for _hop in range(max_hops):
        # Rebuilt each hop: a tool called in the previous hop may have just
        # changed LeftBrain/RightBrain, and this hop should see the new value.
        system_prompt = _build_system_prompt(session, recalled_memories)
        turn = llm_client.create_turn(system=system_prompt, messages=messages, tools=definitions.TOOLS)

        if not turn.wants_tool_use:
            if not turn.text:
                # See run_turn_stream: an empty conclusion is dead air on a
                # live call, so re-sample rather than return silence.
                logger.warning("empty conclusion on hop=%d, re-sampling", _hop)
                continue
            final_text = turn.text
            break

        escalate_called |= _execute_tool_calls(turn, session, publisher, messages)
    else:
        final_text = (turn.text if turn else "") or (
            "Sorry, I got a bit tangled up there. Could you say that again?"
        )
        logger.warning("Hit MAX_TOOL_HOPS (%d) without a final text answer, session=%s", max_hops, session.session_id)

    # Deterministic guardrails temporarily disabled — the LLM's own judgment
    # (already instructed to treat escalation as a last resort) is the only
    # path to escalate for now, while premature-escalation behavior is being
    # tuned live. Re-enable by flipping ESCALATION_GUARDRAILS_ENABLED.
    if get_settings().escalation_guardrails_enabled:
        should_escalate, source = triggers.check_triggers(session.right_brain, session.last_rag_score)
        if should_escalate and not escalate_called and session.status != "escalated":
            result = executor.dispatch(
                "escalate_to_human",
                {"reason": f"auto-triggered ({source})"},
                session,
                trigger_source=source,
            )
            publisher.publish(session.session_id, "escalation_triggered", {"trigger_source": source, **result})
            final_text += (
                " I'm also going to loop in one of our specialists who'll have full context, "
                "just to make sure you're fully taken care of."
            )

    session.transcript.append(TranscriptTurn(role="assistant", content=final_text))
    logger.info("session=%s final_text=%r", session.session_id, final_text)
    memory_write_back(session.session_id, latest_user_message, final_text)
    return final_text


def run_turn_stream(
    session: SessionState,
    history: list[TranscriptTurn],
    *,
    llm_client: StreamingChatLLMClient | None = None,
    publisher: RtmPublisher | None = None,
    memory_recall: MemoryRecallFn = safe_recall,
    memory_write_back: MemoryWriteBackFn = safe_write_back,
    max_hops: int = MAX_TOOL_HOPS,
) -> Iterator[str]:
    """Streaming twin of run_turn: yields reply text as it is generated.

    Same tool loop, same session bookkeeping - the only difference is that
    text is handed out token-by-token instead of after the whole loop. That
    matters because Agora starts TTS on the first chunk it receives, so the
    customer hears the opening words while later tool hops are still running,
    instead of waiting ~10s in silence and tripping Agora's own
    `failure_message` timeout.
    """
    llm_client = llm_client or default_llm_client()
    publisher = publisher or default_rtm_publisher()

    session.transcript = list(history)
    messages = _history_to_anthropic_messages(session)

    latest_user_message = next(
        (t.content for t in reversed(session.transcript) if t.role == "user"), ""
    )
    recalled_memories = memory_recall(session.session_id, latest_user_message)

    escalate_called = False
    spoken_parts: list[str] = []
    turn: LLMTurn | None = None
    # At most one bridge line per turn. Two in a row ("let me pull those up"
    # ... "let me pull those up") is worse than none, and a turn that chains
    # three hops would otherwise get one before each.
    bridged = False

    for _hop in range(max_hops):
        system_prompt = _build_system_prompt(session, recalled_memories)

        turn = None
        hop_text: list[str] = []
        hop_started = time.monotonic()

        # Buffered rather than yielded live, because some models (Qwen on Groq
        # notably) write out a complete answer AND call a tool in the same hop,
        # then answer again once the tool returns. Streaming both made Aria say
        # the whole thing twice on a live call. Text is only spoken from a hop
        # that is NOT calling a tool - i.e. the hop that actually concludes the
        # turn.
        for kind, value in llm_client.stream_turn(
            system=system_prompt, messages=messages, tools=definitions.TOOLS
        ):
            if kind == "text":
                hop_text.append(value)
            else:
                turn = value

        logger.info(
            "session=%s hop=%d took %.2fs tools=%s",
            session.session_id,
            _hop,
            time.monotonic() - hop_started,
            [c.name for c in turn.tool_calls] if turn else [],
        )

        if turn is None or not turn.wants_tool_use:
            text = "".join(hop_text)
            if text:
                spoken_parts.append(text)
                yield text
                break
            # Concluded with no tool call AND nothing to say - observed live on
            # a real turn, and it reaches the customer as dead air. Re-sample
            # instead of breaking; if every remaining hop also comes back empty
            # the loop falls through to the spoken fallback below.
            logger.warning(
                "empty conclusion on hop=%d, re-sampling, session=%s", _hop, session.session_id
            )
            continue

        # Speak BEFORE dispatching, so the line covers the tool's own runtime
        # plus the follow-up hop that turns its result into an answer - live
        # that pair measured 4.6s + 3.4s of dead air. Only for tools the
        # customer is actually waiting on, and only once per turn.
        if not bridged:
            waited_on = bridge_lines.speakable_tool([c.name for c in turn.tool_calls])
            line = bridge_lines.line_for(waited_on) if waited_on else None
            if line:
                bridged = True
                spoken_parts.append(line)
                yield line

        escalate_called |= _execute_tool_calls(turn, session, publisher, messages)
    else:
        if not spoken_parts:
            fallback = "Let me pull that up for you - one moment."
            spoken_parts.append(fallback)
            yield fallback
        logger.warning(
            "Hit MAX_TOOL_HOPS (%d) without a final text answer, session=%s", max_hops, session.session_id
        )

    if get_settings().escalation_guardrails_enabled:
        should_escalate, source = triggers.check_triggers(session.right_brain, session.last_rag_score)
        if should_escalate and not escalate_called and session.status != "escalated":
            result = executor.dispatch(
                "escalate_to_human",
                {"reason": f"auto-triggered ({source})"},
                session,
                trigger_source=source,
            )
            publisher.publish(session.session_id, "escalation_triggered", {"trigger_source": source, **result})
            tail = (
                " I'm also going to loop in one of our specialists who'll have full context, "
                "just to make sure you're fully taken care of."
            )
            spoken_parts.append(tail)
            yield tail

    final_text = "".join(spoken_parts)
    session.transcript.append(TranscriptTurn(role="assistant", content=final_text))
    logger.info("session=%s streamed final_text=%r", session.session_id, final_text)
    memory_write_back(session.session_id, latest_user_message, final_text)
