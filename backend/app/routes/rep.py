"""The warm-transfer page: a person stepping into a live call.

After an escalation the console shows a link (`/rep/{escalation_id}`, on
the backend's public URL). Whoever opens it - from any city, on any
device - sees the brief Aria wrote and a single "Join call" button. The
button joins the customer's RTC channel with a token minted here, and the
moment their mic is up the backend has Aria say her handoff line and leave
the channel. The customer never hangs up; the voice on the line changes.

Served as one self-contained HTML page off this backend rather than off
the Next.js console, so nothing but the backend tunnel has to be reachable
from outside and there is no second origin to allow through CORS.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.agora.client import default_agora_client
from app.agora.rtc_token import build_rtc_token
from app.background import run_in_background
from app.config import get_settings
from app.escalation.inbox import inbox
from app.rtm.publisher import default_rtm_publisher
from app.sessions.store import session_store

logger = logging.getLogger("aria")

router = APIRouter()

# How long Aria gets to finish the handoff sentence before she is pulled.
# /speak returns as soon as TTS is queued, not when it has been heard.
_HANDOFF_LINE_SECONDS = 5.0


def _handoff_line(rep_name: str) -> str:
    return (
        f"{rep_name} from our team is on the line now and has the full context. "
        f"I'll hand you over - thanks for your patience."
    )


@router.get("/api/handoff/{escalation_id}")
def handoff_details(escalation_id: str) -> dict:
    """Everything the join page needs: the brief, the lead, and RTC credentials."""
    record = inbox.get(escalation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No such escalation")
    session = session_store.get(record.session_id)
    if session is None or not session.agora_channel:
        raise HTTPException(status_code=404, detail="That call is no longer live")

    settings = get_settings()
    uid = settings.handoff_rep_rtc_uid
    token = build_rtc_token(settings.agora_app_id, settings.agora_app_certificate, session.agora_channel, uid)

    return {
        "escalation_id": record.id,
        "session_id": session.session_id,
        "rep_name": settings.handoff_rep_name,
        "call_live": session.status != "ended",
        "aria_on_call": session.agent_id is not None,
        "reason": record.reason,
        "trigger_source": record.trigger_source,
        "brief": record.brief.model_dump(mode="json"),
        "lead": record.left_brain.model_dump(mode="json"),
        "signals": record.right_brain.model_dump(mode="json"),
        "transcript": [t.model_dump(mode="json") for t in record.transcript][-12:],
        "rtc": {
            "app_id": settings.agora_app_id,
            "channel": session.agora_channel,
            "uid": uid,
            "token": token,
        },
    }


def _hand_over(session_id: str, agent_id: str, rep_name: str) -> None:
    """Aria announces the handoff, then leaves. Backgrounded: the rep's
    browser is waiting on the POST and must not sit through the sentence."""
    client = default_agora_client()
    try:
        client.speak(agent_id, _handoff_line(rep_name))
        time.sleep(_HANDOFF_LINE_SECONDS)
    except Exception:
        logger.exception("handoff line failed, leaving anyway, session=%s", session_id)
    try:
        client.leave(agent_id)
    except Exception:
        logger.exception("agent leave failed on handoff, session=%s", session_id)
    session = session_store.get(session_id)
    if session is not None:
        session.agent_id = None
        session_store.save(session)
    default_rtm_publisher().publish(session_id, "aria_left", {"rep_name": rep_name})


@router.post("/api/handoff/{escalation_id}/joined")
def rep_joined(escalation_id: str) -> dict:
    """Called by the join page once the rep's mic is published."""
    record = inbox.get(escalation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="No such escalation")
    session = session_store.get(record.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="That call is no longer live")

    rep_name = get_settings().handoff_rep_name
    default_rtm_publisher().publish(session.session_id, "rep_joined", {"rep_name": rep_name})

    if session.agent_id:
        run_in_background(_hand_over, session.session_id, session.agent_id, rep_name)
        return {"status": "handing_over", "rep_name": rep_name}
    return {"status": "joined", "rep_name": rep_name}


