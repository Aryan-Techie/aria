"use client";

import { useEffect, useRef } from "react";
import { minutesHandled, toolDone } from "@/lib/vocab";

export interface ToolRecord {
  id: string;
  tool: string;
  /** Seconds into the call when it was dispatched. */
  at: number;
  /** Round trip in ms; null while still running. */
  ms: number | null;
}

const SLOW_MS = 900;

function stamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/**
 * Every tool dispatched, in order, with its round trip. The per-call
 * latency budget is ~800 ms a turn, so anything past 900 ms is marked -
 * this is where a sluggish turn is diagnosed (docs/demo_script.md).
 * The running figure at the bottom is the same sum the brief reports.
 */
export function ActivityCard({ tools, booked }: { tools: ToolRecord[]; booked: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [tools.length]);

  const minutes = minutesHandled(
    tools.map((t) => t.tool),
    booked
  );

  return (
    <section className="card">
      <h3>
        Activity
        <span>{tools.length ? `${tools.length} tool call${tools.length === 1 ? "" : "s"}` : ""}</span>
      </h3>
      <div className="acts" ref={ref}>
        {tools.length === 0 && <p className="meta">Every lookup, write and booking lands here with its round trip.</p>}
        {tools.map((t) => (
          <div className="act" key={t.id}>
            <span className="ts">{stamp(t.at)}</span>
            <span className="n">
              {toolDone(t.tool)}
              <small>{t.tool}</small>
            </span>
            <span className={`ms${t.ms === null ? " busy" : t.ms > SLOW_MS ? " slow" : ""}`}>
              {t.ms === null ? "…" : `${t.ms} ms`}
            </span>
          </div>
        ))}
      </div>
      <div className="saved">
        <span>Rep time handled</span>
        <b>{minutes} min</b>
      </div>
    </section>
  );
}
