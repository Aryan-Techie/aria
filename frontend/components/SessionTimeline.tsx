"use client";

import { useEffect, useRef } from "react";

export type SessionEventKind = "user" | "assistant" | "tool" | "escalation" | "outcome";

export interface SessionEvent {
  id: string;
  ts: string;
  kind: SessionEventKind;
  label: string;
  body: string;
}

const KIND_LABEL: Record<SessionEventKind, string> = {
  user: "Customer",
  assistant: "Aria",
  tool: "Tool",
  escalation: "Alarm",
  outcome: "Outcome",
};

export function SessionTimeline({
  events,
  toolStatus,
  error,
}: {
  events: SessionEvent[];
  toolStatus: string | null;
  error?: string | null;
}) {
  const trackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const track = trackRef.current;
    if (track) track.scrollTop = track.scrollHeight;
  }, [events.length]);

  return (
    <main className="timeline-wrap">
      <div className="timeline-head">
        <span className="timeline-title">Session timeline</span>
        {toolStatus && <span className="tool-status">{toolStatus}</span>}
      </div>

      {error && <div className="error-strip">{error}</div>}

      <div className="track" ref={trackRef}>
        {events.length === 0 && (
          <p className="track-empty">
            Nothing on the tape yet. Start the call — every turn Aria takes and every tool it
            fires will print here as it happens.
          </p>
        )}
        {events.map((event) => (
          <div className={`event ${event.kind}`} key={event.id}>
            <span className="event-ts mono">{event.ts}</span>
            <span className={`event-kind ${event.kind}`}>{KIND_LABEL[event.kind]}</span>
            <span className="event-body">{event.body}</span>
          </div>
        ))}
      </div>
    </main>
  );
}
