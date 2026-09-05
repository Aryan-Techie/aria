"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { TransportRail, type CallStatus } from "@/components/TransportRail";
import { SessionTimeline, type SessionEvent } from "@/components/SessionTimeline";
import { PatchBay, type LeftBrainView } from "@/components/PatchBay";
import { AlarmChannel } from "@/components/AlarmChannel";
import { DealFader, type DealRound } from "@/components/DealFader";
import { AgoraCallClient, type RtmCustomEvent, type TranscriptEvent } from "@/lib/agoraClient";
import { endCall, fetchSessionEvents, startCall } from "@/lib/api";

function elapsedTs(startedAt: number | null): string {
  if (startedAt === null) return "00:00";
  const s = Math.max(0, Math.floor((Date.now() - startedAt) / 1000));
  const m = Math.floor(s / 60)
    .toString()
    .padStart(2, "0");
  const r = (s % 60).toString().padStart(2, "0");
  return `${m}:${r}`;
}

let eventSeq = 0;
function nextId(): string {
  eventSeq += 1;
  return `evt-${eventSeq}`;
}

export default function Home() {
  const [status, setStatus] = useState<CallStatus>("idle");
  const [outcome, setOutcome] = useState<string | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [leftBrain, setLeftBrain] = useState<LeftBrainView | null>(null);
  const [escalationReason, setEscalationReason] = useState<string | null>(null);
  const [dealRounds, setDealRounds] = useState<DealRound[]>([]);
  const [pendingApprovalId, setPendingApprovalId] = useState<string | null>(null);
  const [approvedPct, setApprovedPct] = useState<number | null>(null);
  const [approvedBy, setApprovedBy] = useState<string | null>(null);
  const [toolStatus, setToolStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [micMuted, setMicMuted] = useState(false);

  const sessionIdRef = useRef<string | null>(null);
  const clientRef = useRef<AgoraCallClient | null>(null);
  const startedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (status !== "active" && status !== "connecting") return;
    const id = setInterval(() => {
      setElapsedSeconds(startedAtRef.current === null ? 0 : Math.floor((Date.now() - startedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(id);
  }, [status]);

  const pushEvent = useCallback((event: Omit<SessionEvent, "id" | "ts">) => {
    setEvents((prev) => [...prev, { ...event, id: nextId(), ts: elapsedTs(startedAtRef.current) }]);
  }, []);

  // TRANSCRIPT_UPDATED delivers the full current transcript on every call,
  // not one new turn (confirmed live) — reconcile by upserting each turn at
  // its stable id, updating in place if already shown (its text is still
  // streaming in) or appending if it's new, rather than blindly appending
  // every snapshot (which produced garbled, out-of-order fragments).
  const handleTranscriptSnapshot = useCallback((turns: TranscriptEvent[]) => {
    setEvents((prev) => {
      const next = [...prev];
      for (const turn of turns) {
        const eventId = `transcript-${turn.id}`;
        const existingIndex = next.findIndex((e) => e.id === eventId);
        const updated: SessionEvent = {
          id: eventId,
          ts: existingIndex >= 0 ? next[existingIndex].ts : elapsedTs(startedAtRef.current),
          kind: turn.role,
          label: turn.role,
          body: turn.text,
        };
        if (existingIndex >= 0) {
          next[existingIndex] = updated;
        } else {
          next.push(updated);
        }
      }
      return next;
    });
  }, []);

  const handleCustomEvent = useCallback(
    (event: RtmCustomEvent) => {
      switch (event.type) {
        case "qualification_updated":
          setLeftBrain(event.payload as LeftBrainView);
          break;
        case "tool_call_started": {
          const toolName = String(event.payload.tool_name ?? "a tool");
          setToolStatus(`Aria is checking ${toolName}…`);
          pushEvent({ kind: "tool", label: "tool", body: `${toolName} — dispatched` });
          break;
        }
        case "tool_call_finished":
          setToolStatus(null);
          break;
        case "objection_logged":
          pushEvent({
            kind: "tool",
            label: "tool",
            body: `objection logged — ${String(event.payload.topic ?? "unspecified")}`,
          });
          break;
        case "deal_offer_made": {
          const round = event.payload as unknown as DealRound;
          // Keyed on the round number rather than appended, because a poll
          // that overlaps a retry would otherwise print the same round twice.
          setDealRounds((prev) => {
            const next = prev.filter((r) => r.round !== round.round);
            return [...next, round].sort((a, b) => a.round - b.round);
          });
          pushEvent({
            kind: "tool",
            label: "deal",
            body:
              `round ${round.round} - gave ${round.granted_pct}% ` +
              `(${String(round.authorised_by).replace("_", " ")})` +
              (round.clamped ? ` - clamped: ${round.clamp_reason}` : ""),
          });
          break;
        }
        case "deal_approval_requested": {
          setPendingApprovalId(String(event.payload.escalation_id ?? ""));
          pushEvent({
            kind: "escalation",
            label: "approval",
            body: "deal desk at its ceiling - a human signature is needed, call still live",
          });
          break;
        }
        case "deal_approval_granted": {
          setPendingApprovalId(null);
          setApprovedPct(Number(event.payload.approved_pct));
          setApprovedBy(String(event.payload.approved_by ?? "a manager"));
          pushEvent({
            kind: "outcome",
            label: "approval",
            body: `${event.payload.approved_pct}% signed off by ${event.payload.approved_by}`,
          });
          break;
        }
        case "escalation_triggered": {
          const reason = String(event.payload.reason ?? event.payload.trigger_source ?? "handoff triggered");
          setEscalationReason(reason);
          pushEvent({ kind: "escalation", label: "escalation", body: reason });
          break;
        }
        case "call_outcome_set": {
          const outcomeValue = String(event.payload.outcome ?? "");
          setOutcome(outcomeValue);
          pushEvent({ kind: "outcome", label: "outcome", body: outcomeValue });
          break;
        }
      }
    },
    [pushEvent]
  );

  // Poll the backend for tool/qualification/escalation envelopes while the
  // call is live. Same events the backend publishes to RTM, over a transport
  // we control - see fetchSessionEvents in lib/api.ts for why.
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
          handleCustomEvent({
            type: envelope.type,
            payload: envelope.payload,
          } as RtmCustomEvent);
        }
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

  const handleStart = useCallback(async () => {
    setError(null);
    setStatus("connecting");
    try {
      // Defensive cleanup: an RTM client left connected from a prior attempt
      // (e.g. Start clicked again without a page reload after an error) logs
      // in twice under the same uid — Agora's own warning calls this a
      // "mutual kick" risk, confirmed live. Always close any stale client
      // before creating a new one.
      if (clientRef.current) {
        await clientRef.current.leave().catch(() => {});
        clientRef.current = null;
      }

      const session = await startCall();
      sessionIdRef.current = session.session_id;
      startedAtRef.current = Date.now();
      setElapsedSeconds(0);
      setEvents([]);
      setDealRounds([]);
      setPendingApprovalId(null);
      setApprovedPct(null);
      setApprovedBy(null);
      setMicMuted(false);

      const client = new AgoraCallClient();
      clientRef.current = client;

      await client.join(session, {
        onTranscriptSnapshot: handleTranscriptSnapshot,
        onCustomEvent: handleCustomEvent,
        onError: (e) => setError(String(e)),
      });

      setStatus("active");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus("idle");
    }
  }, [handleTranscriptSnapshot, handleCustomEvent]);

  const handleEnd = useCallback(async () => {
    setStatus("ending");
    try {
      await clientRef.current?.leave();
      // Drop the reference too: a retained client that has already been torn
      // down was what let a second RTM instance be created on the next call.
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
    }
  }, []);

  const handleToggleMute = useCallback(async () => {
    const next = !micMuted;
    try {
      await clientRef.current?.setMicMuted(next);
      setMicMuted(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [micMuted]);

  return (
    <div className="desk">
      <TransportRail
        status={status}
        outcome={outcome}
        elapsedSeconds={elapsedSeconds}
        micMuted={micMuted}
        onStart={handleStart}
        onEnd={handleEnd}
        onToggleMute={handleToggleMute}
      />

      <SessionTimeline events={events} toolStatus={toolStatus} error={error} />

      <aside className="rail rail-patchbay">
        <PatchBay leftBrain={leftBrain} />
        <DealFader
          rounds={dealRounds}
          pendingApprovalId={pendingApprovalId}
          approvedPct={approvedPct}
          approvedBy={approvedBy}
        />
        <AlarmChannel reason={escalationReason} />
      </aside>
    </div>
  );
}
