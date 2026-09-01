"""Which model answers a real turn fastest, measured rather than assumed.

Runs candidate models against the ACTUAL system prompt and the ACTUAL tool
schemas this backend sends, because a benchmark on a toy prompt tells you
nothing: our fixed per-hop cost is ~4,600 tokens and that is most of what a
model is doing before it emits anything.

Two numbers matter and they are not the same one:

  * **TTFT** - time to the first token. This is what the customer feels, since
    Agora starts speaking on the first chunk it receives.
  * **total** - time to the end of the hop, which is what the *next* hop waits
    on and what decides whether a tool call lands inside Agora's window.

It also reports whether the model actually produced the tool call the turn
needed. A model that is fast and picks the wrong tool is not a faster agent,
it is a broken one - so `tool` in the output is a pass/fail gate, not a
statistic.

    python scripts/bench_llm.py
    python scripts/bench_llm.py --models openai/gpt-oss-20b,qwen/qwen3.8-27b --runs 5
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

CANDIDATES = [
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "qwen/qwen3.6-27b",
    "groq/compound-mini",
]

# A turn that MUST call a tool, so tool-calling accuracy is measured on the
# same run as the latency rather than assumed from a separate one.
TOOL_TURN = [
    {"role": "user", "content": "Hi, this is Priya from Northwind Logistics. We need about 60 MacBooks."},
]
# ...and one that must NOT, because a model that calls a tool on a greeting
# spends a whole extra hop before it says anything.
CHAT_TURN = [
    {"role": "user", "content": "Hello, is this the Apple business team?"},
]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))], 3)


def bench(model: str, api_key: str, runs: int, reasoning_effort: str) -> dict:
    from groq import Groq

    from app.orchestrator.llm_client import _messages_to_openai, _tools_to_openai
    from app.tools import definitions
    from app.tools.prompts import build_system_prompt

    client = Groq(api_key=api_key, timeout=30.0, max_retries=0)
    system = build_system_prompt()
    tools = _tools_to_openai(definitions.TOOLS)

    ttfts: list[float] = []
    totals: list[float] = []
    tool_hits = 0
    chat_clean = 0
    error = None

    for index in range(runs):
        messages = TOOL_TURN if index % 2 == 0 else CHAT_TURN
        kwargs = {
            "model": model,
            "messages": _messages_to_openai(system, messages),
            "max_completion_tokens": 400,
            "temperature": 0.6,
            "tools": tools,
            "tool_choice": "auto",
            "stream": True,
        }
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort

        started = time.perf_counter()
        first = None
        called: list[str] = []
        try:
            for chunk in client.chat.completions.create(**kwargs):
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if first is None and (getattr(delta, "content", None) or getattr(delta, "tool_calls", None)):
                    first = time.perf_counter() - started
                for call in getattr(delta, "tool_calls", None) or []:
                    fn = getattr(call, "function", None)
                    if fn is not None and fn.name:
                        called.append(fn.name)
        except Exception as exc:  # noqa: BLE001 - a benchmark reports, it does not raise
            error = f"{type(exc).__name__}: {exc}"
            break

        totals.append(time.perf_counter() - started)
        if first is not None:
            ttfts.append(first)
        if index % 2 == 0:
            tool_hits += int("crm_upsert_lead" in called)
        else:
            chat_clean += int(not called)

    return {
        "model": model,
        "error": error,
        "runs": len(totals),
        "ttft_p50": _percentile(ttfts, 0.5),
        "ttft_p95": _percentile(ttfts, 0.95),
        "total_p50": _percentile(totals, 0.5),
        "total_mean": round(statistics.fmean(totals), 3) if totals else 0.0,
        "tool_turns_correct": tool_hits,
        "chat_turns_clean": chat_clean,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default=",".join(CANDIDATES))
    parser.add_argument("--runs", type=int, default=4)
    parser.add_argument("--reasoning-effort", default="none")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    from app.config import Settings, get_settings

    Settings.model_config["env_file"] = None
    get_settings.cache_clear()

    api_key = args.api_key
    if not api_key:
        import os
        import re

        env = (Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8")
        match = re.search(r"(?m)^GROQ_API_KEY=(.+)$", env)
        api_key = (match.group(1).strip() if match else "") or os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        print("No GROQ_API_KEY found in .env or the environment.", file=sys.stderr)
        return 1

    results = [bench(m.strip(), api_key, args.runs, args.reasoning_effort) for m in args.models.split(",") if m.strip()]
    results.sort(key=lambda r: (r["error"] is not None, r["ttft_p50"] or 99))

    print(f"{'model':<28} {'ttft p50':>9} {'ttft p95':>9} {'total p50':>10}  {'tools':>5} {'chat':>5}")
    print("-" * 76)
    for r in results:
        if r["error"]:
            print(f"{r['model']:<28} {r['error'][:44]}")
            continue
        print(
            f"{r['model']:<28} {r['ttft_p50']:>9.3f} {r['ttft_p95']:>9.3f} "
            f"{r['total_p50']:>10.3f}  {r['tool_turns_correct']:>5} {r['chat_turns_clean']:>5}"
        )
    print()
    print("ttft = what the customer feels (Agora speaks on the first chunk).")
    print("tools/chat = correct tool call made / greeting answered without one. Both must be non-zero.")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
