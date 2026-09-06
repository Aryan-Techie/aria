"""The Agora-facing webhook: this route's full URL (minted per-session at
/join time — see agora/join_payload.py, build-order Step 3) is what we set
as `llm.url`. Agora calls this in an OpenAI-chat-completions-shaped request
whenever the user speaks; we respond in the same shape so it can be piped
into TTS.
"""
import hmac
import json
import logging
import time
import uuid
from typing import Iterator, Literal

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import get_settings
from app.escalation.models import TranscriptTurn
from app.language.profiles import strip_speech_markup
from app.orchestrator import pipeline
from app.rtm.publisher import default_rtm_publisher
from app.sessions.store import session_store

logger = logging.getLogger("aria")

router = APIRouter()


def _verify_shared_secret(authorization: str | None) -> None:
    """Agora echoes whatever we set as `llm.api_key` (join_payload.py) back on
    every webhook call, OpenAI-style, as `Authorization: Bearer <key>`.

    This endpoint is reachable from the public internet (Agora has to be able
    to call it), so it is the only thing standing between a stranger and an
    Anthropic bill. Skipped entirely when the secret is unset, which keeps the
    test suite and local no-credential dev hermetic.
    """
    expected = get_settings().llm_shared_secret
    if not expected:
        return
    provided = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str | None = None


class ChatCompletionsRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    stream: bool | None = False


def _history_from_openai_messages(messages: list[ChatMessage]) -> list[TranscriptTurn]:
    """Drops system messages (we own the persona/system prompt ourselves —
    see tools/prompts.py) and keeps user/assistant turns in order.

    Also drops blank/whitespace-only turns — found live, on a real call:
    Agora sends an empty-content message in some turns (an interim ASR slot
    or similar), and Anthropic's API rejects any message with empty content
    outright ("messages.N: user messages must have non-empty content"),
    turning an otherwise-normal turn into a hard 500 for the live call.
    """
    return [
        TranscriptTurn(role=m.role, content=m.content)
        for m in messages
        if m.role in ("user", "assistant") and m.content and m.content.strip()
    ]


NO_SPEECH_REPLY = "Sorry, I didn't quite catch that - could you say that again?"


def _publish_turn(session_id: str, turn_id: str, role: str, text: str, final: bool) -> None:
    """Puts one side of the conversation on the console's event stream.

    The console reads the transcript from here rather than from Agora's own
    transcript feed over RTM, which never reliably reached the page (same
    story as the tool events - see rtm/publisher.py::SessionEventRecorder).
    This route already sees every word: the user's turn arrives in the
    request, Aria's leaves in the response. Speech markup is stripped so
    the console shows what she says, not the pause tags the TTS reads.
    """
    default_rtm_publisher().publish(
        session_id,
        "transcript_turn",
        {"turn_id": turn_id, "role": role, "text": strip_speech_markup(text), "final": final},
    )


def _latest_user_text(history: list[TranscriptTurn]) -> str:
    return next((t.content for t in reversed(history) if t.role == "user"), "")


def _sse_chunk(chunk_id: str, model: str, created: int, delta: dict, finish: str | None) -> str:
    payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


def _stream_response(session_id: str, request: ChatCompletionsRequest) -> StreamingResponse:
    """Server-Sent Events, OpenAI chat.completion.chunk shaped.

    Agora begins TTS on the first chunk rather than waiting for the whole
    reply, so the customer hears the opening words while later tool hops are
    still running. Without this a tool-heavy turn took ~10s of silence, which
    is what pushes Agora into speaking its own `failure_message`.
    """
    session = session_store.get_or_create(session_id)
    history = _history_from_openai_messages(request.messages)
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = request.model or "aria-orchestrator"
    turn_id = chunk_id
    user_text = _latest_user_text(history)

    def generate() -> Iterator[str]:
        yield _sse_chunk(chunk_id, model, created, {"role": "assistant", "content": ""}, None)
        if user_text:
            _publish_turn(session_id, turn_id, "user", user_text, True)
        spoken: list[str] = []
        try:
            if not history:
                spoken.append(NO_SPEECH_REPLY)
                yield _sse_chunk(chunk_id, model, created, {"content": NO_SPEECH_REPLY}, None)
            else:
                for delta in pipeline.run_turn_stream(session, history):
                    if delta:
                        spoken.append(delta)
                        _publish_turn(session_id, turn_id, "assistant", "".join(spoken), False)
                        yield _sse_chunk(chunk_id, model, created, {"content": delta}, None)
        except Exception:
            # A crash mid-stream would otherwise drop the SSE connection with no
            # terminator, leaving Agora to time out and speak its failure_message.
            # Better to apologise in-character and keep the call alive.
            logger.exception("streamed turn failed, session=%s", session_id)
            apology = " Sorry, I lost my train of thought there - could you say that again?"
            spoken.append(apology)
            yield _sse_chunk(chunk_id, model, created, {"content": apology}, None)
        finally:
            session_store.save(session)
            if spoken:
                _publish_turn(session_id, turn_id, "assistant", "".join(spoken), True)
        yield _sse_chunk(chunk_id, model, created, {}, "stop")
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/agent/{session_id}/v1/chat/completions")
def chat_completions(
    session_id: str,
    request: ChatCompletionsRequest,
    authorization: str | None = Header(default=None),
):
    _verify_shared_secret(authorization)

    if request.stream:
        return _stream_response(session_id, request)

    session = session_store.get_or_create(session_id)
    history = _history_from_openai_messages(request.messages)

    if not history:
        # Every turn came in blank (e.g. an interim ASR slot with nothing
        # transcribed yet) — nothing meaningful to respond to, and Anthropic's
        # API requires at least one non-empty message, so skip the LLM call
        # entirely rather than erroring on an empty request.
        reply_text = NO_SPEECH_REPLY
    else:
        reply_text = pipeline.run_turn(session, history)
    session_store.save(session)

    turn_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    user_text = _latest_user_text(history)
    if user_text:
        _publish_turn(session_id, turn_id, "user", user_text, True)
    _publish_turn(session_id, turn_id, "assistant", reply_text, True)

    return {
        "id": turn_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model or "aria-orchestrator",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": reply_text},
                "finish_reason": "stop",
            }
        ],
    }
