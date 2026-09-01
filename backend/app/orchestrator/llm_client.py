"""Adapter over the Anthropic SDK. Pipeline code only depends on the small
`LLMTurn`/`ToolCall` shapes below, never on raw Anthropic response objects —
that's what makes the tool-calling loop in pipeline.py testable with a fake
client and no network/API key.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Iterator, Protocol

logger = logging.getLogger("aria.llm")


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMTurn:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"

    @property
    def wants_tool_use(self) -> bool:
        return bool(self.tool_calls)


class ChatLLMClient(Protocol):
    def create_turn(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn: ...


class StreamingChatLLMClient(ChatLLMClient, Protocol):
    """Adds token streaming on top of ChatLLMClient.

    `stream_turn` yields ("text", delta) as tokens arrive and finally
    ("done", LLMTurn) once the message is complete - so the caller can start
    speaking the first words while the rest is still generating, rather than
    waiting for the whole reply.
    """

    def stream_turn(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> Iterator[tuple[str, object]]: ...


class AnthropicChatClient:
    def __init__(self, api_key: str, model: str, max_tokens: int = 1024):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        """One client for the process, not one per turn.

        This used to construct `anthropic.Anthropic(...)` on every call, which
        threw away the connection pool and paid a fresh TLS handshake on each
        hop - two or three times per spoken reply, on the critical path.
        """
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def create_turn(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn:
        client = self._get_client()
        # `tools` is omitted rather than passed empty: the deal desk
        # (app/deal/desk.py) reuses this client for a plain JSON completion
        # with no toolset, and an empty array is not the same thing as no
        # tools to the API.
        kwargs = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        response = client.messages.create(**kwargs)
        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in response.content
            if b.type == "tool_use"
        ]
        return LLMTurn(text=text, tool_calls=tool_calls, stop_reason=response.stop_reason)

    def stream_turn(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> Iterator[tuple[str, object]]:
        client = self._get_client()
        with client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        ) as stream:
            for event in stream:
                if (
                    event.type == "content_block_delta"
                    and getattr(event.delta, "type", None) == "text_delta"
                ):
                    yield ("text", event.delta.text)
            final = stream.get_final_message()

        text = "".join(b.text for b in final.content if b.type == "text")
        tool_calls = [
            ToolCall(id=b.id, name=b.name, input=b.input)
            for b in final.content
            if b.type == "tool_use"
        ]
        yield ("done", LLMTurn(text=text, tool_calls=tool_calls, stop_reason=final.stop_reason))


# --------------------------------------------------------------------------
# Groq
# --------------------------------------------------------------------------
# The pipeline speaks Anthropic's block format (tool_use / tool_result blocks
# inside message content). Groq speaks OpenAI's (a `tool_calls` array on the
# assistant message, and separate role="tool" messages). These helpers convert
# between the two so the pipeline never has to care which provider is serving
# the turn.


def _tools_to_openai(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for tool in tools
    ]


def _messages_to_openai(system: str, messages: list[dict]) -> list[dict]:
    converted: list[dict] = [{"role": "system", "content": system}]

    for message in messages:
        content = message.get("content")
        role = message.get("role")

        if isinstance(content, str):
            converted.append({"role": role, "content": content})
            continue

        blocks = content or []

        if role == "assistant":
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            tool_calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            ]
            assistant: dict = {"role": "assistant", "content": text or None}
            if tool_calls:
                assistant["tool_calls"] = tool_calls
            converted.append(assistant)
            continue

        # user turn: either plain text blocks or the tool_result blocks the
        # pipeline appends after running a hop's tools
        for block in blocks:
            if block.get("type") == "tool_result":
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block.get("content", ""),
                    }
                )
            elif block.get("type") == "text":
                converted.append({"role": "user", "content": block.get("text", "")})

    return converted


def _parse_arguments(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class GroqChatClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 1024,
        reasoning_effort: str = "none",
        timeout_seconds: float = 6.0,
    ):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._reasoning_effort = reasoning_effort
        self._timeout_seconds = timeout_seconds
        self._client = None

    def _get_client(self):
        if self._client is None:
            from groq import Groq

            # max_retries=0: a rate-limited call must surface immediately so
            # the fallback can serve the turn. Retrying just spends more of
            # the customer's silence waiting for a window that has not reset.
            self._client = Groq(
                api_key=self._api_key,
                timeout=self._timeout_seconds,
                max_retries=0,
            )
        return self._client

    def _kwargs(self, system: str, messages: list[dict], tools: list[dict]) -> dict:
        kwargs = {
            "model": self._model,
            "messages": _messages_to_openai(system, messages),
            "max_completion_tokens": self._max_tokens,
            "temperature": 0.6,
        }
        if tools:
            kwargs["tools"] = _tools_to_openai(tools)
            kwargs["tool_choice"] = "auto"
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort
        return kwargs

    def create_turn(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn:
        response = self._get_client().chat.completions.create(**self._kwargs(system, messages, tools))
        choice = response.choices[0]
        raw_calls = getattr(choice.message, "tool_calls", None) or []
        return LLMTurn(
            text=choice.message.content or "",
            tool_calls=[
                ToolCall(id=c.id, name=c.function.name, input=_parse_arguments(c.function.arguments))
                for c in raw_calls
            ],
            stop_reason=choice.finish_reason or "end_turn",
        )

    def stream_turn(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> Iterator[tuple[str, object]]:
        stream = self._get_client().chat.completions.create(
            stream=True, **self._kwargs(system, messages, tools)
        )

        text_parts: list[str] = []
        # Tool calls arrive as deltas keyed by index and must be reassembled -
        # the name and the JSON arguments both stream in fragments.
        pending: dict[int, dict] = {}
        finish_reason = "end_turn"

        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta

            if getattr(delta, "content", None):
                text_parts.append(delta.content)
                yield ("text", delta.content)

            for call in getattr(delta, "tool_calls", None) or []:
                slot = pending.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                if call.id:
                    slot["id"] = call.id
                function = getattr(call, "function", None)
                if function is not None:
                    if function.name:
                        slot["name"] += function.name
                    if function.arguments:
                        slot["arguments"] += function.arguments

        tool_calls = [
            ToolCall(id=slot["id"], name=slot["name"], input=_parse_arguments(slot["arguments"]))
            for _, slot in sorted(pending.items())
            if slot["name"]
        ]
        yield (
            "done",
            LLMTurn(text="".join(text_parts), tool_calls=tool_calls, stop_reason=finish_reason),
        )


class FallbackChatClient:
    """Runs `primary`, and falls back to `secondary` if it raises.

    For streaming this can only fall back before the first token is handed
    out - once the customer is hearing words, switching providers mid-sentence
    would produce a spliced reply, so a later failure is allowed to propagate
    to the route's error handling instead.
    """

    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def create_turn(self, *, system: str, messages: list[dict], tools: list[dict]) -> LLMTurn:
        try:
            return self._primary.create_turn(system=system, messages=messages, tools=tools)
        except Exception as exc:
            logger.warning("primary LLM unavailable (%s), falling back", type(exc).__name__)
            return self._secondary.create_turn(system=system, messages=messages, tools=tools)

    def stream_turn(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> Iterator[tuple[str, object]]:
        try:
            stream = self._primary.stream_turn(system=system, messages=messages, tools=tools)
            first = next(stream)
        except StopIteration:
            return
        except Exception as exc:
            logger.warning("primary LLM stream unavailable (%s), falling back", type(exc).__name__)
            yield from self._secondary.stream_turn(system=system, messages=messages, tools=tools)
            return

        yield first
        yield from stream


def default_llm_client() -> ChatLLMClient:
    """Groq first for latency, Anthropic behind it as the safety net.

    Falls straight through to Anthropic when Groq is unconfigured or the
    provider is switched over, so a missing GROQ_API_KEY degrades to the
    previous behaviour rather than breaking calls.
    """
    from app.config import get_settings

    settings = get_settings()

    if settings.llm_provider != "groq" or not settings.groq_api_key:
        # Anthropic is the only provider, so it is the conversation - not a
        # fallback - and gets the stronger model.
        return AnthropicChatClient(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )

    # Behind Groq, speed is what this is for. See anthropic_fallback_model.
    anthropic = AnthropicChatClient(
        api_key=settings.anthropic_api_key, model=settings.anthropic_fallback_model
    )

    groq = GroqChatClient(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        reasoning_effort=settings.groq_reasoning_effort,
        timeout_seconds=settings.groq_timeout_seconds,
    )
    return FallbackChatClient(groq, anthropic)
