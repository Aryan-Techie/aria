"""How many conversations does Aria actually hold at once?

Runs N simultaneous calls through the real turn loop and reports what it
measured. Two modes, and the difference between them is the whole point:

  --mode pipeline   (default, no keys, no network)
      Drives pipeline.run_turn_stream directly with a scripted buyer and a
      stubbed model, N sessions at a time. Every tool really runs: the CRM is
      written, the deal desk consulted, the calendar booked. This measures OUR
      concurrency - the tool loop, the stores, the locks - with the one part
      we do not control removed.

  --mode live       (needs a running backend)
      POSTs real turns at {base}/agent/{id}/v1/chat/completions, N at a time,
      exactly as Agora does. This measures the whole thing end to end, and in
      practice it measures the LLM provider's rate limit, because that is
      where a turn spends most of its time.

Be honest about which number is being quoted. "We handled 64 concurrent
conversations" from --mode pipeline means our code did not fall over at 64; it
does not mean a Groq free tier will serve 64. Run both and quote both.

    python scripts/capacity_test.py --sessions 32 --turns 6
    python scripts/capacity_test.py --mode live --base http://localhost:8000 --sessions 8
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def use_hermetic_settings() -> None:
    """Ignore the developer's .env, the same way the test suite does.

    Without this the harness picks up CRM_BACKEND=espocrm and every simulated
    call tries to write to a real CRM. Measured: with EspoCRM not running,
    each write spent five seconds in a connection timeout and the reported p95
    was almost entirely that - a number about Docker, not about concurrency.
    Pass --real-env to measure the stack as configured, deliberately.
    """
    from app.config import Settings, get_settings

    Settings.model_config["env_file"] = None
    get_settings.cache_clear()


# The scripted buyer. Deliberately the awkward path rather than a happy one:
# a price question, an objection, a requirement change, a discount push, a
# second discount push, then a booking. Every one of those exercises a
# different tool, so the measurement covers the loop that actually runs on a
# real call rather than a single cheap turn repeated.
BUYER_TURNS = [
    "Hi, this is Priya from Northwind Logistics. We're looking at moving the team to Mac.",
    "That's a lot more than the Windows laptops we usually buy.",
    "Actually it's more like sixty devices, not twenty five.",
    "What kind of discount can you do on sixty?",
    "That's still not enough - Dell came in well under that.",
    "Alright. Can we get a time in the diary with someone?",
]


class ScriptedLLM:
    """A model that calls a plausible tool for each turn and then answers.

    Not a no-op: it returns real tool calls, so the CRM write, the deal desk
    consult, the calendar lookup and the booking all happen for real on every
    simulated call. What it removes is the network round trip to a provider,
    which is the thing being deliberately excluded from this measurement.
    """

    def __init__(self) -> None:
        self._hops: dict[int, int] = {}
        self._lock = threading.Lock()

    def begin(self) -> None:
        """Reset this thread's position in the script.

        The hop counter is keyed by thread, and a thread pool reuses threads:
        a worker that finishes one simulated call and picks up another would
        otherwise start it halfway through the script, so some calls never
        reached the negotiation turns at all.
        """
        with self._lock:
            self._hops[threading.get_ident()] = 0

    def _tool_for(self, turn_index: int):
        from app.orchestrator.llm_client import ToolCall

        call_id = uuid.uuid4().hex
        if turn_index == 0:
            return ToolCall(id=call_id, name="crm_upsert_lead", input={"company": "Northwind Logistics", "user_count": 25, "name": "Priya"})
        if turn_index == 1:
            return ToolCall(id=call_id, name="search_pricing_rag", input={"query": "mac vs windows total cost"})
        if turn_index == 2:
            return ToolCall(id=call_id, name="crm_upsert_lead", input={"user_count": 60})
        if turn_index in (3, 4):
            return ToolCall(id=call_id, name="negotiate_deal", input={"customer_ask": "discount please", "requested_discount_pct": 12})
        return ToolCall(id=call_id, name="calendar_check_availability", input={})

    def stream_turn(self, *, system, messages, tools):
        from app.orchestrator.llm_client import LLMTurn

        key = threading.get_ident()
        with self._lock:
            hop = self._hops.get(key, 0)
            self._hops[key] = hop + 1

        # First hop of a turn calls a tool; the second concludes it. That is
        # the shape of a real turn, and it is what makes the hop count and the
        # bridge line behave as they do live.
        if hop % 2 == 0:
            turn_index = min(hop // 2, len(BUYER_TURNS) - 1)
            yield ("done", LLMTurn(text="", tool_calls=[self._tool_for(turn_index)]))
        else:
            for chunk in ("Understood. ", "Here is where that leaves us."):
                yield ("text", chunk)
            yield ("done", LLMTurn(text="Understood. Here is where that leaves us."))

    def create_turn(self, *, system, messages, tools):
        from app.orchestrator.llm_client import LLMTurn

        return LLMTurn(text=json.dumps({"recommended_discount_pct": 6.0, "commitments": [{"kind": "decision_by", "detail": "Decide by Friday."}]}))


class StubDesk:
    """The deal desk, stubbed the same way and for the same reason."""

    def complete(self, *, system: str, prompt: str) -> str:
        return json.dumps(
            {
                "recommended_discount_pct": 8.0,
                "concessions": [{"kind": "trade_in", "detail": "Trade in the old fleet.", "value_usd": 0}],
                "commitments": [{"kind": "decision_by", "detail": "Decide by Friday."}],
                "rationale": "load test",
                "read": "load test",
            }
        )


def run_pipeline_mode(sessions: int, turns: int) -> dict:
    from app.deal import desk
    from app.escalation.models import TranscriptTurn
    from app.orchestrator import pipeline
    from app.sessions.models import SessionState
    from app.sessions.store import session_store

    real_consult = desk.consult
    desk.consult = lambda **kwargs: real_consult(**{**kwargs, "client": StubDesk()})

    llm = ScriptedLLM()
    latencies: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()

    def one_call(index: int) -> None:
        llm.begin()
        state = SessionState(session_id=f"load-{index}-{uuid.uuid4().hex[:8]}")
        session_store.save(state)
        history: list[TranscriptTurn] = []

        for turn_index in range(turns):
            history.append(TranscriptTurn(role="user", content=BUYER_TURNS[turn_index % len(BUYER_TURNS)]))
            started = time.perf_counter()
            try:
                reply = "".join(
                    pipeline.run_turn_stream(
                        state,
                        list(history),
                        llm_client=llm,
                        memory_recall=lambda *_: [],
                        memory_write_back=lambda *_: None,
                    )
                )
                history.append(TranscriptTurn(role="assistant", content=reply))
            except Exception as exc:  # noqa: BLE001 - a load test reports failures, it does not raise them
                with lock:
                    errors.append(f"{type(exc).__name__}: {exc}")
                continue
            with lock:
                latencies.append(time.perf_counter() - started)

        # Whatever the run actually produced is what gets reported. Stamping
        # an outcome on here would make the capacity snapshot below a
        # description of this line rather than of the calls.
        state.status = "ended"
        state.ended_at = datetime.now(timezone.utc)
        session_store.save(state)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=sessions) as pool:
        futures = [pool.submit(one_call, i) for i in range(sessions)]
        for future in as_completed(futures):
            future.result()
    wall = time.perf_counter() - started

    desk.consult = real_consult
    return _report("pipeline", sessions, turns, wall, latencies, errors)


def run_live_mode(base: str, sessions: int, turns: int, secret: str) -> dict:
    import httpx

    latencies: list[float] = []
    errors: list[str] = []
    lock = threading.Lock()
    headers = {"Authorization": f"Bearer {secret}"} if secret else {}

    def one_call(index: int) -> None:
        session_id = f"load-{index}-{uuid.uuid4().hex[:8]}"
        messages = []
        with httpx.Client(timeout=60.0) as client:
            for turn_index in range(turns):
                messages.append({"role": "user", "content": BUYER_TURNS[turn_index % len(BUYER_TURNS)]})
                started = time.perf_counter()
                try:
                    response = client.post(
                        f"{base}/agent/{session_id}/v1/chat/completions",
                        json={"model": "aria", "messages": messages, "stream": True},
                        headers=headers,
                    )
                    response.raise_for_status()
                    messages.append({"role": "assistant", "content": response.text[:400]})
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(f"{type(exc).__name__}: {exc}")
                    continue
                with lock:
                    latencies.append(time.perf_counter() - started)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=sessions) as pool:
        for future in as_completed([pool.submit(one_call, i) for i in range(sessions)]):
            future.result()
    wall = time.perf_counter() - started
    return _report("live", sessions, turns, wall, latencies, errors)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 3)


def _report(mode, sessions, turns, wall, latencies, errors) -> dict:
    return {
        "mode": mode,
        "concurrent_sessions": sessions,
        "turns_per_session": turns,
        "turns_completed": len(latencies),
        "turns_failed": len(errors),
        "wall_seconds": round(wall, 2),
        "turns_per_second": round(len(latencies) / wall, 2) if wall else 0.0,
        "turn_latency_seconds": {
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "p99": _percentile(latencies, 0.99),
            "max": round(max(latencies), 3) if latencies else 0.0,
            "mean": round(statistics.fmean(latencies), 3) if latencies else 0.0,
        },
        "first_errors": errors[:5],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=("pipeline", "live"), default="pipeline")
    parser.add_argument("--sessions", type=int, default=16, help="calls held at the same time")
    parser.add_argument("--turns", type=int, default=6, help="customer turns per call")
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--secret", default="", help="LLM_SHARED_SECRET, for live mode")
    parser.add_argument(
        "--real-env",
        action="store_true",
        help="read the real .env - measures the stack as configured, CRM included",
    )
    args = parser.parse_args()

    if args.mode == "pipeline" and not args.real_env:
        use_hermetic_settings()

    if args.mode == "pipeline":
        result = run_pipeline_mode(args.sessions, args.turns)
        from app.metrics import capacity
        from app.sessions.store import session_store

        result["capacity"] = capacity.snapshot(session_store.all())
    else:
        result = run_live_mode(args.base, args.sessions, args.turns, args.secret)

    print(json.dumps(result, indent=2, default=str))

    latency = result["turn_latency_seconds"]
    print(
        f"\n{result['concurrent_sessions']} concurrent calls, "
        f"{result['turns_completed']} turns in {result['wall_seconds']}s "
        f"({result['turns_per_second']}/s), p95 {latency['p95']}s, "
        f"{result['turns_failed']} failed.",
        file=sys.stderr,
    )
    if args.mode == "pipeline":
        print(
            "Measured with the model stubbed out: this is our concurrency, not a "
            "provider's. Run --mode live against a real backend for the end-to-end number.",
            file=sys.stderr,
        )
    return 1 if result["turns_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