@router.get("/rep/{escalation_id}", response_class=HTMLResponse)
def rep_page(escalation_id: str) -> str:
    return _PAGE.replace("__ESCALATION_ID__", escalation_id)


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Join call</title>
<style>
  :root { --ink:#1d1d1f; --ink2:#515154; --ink3:#86868b; --line:#e5e5ea; --bg:#f5f5f7; --surface:#fff; --accent:#0a84ff; --bad:#ff3b30; --good:#30d158; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif; }
  main { max-width:560px; margin:0 auto; padding:28px 18px 60px; }
  h1 { font-size:24px; letter-spacing:-0.02em; margin:0 0 4px; }
  .sub { color:var(--ink3); margin:0 0 22px; }
  .card { background:var(--surface); border:1px solid var(--line); border-radius:16px; padding:18px 20px; margin-bottom:14px; }
  .card h3 { margin:0 0 10px; font-size:11.5px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--ink3); }
  .reason { font-size:17px; font-weight:600; margin:0 0 6px; }
  dl { display:grid; grid-template-columns:auto 1fr; gap:6px 14px; margin:0; }
  dt { color:var(--ink3); font-size:13px; } dd { margin:0; }
  .turn { padding:6px 0; border-top:1px solid var(--line); font-size:14px; }
  .turn b { color:var(--ink3); font-weight:500; font-size:12px; display:block; }
  .join { position:sticky; bottom:18px; margin-top:20px; }
  button { width:100%; padding:16px; border:0; border-radius:14px; font:inherit; font-size:17px; font-weight:600; color:#fff; background:var(--accent); cursor:pointer; box-shadow:0 8px 24px rgba(10,132,255,.3); }
  button.end { background:var(--bad); box-shadow:0 8px 24px rgba(255,59,48,.3); }
  button:disabled { opacity:.5; cursor:default; }
  .state { text-align:center; color:var(--ink2); margin:10px 0 0; min-height:22px; }
  .state.bad { color:var(--bad); }
  .live { display:inline-flex; align-items:center; gap:6px; }
  .live i { width:8px; height:8px; border-radius:50%; background:var(--good); box-shadow:0 0 0 4px rgba(48,209,88,.18); }
</style>
</head>
<body>
<main>
  <h1 id="title">Loading the brief…</h1>
  <p class="sub" id="subtitle"></p>
  <div id="content"></div>
  <div class="join">
    <button id="join" disabled>Join call</button>
    <p class="state" id="state"></p>
  </div>
</main>
<script src="https://download.agora.io/sdk/release/AgoraRTC_N.js"></script>
<script>
(async () => {
  const id = "__ESCALATION_ID__";
  const $ = (s) => document.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
  const btn = $("#join"), state = $("#state");

  let info;
  try {
    const res = await fetch(`/api/handoff/${id}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    info = await res.json();
  } catch (e) {
    $("#title").textContent = "This call isn't available";
    $("#subtitle").textContent = e.message;
    btn.hidden = true;
    return;
  }

  const lead = info.lead || {}, b = info.brief || {};
  $("#title").textContent = `${info.rep_name}, a customer is waiting`;
  $("#subtitle").innerHTML = info.call_live
    ? `<span class="live"><i></i>Live now · Aria ${info.aria_on_call ? "is holding the line" : "has already left"}</span>`
    : "This call has ended.";
  $("#content").innerHTML = `
    <div class="card">
      <h3>Why you</h3>
      <p class="reason">${esc(info.reason)}</p>
      <p style="margin:0;color:var(--ink2)">${esc(b.recommended_action)}</p>
    </div>
    <div class="card">
      <h3>Lead</h3>
      <dl>
        <dt>Company</dt><dd>${esc(lead.company || "—")}</dd>
        <dt>Devices</dt><dd>${esc(lead.user_count ?? "—")}</dd>
        <dt>Budget</dt><dd>${esc(lead.budget_range || "—")}</dd>
        <dt>Timeline</dt><dd>${esc(lead.timeline || "—")}</dd>
        <dt>Stage</dt><dd>${esc(lead.decision_stage || "—")}</dd>
        <dt>Mood</dt><dd>${esc(b.sentiment || "—")}</dd>
        <dt>Blocker</dt><dd>${esc(b.blocker || "—")}</dd>
      </dl>
    </div>
    <div class="card">
      <h3>Last few turns</h3>
      ${(info.transcript || []).map(t => `<div class="turn"><b>${t.role === "user" ? "Customer" : "Aria"}</b>${esc(t.content)}</div>`).join("") || "<p style='margin:0;color:var(--ink3)'>Nothing yet.</p>"}
    </div>`;

  if (!info.call_live) { btn.hidden = true; return; }
  btn.disabled = false;

  let client = null, mic = null;
  btn.onclick = async () => {
    if (client) {
      btn.disabled = true;
      try { mic && mic.close(); await client.leave(); } catch {}
      client = null; mic = null;
      btn.textContent = "Left the call"; state.textContent = "";
      return;
    }
    btn.disabled = true; state.className = "state"; state.textContent = "Joining…";
    try {
      const { app_id, channel, uid, token } = info.rtc;
      client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      client.on("user-published", async (user, mediaType) => {
        await client.subscribe(user, mediaType);
        if (mediaType === "audio") user.audioTrack.play();
      });
      await client.join(app_id, channel, token, uid);
      mic = await AgoraRTC.createMicrophoneAudioTrack();
      await client.publish([mic]);
      const r = await fetch(`/api/handoff/${id}/joined`, { method: "POST" }).then(r => r.json());
      state.textContent = r.status === "handing_over"
        ? "You're in. Aria is handing over to you, then leaving."
        : "You're in. You have the call.";
      btn.textContent = "Leave call"; btn.className = "end"; btn.disabled = false;
    } catch (e) {
      state.className = "state bad"; state.textContent = "Couldn't join: " + (e.message || e);
      btn.disabled = false;
    }
  };
})();
</script>
</body>
</html>
"""
