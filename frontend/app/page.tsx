"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Logo } from "@/components/Logo";
import { Orb, type Phase, type Speaker } from "@/components/Orb";
import { Transcript, type FeedItem } from "@/components/Transcript";
import { LeadCard } from "@/components/LeadCard";
import { SignalsCard } from "@/components/SignalsCard";
import { DealCard, type DealRound } from "@/components/DealCard";
import { HandoffCard, type Escalation } from "@/components/HandoffCard";
import { ActivityCard, type ToolRecord } from "@/components/ActivityCard";
import { Brief } from "@/components/Brief";
import { AgoraCallClient, type RtmCustomEvent } from "@/lib/agoraClient";
import {
  endCall,
  fetchSessionEvents,
  fetchSummary,
  startCall,
  type CallSummary,
  type LeftBrain,
  type RightBrain,
} from "@/lib/api";
import { toolBusy } from "@/lib/vocab";

type CallStatus = "idle" | "connecting" | "active" | "ending" | "ended";

function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

let seq = 0;
const nextId = (prefix: string) => `${prefix}-${++seq}`;

export default function Home() {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [tools, setTools] = useState<ToolRecord[]>([]);
  const [leftBrain, setLeftBrain] = useState<LeftBrain | null>(null);
  const [rightBrain, setRightBrain] = useState<RightBrain | null>(null);
  const [rounds, setRounds] = useState<DealRound[]>([]);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const [requestedPct, setRequestedPct] = useState<number | null>(null);
  const [approvedPct, setApprovedPct] = useState<number | null>(null);
  const [approvedBy, setApprovedBy] = useState<string | null>(null);
  const [escalation, setEscalation] = useState<Escalation | null>(null);
  // Name of the person on the channel after a warm transfer; null while
  // Aria still has the call.
  const [repOnCall, setRepOnCall] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [leadId, setLeadId] = useState<string | null>(null);
  const [booked, setBooked] = useState(false);
  const [summary, setSummary] = useState<CallSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [micMuted, setMicMuted] = useState(false);
  const [hold, setHold] = useState(false);
  const [agentState, setAgentState] = useState<string>("idle");
  const [youTalking, setYouTalking] = useState(false);
  const [tab, setTab] = useState<"brief" | "transcript">("brief");
  const [dark, setDark] = useState(false);

  const sessionIdRef = useRef<string | null>(null);
  const clientRef = useRef<AgoraCallClient | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const endedAtRef = useRef<number | null>(null);
  // tool_call_started and tool_call_finished carry no shared id, only the
  // tool name, so in-flight calls are matched first-in first-out per name.
  const inFlightRef = useRef<Map<string, { id: string; startedMs: number }[]>>(new Map());

  const phase: Phase = status === "idle" ? "idle" : status === "ended" ? "ended" : "live";

  /* ---------------- theme ---------------- */
  useEffect(() => {
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.dataset.theme = next ? "dark" : "light";
    try {
      localStorage.setItem("aria-theme", next ? "dark" : "light");
    } catch {
      // private mode - the choice just does not persist
    }
  };

  /* ---------------- clock ---------------- */
  useEffect(() => {
    if (status !== "active" && status !== "connecting") return;
    const id = setInterval(() => {
      setElapsed(startedAtRef.current === null ? 0 : Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 500);
    return () => clearInterval(id);
  }, [status]);

  /* ---------------- who is talking (for the orb and caption) ---------------- */
  useEffect(() => {
    if (status !== "active") {
      setYouTalking(false);
      return;
    }
    const id = setInterval(() => {
      const levels = clientRef.current?.getLevels();
      setYouTalking(!!levels && !micMuted && !hold && levels.local > 0.08);
    }, 120);
    return () => clearInterval(id);
  }, [status, micMuted, hold]);

  const toolInFlight = useMemo(() => tools.find((t) => t.ms === null) ?? null, [tools]);

  const speaker: Speaker =
    phase !== "live"
      ? "none"
      : agentState === "speaking"
        ? "aria"
        : toolInFlight || agentState === "thinking"
          ? "think"
          : youTalking
            ? "you"
            : "none";

  const getLevel = useCallback(() => {
    const levels = clientRef.current?.getLevels();
    if (!levels) return 0;
    return speaker === "aria" ? levels.remote : speaker === "you" ? levels.local : 0;
  }, [speaker]);

  /* ---------------- feed helpers ---------------- */
  const pushNote = useCallback((tone: "info" | "good" | "warn" | "bad", text: string) => {
    setFeed((prev) => [...prev, { kind: "note", id: nextId("note"), tone, text }]);
  }, []);

  // One side of one exchange. The backend publishes these from the LLM
  // route as the words flow (routes/llm.py::_publish_turn) - the user's
  // turn once, Aria's repeatedly as her reply grows, then once more marked
  // final. Upsert at the stable id so a growing reply updates in place.
  const upsertTurn = useCallback((id: string, role: "user" | "assistant", text: string, final: boolean) => {
    setFeed((prev) => {
      const item: FeedItem = { kind: "turn", id, role, text, final };
      const i = prev.findIndex((e) => e.id === id);
      if (i >= 0) {
        const next = [...prev];
        next[i] = item;
        return next;
      }
      return [...prev, item];
    });
  }, []);

  const handleCustomEvent = useCallback(
    (event: RtmCustomEvent) => {
      const p = event.payload;
      const eventMs = event.ts ? Date.parse(event.ts) : Date.now();
      switch (event.type) {
        case "transcript_turn": {
          const role = p.role === "user" ? "user" : "assistant";
          const text = String(p.text ?? "");
          if (!text) break;
          upsertTurn(`turn-${role}-${String(p.turn_id ?? eventMs)}`, role, text, Boolean(p.final));
          break;
        }
        case "tool_call_started": {
          const tool = String(p.tool_name ?? "tool");
          const id = nextId("tool");
          const list = inFlightRef.current.get(tool) ?? [];
          list.push({ id, startedMs: eventMs });
          inFlightRef.current.set(tool, list);
          const at = startedAtRef.current ? Math.max(0, (eventMs - startedAtRef.current) / 1000) : 0;
          setTools((prev) => [...prev, { id, tool, at, ms: null }]);
          setFeed((prev) => [...prev, { kind: "tool", id, tool, ms: null }]);
          break;
        }
        case "tool_call_finished": {
          const tool = String(p.tool_name ?? "tool");
          const list = inFlightRef.current.get(tool) ?? [];
          const started = list.shift();
          if (!started) break;
          const ms = Math.max(0, Math.round(eventMs - started.startedMs));
          const failed = String(p.result_summary ?? "").includes('"error"');
          setTools((prev) => prev.map((t) => (t.id === started.id ? { ...t, ms } : t)));
          setFeed((prev) =>
            prev.map((e) =>
              e.kind === "tool" && e.id === started.id
                ? { ...e, ms, tone: failed ? "bad" : tool === "calendar_book_meeting" ? "good" : undefined }
                : e
            )
          );
          break;
        }
        case "qualification_updated":
          setLeftBrain(p as LeftBrain);
          if (p.lead_id) setLeadId(String(p.lead_id));
          break;
        case "deal_offer_made": {
          const round = p as unknown as DealRound;
          // Keyed on the round number rather than appended: a poll that
          // overlaps a retry would otherwise print the same round twice.
          setRounds((prev) => [...prev.filter((r) => r.round !== round.round), round].sort((a, b) => a.round - b.round));
          break;
        }
        case "deal_approval_requested":
          setPendingApprovalId(String(p.escalation_id ?? ""));
          setRequestedPct(p.requested_pct == null ? null : Number(p.requested_pct));
          pushNote("warn", "The deal desk is at its ceiling. A signature is needed; the call is still live.");
          break;
        case "deal_approval_granted":
          setPendingApprovalId(null);
          setApprovedPct(Number(p.approved_pct));
          setApprovedBy(String(p.approved_by ?? "a manager"));
          pushNote("good", `${p.approved_pct}% signed off by ${p.approved_by ?? "a manager"}`);
          break;
        case "escalation_triggered": {
          const esc: Escalation = {
            trigger_source: String(p.trigger_source ?? "llm"),
            reason: p.reason ? String(p.reason) : null,
            escalation_id: p.escalation_id ? String(p.escalation_id) : null,
            inbox_position: p.inbox_position == null ? null : Number(p.inbox_position),
            handoff_url: p.handoff_url ? String(p.handoff_url) : null,
            rep_name: p.rep_name ? String(p.rep_name) : null,
          };
          setEscalation(esc);
          pushNote("bad", esc.reason ? `Handed to a person: ${esc.reason}` : "Handed to a person with a written brief");
          break;
        }
        case "call_outcome_set": {
          const value = String(p.outcome ?? "");
          setOutcome(value);
          if (value === "meeting_booked") {
            setBooked(true);
            pushNote("good", "Meeting booked. The invite is on its way.");
          }
          break;
        }
        case "rep_joined": {
          const name = String(p.rep_name ?? "A colleague");
          setRepOnCall(name);
          pushNote("good", `${name} is on the call. Aria is handing over.`);
          break;
        }
        case "aria_left":
          setAgentState("left");
          pushNote("info", "Aria has left the call.");
          break;
        case "objection_logged":
          // Reflected in right_brain on the next poll; nothing to print.
          break;
      }
    },
    [pushNote, upsertTurn]
  );

  /* ---------------- poll the backend for envelopes + brains ---------------- */
  useEffect(() => {
    if (status !== "active") return;
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;

    let cancelled = false;
    let cursor = 0;
    const poll = async () => {
      try {
        const data = await fetchSessionEvents(sessionId, cursor);
        if (cancelled) return;
        cursor = data.cursor;
        for (const envelope of data.events) {
          handleCustomEvent({ type: envelope.type, payload: envelope.payload, ts: envelope.ts, session_id: sessionId });
        }
        if (data.left_brain) setLeftBrain(data.left_brain);
        if (data.right_brain) setRightBrain(data.right_brain);
      } catch {
        // transient - the next tick retries
      }
    };
    void poll();
    const timer = setInterval(poll, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [status, handleCustomEvent]);

  /* ---------------- the brief, once the backend has written it ---------------- */
  useEffect(() => {
    if (status !== "ended" || summary) return;
    const sessionId = sessionIdRef.current;
    if (!sessionId) return;
    let cancelled = false;
    let tries = 0;
    const tick = async () => {
      tries += 1;
      try {
        const s = await fetchSummary(sessionId);
        if (cancelled) return;
        if (s) {
          setSummary(s);
          return;
        }
      } catch {
        // keep trying
      }
      if (!cancelled && tries < 20) setTimeout(tick, 1500);
    };
    void tick();
    return () => {
      cancelled = true;
    };
  }, [status, summary]);

  /* ---------------- lifecycle ---------------- */
  const handleStart = useCallback(async () => {
    setError(null);
    setStatus("connecting");
    setFeed([]);
    setTools([]);
    setLeftBrain(null);
    setRightBrain(null);
    setRounds([]);
    setPendingApprovalId(null);
    setRequestedPct(null);
    setApprovedPct(null);
    setApprovedBy(null);
    setEscalation(null);
    setRepOnCall(null);
    setOutcome(null);
    setLeadId(null);
    setBooked(false);
    setSummary(null);
    setMicMuted(false);
    setHold(false);
    setAgentState("idle");
    setTab("brief");
    setElapsed(0);
    inFlightRef.current = new Map();
    try {
      // An RTM client left connected from a prior attempt logs in twice
      // under the same uid - Agora's own warning calls this a "mutual kick"
      // risk, confirmed live. Always close any stale client first.
      if (clientRef.current) {
        await clientRef.current.leave().catch(() => {});
        clientRef.current = null;
      }
      const session = await startCall();
      sessionIdRef.current = session.session_id;
      startedAtRef.current = Date.now();
      endedAtRef.current = null;

      const client = new AgoraCallClient();
      clientRef.current = client;
      await client.join(session, {
        // Transcript comes over the polled event stream (transcript_turn),
        // not the toolkit's TRANSCRIPT_UPDATED - see handleCustomEvent.
        onCustomEvent: handleCustomEvent,
        onAgentStateChanged: (state) => setAgentState(state),
        onError: (e) => {
          const text = e instanceof Error ? e.message : String(e);
          setError(text);
          pushNote("bad", text);
        },
      });
      setStatus("active");
    } catch (e) {
      const text = e instanceof Error ? e.message : String(e);
      setError(text);
      setStatus("idle");
    }
  }, [handleCustomEvent, pushNote]);

  const handleEnd = useCallback(async () => {
    setStatus("ending");
    endedAtRef.current = Date.now();
    try {
      await clientRef.current?.leave();
      clientRef.current = null;
      if (sessionIdRef.current) {
        const result = await endCall(sessionIdRef.current);
        setOutcome(result.outcome);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      clientRef.current = null;
      setStatus("ended");
      setTab("brief");
    }
  }, []);

  const toggleMute = useCallback(async () => {
    const next = !micMuted;
    try {
      await clientRef.current?.setMicMuted(next);
      setMicMuted(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [micMuted]);

  const toggleHold = useCallback(async () => {
    const next = !hold;
    try {
      await clientRef.current?.setHold(next);
      setHold(next);
      // Coming off hold restores the mic; going on hold implies mute.
      if (next) setMicMuted(true);
      else {
        await clientRef.current?.setMicMuted(false);
        setMicMuted(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [hold]);

  /* ---------------- captions ---------------- */
  const durationSeconds =
    startedAtRef.current === null
      ? 0
      : Math.floor(((endedAtRef.current ?? Date.now()) - startedAtRef.current) / 1000);

  let caption: React.ReactNode;
  if (status === "idle") caption = error ? <span className="tone-bad">{error}</span> : "Ready when you are";
  else if (status === "connecting") caption = <em>Connecting…</em>;
  else if (status === "ending") caption = <em>Wrapping up…</em>;
  else if (status === "ended")
    caption = (
      <>
        Call ended · {fmt(durationSeconds)}
        <br />
        <em>{summary ? "Brief sent, CRM note written." : "Writing the brief for the rep…"}</em>
      </>
    );
  else if (hold) caption = <>On hold <em>· Aria can’t hear you and you can’t hear her</em></>;
  else if (repOnCall && agentState === "left") caption = <>{repOnCall} has the call <em>· Aria has left</em></>;
  else if (repOnCall) caption = <>{repOnCall} is on the line <em>· Aria is handing over</em></>;
  else if (toolInFlight) caption = `${toolBusy(toolInFlight.tool)}…`;
  else if (agentState === "speaking") caption = "Aria is speaking";
  else if (agentState === "thinking") caption = <em>Thinking</em>;
  else if (micMuted) caption = <em>Muted</em>;
  else caption = youTalking ? "Listening" : <em>Listening</em>;

  const turnCount = feed.filter((e) => e.kind === "turn").length;
  const statusLabel =
    status === "idle" ? "Standby" : status === "connecting" ? "Connecting" : status === "ended" ? "Ended" : "Live";

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <Logo size={24} />
          <span>Aria</span>
          <span className="sub">Console</span>
        </div>
        <div className={`status ${phase}${status === "connecting" ? " connecting" : ""}`} role="status">
          <span className="dot" />
          <span>{statusLabel}</span>
          {status !== "idle" && <span className="time">{fmt(status === "ended" ? durationSeconds : elapsed)}</span>}
        </div>
        <div className="actions">
          <button className="ghost" onClick={toggleTheme}>
            {dark ? "Light" : "Dark"}
          </button>
        </div>
      </header>

      <main className="stage" data-phase={phase}>
        <section className="left">
          <div className={`voice${hold ? " hold" : ""}`}>
            <Orb phase={phase} speaker={speaker} hold={hold} getLevel={getLevel} />
            <div className="caption">{caption}</div>
            <div className="controls">
              {(status === "idle" || status === "ended") && (
                <button className="primary" onClick={handleStart}>
                  {status === "ended" ? "New call" : "Start call"}
                </button>
              )}
              {(status === "connecting" || status === "active" || status === "ending") && (
                <>
                  <button
                    className={`round${micMuted ? " on" : ""}`}
                    onClick={toggleMute}
                    disabled={status !== "active" || hold}
                    title={micMuted ? "Unmute" : "Mute"}
                    aria-pressed={micMuted}
                  >
                    <MicIcon muted={micMuted} />
                  </button>
                  <button
                    className={`round${hold ? " on" : ""}`}
                    onClick={toggleHold}
                    disabled={status !== "active"}
                    title={hold ? "Resume" : "Hold"}
                    aria-pressed={hold}
                  >
                    {hold ? <PlayIcon /> : <PauseIcon />}
                  </button>
                  <button className="round end" onClick={handleEnd} disabled={status !== "active"} title="End call">
                    <EndIcon />
                  </button>
                </>
              )}
            </div>
          </div>

          {status === "ended" && (
            <div className="tabs" role="tablist">
              <button role="tab" aria-selected={tab === "brief"} className={tab === "brief" ? "on" : ""} onClick={() => setTab("brief")}>
                Brief
              </button>
              <button
                role="tab"
                aria-selected={tab === "transcript"}
                className={tab === "transcript" ? "on" : ""}
                onClick={() => setTab("transcript")}
              >
                Transcript
              </button>
            </div>
          )}

          {status !== "idle" && (
            <Transcript
              items={feed}
              hidden={status === "ended" && tab !== "transcript"}
              emptyText={status === "connecting" ? "Joining the channel…" : "Say hello. Every turn and every tool call prints here as it happens."}
            />
          )}

          {status === "ended" && tab === "brief" && (
            <Brief
              summary={summary}
              outcome={outcome}
              durationSeconds={durationSeconds}
              turnCount={turnCount}
              tools={tools.map((t) => t.tool)}
              lead={leftBrain}
              brain={rightBrain}
              rounds={rounds}
              approvedPct={approvedPct}
              approvedBy={approvedBy}
              booked={booked}
              escalated={escalation !== null}
              leadId={leadId}
            />
          )}
        </section>

        <aside className="sheet">
          <LeadCard lead={leftBrain} booked={booked} escalated={escalation !== null} />
          <SignalsCard brain={rightBrain} />
          <DealCard
            rounds={rounds}
            pendingApprovalId={pendingApprovalId}
            requestedPct={requestedPct}
            approvedPct={approvedPct}
            approvedBy={approvedBy}
          />
          <HandoffCard brain={rightBrain} escalation={escalation} repOnCall={repOnCall} />
          <ActivityCard tools={tools} booked={booked} />
        </aside>
      </main>
    </div>
  );
}

const icon = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

function MicIcon({ muted }: { muted: boolean }) {
  return (
    <svg viewBox="0 0 24 24" {...icon}>
      <rect x="9" y="3" width="6" height="12" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      {muted && <path d="M4 4l16 16" />}
    </svg>
  );
}
function PauseIcon() {
  return (
    <svg viewBox="0 0 24 24" {...icon}>
      <path d="M8 5v14M16 5v14" strokeWidth="2.4" />
    </svg>
  );
}
function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M7 4.5v15l12-7.5z" />
    </svg>
  );
}
function EndIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor">
      <path d="M3.6 13.9c-.9-.9-.9-2.2-.1-3.1C6 8.3 9 7 12 7s6 1.3 8.5 3.8c.8.9.8 2.2-.1 3.1l-1.6 1.6c-.7.7-1.8.8-2.6.2l-2-1.5c-.6-.5-.9-1.2-.8-1.9l.2-1.2c-1.1-.4-2.3-.4-3.4 0l.2 1.2c.1.7-.2 1.4-.8 1.9l-2 1.5c-.8.6-1.9.5-2.6-.2z" />
    </svg>
  );
}
