"use client";

import { useEffect, useRef } from "react";
import { SpinIcon, ToolIcon, toolBusy, toolDone } from "@/lib/vocab";

/**
 * One row of the feed. Turns are upserted by id as the transcript snapshot
 * streams (see page.tsx); tool rows are created on tool_call_started and
 * finished in place; notes are the one-line system moments - an escalation,
 * an approval, an outcome, an error - that belong in the flow of the call
 * rather than in a side panel.
 *
 * Layout: two columns. The narrow left column carries tool calls and notes
 * (the machinery), the wide right column carries what was actually said -
 * the operator's turns and Aria's, streaming in real time. Each column
 * follows its own bottom.
 */
export type FeedItem =
  | { kind: "turn"; id: string; role: "user" | "assistant"; text: string; final: boolean }
  | { kind: "tool"; id: string; tool: string; ms: number | null; tone?: "good" | "warn" | "bad" }
  | { kind: "note"; id: string; tone: "info" | "good" | "warn" | "bad"; text: string };

function useFollowBottom<T>(items: T[]) {
  const ref = useRef<HTMLDivElement>(null);
  const lastCount = useRef(0);
  // Follow the bottom as new rows land, but do not yank the operator back
  // down while they are reading something earlier.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (nearBottom || items.length !== lastCount.current) {
      el.scrollTop = el.scrollHeight;
    }
    lastCount.current = items.length;
  }, [items]);
  return ref;
}

export function Transcript({
  items,
  hidden,
  emptyText,
}: {
  items: FeedItem[];
  hidden?: boolean;
  emptyText: string;
}) {
  const turns = items.filter((i) => i.kind === "turn");
  const events = items.filter((i) => i.kind !== "turn");
  const turnsRef = useFollowBottom(turns);
  const eventsRef = useFollowBottom(events);

  return (
    <div className="feed" hidden={hidden}>
      <div className="feed-events" ref={eventsRef}>
        {events.map((item) => {
          if (item.kind === "tool") {
            const busy = item.ms === null;
            return (
              <div className="evt" key={item.id}>
                <span className={`pill${busy ? " busy" : ""}${item.tone ? ` ${item.tone}` : ""}`}>
                  {busy ? <SpinIcon /> : <ToolIcon tool={item.tool} />}
                  <span>{busy ? `${toolBusy(item.tool)}…` : toolDone(item.tool)}</span>
                  {!busy && <span className="ms">{item.ms} ms</span>}
                </span>
              </div>
            );
          }
          if (item.kind === "note") {
            return (
              <div className="evt" key={item.id}>
                <span className={`note ${item.tone}`}>{item.text}</span>
              </div>
            );
          }
          return null;
        })}
      </div>
      <div className="feed-turns" ref={turnsRef}>
        {turns.length === 0 && <p className="feed-empty">{emptyText}</p>}
        {turns.map((item) => {
          if (item.kind !== "turn") return null;
          return (
            <div className={`turn ${item.role === "user" ? "you" : "aria"}${item.final ? "" : " live"}`} key={item.id}>
              <div className="who">
                <i />
                {item.role === "user" ? "You" : "Aria"}
              </div>
              <div className="text">{item.text}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
