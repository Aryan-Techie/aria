"""Does Agora actually let us change the voice mid-call on THIS account?

Everything else about voice switching is built and tested, but the one thing
tests cannot tell you is whether `POST /agents/{id}/update` is available to
this project under managed credentials. Agora documents runtime TTS updates
for custom-LLM setups, which is what this backend is - but this same account
has already had one (vendor, model) combination refused for its SKU, so
"documented" and "available to us" are not the same claim.

Run it against a call that is actually in progress:

    1. start a call in the console at http://localhost:3000
    2. python scripts/check_voice_switch.py
    3. keep talking - the voice should change within a sentence or two

It finds the live agent itself, switches the voice, waits, and switches back,
printing exactly what Agora returned at each step. A 404 or 405 on the update
means the endpoint is not there for this account and VOICE_SWITCHING_ENABLED
should stay off; anything else is worth reading in full.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--voice",
        default="",
        help="voice/speaker to switch to (default: the profile's deal-desk voice) - "
        "a MiniMax voice id under TTS_VENDOR=minimax, a Sarvam speaker under sarvam",
    )
    parser.add_argument("--hold", type=float, default=12.0, help="seconds to keep the new voice before reverting")
    parser.add_argument("--agent-id", default="", help="skip discovery and use this agent id")
    args = parser.parse_args()

    import httpx

    from app.agora.client import default_agora_client
    from app.config import get_settings
    from app.language.profiles import get_profile
    from app.sessions.store import session_store
    from app.voice.director import resolve_sarvam_target, resolve_voice

    settings = get_settings()
    profile = get_profile(settings.agent_language)
    client = default_agora_client()

    agent_id = args.agent_id
    if not agent_id:
        live = [s for s in session_store.all() if s.status == "active" and s.agent_id]
        if live:
            agent_id = live[-1].agent_id
        else:
            # The session store is in the backend's process, not this one, so
            # fall back to asking Agora which agents it is running for us.
            try:
                agents = client.list_agents().get("data", []) or []
            except Exception as exc:
                print(f"Could not list agents: {exc}", file=sys.stderr)
                agents = []
            running = [a for a in agents if str(a.get("status", "")).upper() in ("RUNNING", "STARTING")]
            if not running:
                print("No running agent found. Start a call at http://localhost:3000 first.", file=sys.stderr)
                return 1
            agent_id = running[-1].get("agent_id") or running[-1].get("id")

    if settings.tts_vendor == "sarvam":
        original = resolve_sarvam_target(profile, role="aria")
        target = (
            {"speaker": args.voice, "target_language_code": profile.sarvam_language_code}
            if args.voice
            else resolve_sarvam_target(profile, role="deal_desk")
        )
    else:
        original = settings.minimax_voice_id or profile.voice_id
        target = args.voice or profile.agent_voices.get("deal_desk") or original

    print(f"agent    : {agent_id}")
    print(f"profile  : {profile.code}")
    print(f"vendor   : {settings.tts_vendor}")
    print(f"switching: {original}  ->  {target}")

    def switch(voice) -> bool:
        params = {"voice_setting": {"voice_id": voice}} if isinstance(voice, str) else voice
        payload = {"tts": {"params": params}}
        try:
            client.update(agent_id, payload)
            print(f"  [OK]  update accepted -> {voice}")
            return True
        except httpx.HTTPStatusError as exc:
            body = exc.response.text[:400]
            print(f"  [X]   HTTP {exc.response.status_code}: {body}")
            if exc.response.status_code in (404, 405):
                print("        This account/route does not support runtime updates.")
                print("        Leave VOICE_SWITCHING_ENABLED=false.")
            return False
        except Exception as exc:
            print(f"  [X]   {type(exc).__name__}: {exc}")
            return False

    if not switch(target):
        return 1

    print(f"  ...listening window: {args.hold:g}s - keep talking, the voice should change")
    time.sleep(args.hold)
    switch(original)

    print()
    print("If you heard the voice change and change back, set VOICE_SWITCHING_ENABLED=true")
    print("in .env and restart the backend. If the update was accepted but nothing")
    print("changed, Agora took the call and ignored the field - also leave it off.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
