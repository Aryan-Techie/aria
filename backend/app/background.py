"""Small shared thread pool for work that must never block a live call turn.

Agora gives the LLM webhook a limited window to respond before it gives up and
speaks its own `failure_message` (agora/join_payload.py). Anything that runs
inside `pipeline.run_turn` therefore spends the customer's patience directly:
a single turn was observed making two Anthropic calls *plus* five blocking
Agora RTM posts, each with a 5s timeout, before the reply was returned.

Work submitted here is fire-and-forget. The caller does not wait, the return
value is discarded, and a failure is logged rather than raised - appropriate
only for side effects the conversation does not depend on (UI events, memory
write-back), never for anything whose result the reply needs.
"""
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger("aria.background")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="aria-bg")


def run_in_background(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """Submits `fn` to the shared pool and returns immediately."""

    def _swallow() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.warning(
                "background task %s failed", getattr(fn, "__name__", repr(fn)), exc_info=True
            )

    _executor.submit(_swallow)
