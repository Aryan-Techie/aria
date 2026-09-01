"""Layer 2, second seat: the solutions engineer.

The deal desk (app/deal/desk.py) is the other one. Between them they are what
makes the middle layer a *tier* rather than a single helper: two specialists
with different objectives, neither of which is "hold a conversation", both
reached by Aria and neither able to speak to the customer.

This one exists to close the gap that made escalation look reasonable. A
compatibility, migration or deployment question that four sales documents do
not settle left exactly two honest options: guess, or fetch a person. Guessing
is how you promise a customer that their bespoke ERP client runs fine; fetching
a person costs twenty minutes of someone's day and ends the call.

So there is a third option: a specialist that reads everything the retriever
can find, answers only from it, and - this is the part that matters - is
required to say precisely what it does NOT know rather than rounding a gap
down to reassurance. A precise "we can confirm x and y; z depends on your
specific build, and here is who checks it" is a genuinely useful answer, and
it is one a generalist prompt optimised for warmth will not give you.

It escalates when it should. `escalate_recommended` comes back true when the
material does not support an answer at all, and that is a *better* handoff
than the one it replaces: the human arrives knowing exactly which question is
open.
"""
from __future__ import annotations

import json
import logging
from typing import Literal, Protocol

from pydantic import BaseModel, Field

logger = logging.getLogger("aria.specialists")

Confidence = Literal["high", "medium", "low"]

SOLUTIONS_SYSTEM_PROMPT = """You are a senior Apple deployment engineer supporting a live sales call. A voice agent has come to you with a technical question she cannot answer from the sales material. You do not speak to the customer; you brief her.

You answer ONLY from the reference material you are given. This is not a style preference - a promise about software compatibility that turns out to be wrong is found out during a deployment, months later, and it is expensive.

The single most useful thing you do is be precise about the boundary. Split what you know from what you do not:
- What the material actually supports, stated plainly.
- What it does NOT cover, stated just as plainly, as a specific open question rather than a vague caveat. "Whether your in-house dispatch client has an Apple Silicon build" is useful. "Some software may need checking" is not.
- What would settle each open question, and who would settle it.

Never round a gap down to reassurance. "That should be fine" is the failure mode here.

Respond with ONLY a JSON object with exactly these keys:
"answer": what Aria should say, in two or three sentences of plain spoken English, no markdown. Lead with what IS supported.
"confidence": "high" if the material fully answers it, "medium" if it answers the substance but leaves specifics open, "low" if it does not really cover this.
"open_questions": array of short strings - the specific things that are genuinely unresolved. Empty if there are none.
"escalate_recommended": true only if the material does not support any useful answer and a human engineer is genuinely needed.
"""


class SolutionsAnswer(BaseModel):
    answer: str = ""
    confidence: Confidence = "low"
    open_questions: list[str] = Field(default_factory=list)
    escalate_recommended: bool = False


class SpecialistClient(Protocol):
    def complete(self, *, system: str, prompt: str) -> str: ...


class LLMSpecialistClient:
    def __init__(self, client=None):
        self._client = client

    def complete(self, *, system: str, prompt: str) -> str:
        client = self._client
        if client is None:
            from app.orchestrator.llm_client import default_llm_client

            client = self._client = default_llm_client()
        return client.create_turn(
            system=system, messages=[{"role": "user", "content": prompt}], tools=[]
        ).text


def _build_prompt(question: str, chunks: list[dict], context: str) -> str:
    material = "\n\n".join(
        f"[{chunk.get('source', 'reference')}]\n{chunk.get('text', '')}" for chunk in chunks
    )
    return (
        f"Customer's question: {question}\n"
        f"What we know about their setup: {context or 'nothing captured yet'}\n\n"
        f"Reference material:\n{material or '(the retriever found nothing relevant)'}"
    )


def heuristic_answer(chunks: list[dict]) -> SolutionsAnswer:
    """No-model fallback. It deliberately does not attempt an answer: making
    one up is the exact failure this specialist exists to prevent, so an
    unavailable specialist says so and hands the question on."""
    if not chunks:
        return SolutionsAnswer(
            answer=(
                "I do not want to guess at this one. Let me get one of our deployment "
                "engineers to confirm it properly."
            ),
            confidence="low",
            escalate_recommended=True,
        )
    return SolutionsAnswer(
        answer=(
            "Here is what our material covers on that - and anything specific to your own "
            "software I would rather have an engineer confirm than guess at."
        ),
        confidence="low",
        open_questions=["Compatibility of their specific in-house software"],
        escalate_recommended=False,
    )


def consult(
    *,
    question: str,
    chunks: list[dict],
    context: str = "",
    client: SpecialistClient | None = None,
) -> SolutionsAnswer:
    """Never raises: this sits on a live turn, and a specialist that cannot
    answer must degrade to saying so rather than to a failed turn."""
    active = client or LLMSpecialistClient()
    try:
        raw = active.complete(
            system=SOLUTIONS_SYSTEM_PROMPT, prompt=_build_prompt(question, chunks, context)
        )
        text = raw.strip()
        start, end = text.find("{"), text.rfind("}")
        return SolutionsAnswer(**json.loads(text[start : end + 1] if start != -1 else text))
    except Exception as exc:
        logger.warning("solutions engineer unavailable (%s)", exc)
        return heuristic_answer(chunks)
