"use client";

import { useEffect, useRef, useState } from "react";
import type { LeftBrain } from "@/lib/api";
import { STAGES } from "@/lib/vocab";

/** Counts a number up or down to its new value, so "10 devices" becoming
 * "50 devices" is seen to change rather than found to have changed. */
function useTween(value: number | null | undefined): number | null {
  const [shown, setShown] = useState<number | null>(value ?? null);
  const from = useRef<number>(value ?? 0);
  useEffect(() => {
    if (value == null) {
      setShown(null);
      return;
    }
    const start = from.current;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || start === value) {
      from.current = value;
      setShown(value);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / 700);
      const e = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(start + (value - start) * e));
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return shown;
}

export function LeadCard({ lead, booked, escalated }: { lead: LeftBrain | null; booked: boolean; escalated: boolean }) {
  const users = useTween(lead?.user_count);
  const [hot, setHot] = useState(false);
  useEffect(() => {
    if (lead?.user_count == null) return;
    setHot(true);
    const id = setTimeout(() => setHot(false), 1600);
    return () => clearTimeout(id);
  }, [lead?.user_count]);

  const stageIndex = STAGES.findIndex((s) => s.key === lead?.decision_stage);
  const notAFit = lead?.decision_stage === "not_a_fit";
  const pains = lead?.pain_points ?? [];

  return (
    <section className="card">
      <h3>
        Lead
        {booked && <span className="tone-good">Booked</span>}
        {!booked && escalated && <span className="tone-bad">Handed off</span>}
      </h3>
      <div className={`company${lead?.company ? "" : " empty"}`}>{lead?.company ?? "Listening for a company…"}</div>
      <div className="fields">
        <div className="field">
          <div className="k">Devices</div>
          <div className={`v big${users == null ? " empty" : ""}${hot ? " hot" : ""}`}>{users ?? "—"}</div>
        </div>
        <div className="field">
          <div className="k">Budget</div>
          <div className={`v${lead?.budget_range ? "" : " empty"}`}>{lead?.budget_range ?? "—"}</div>
        </div>
        <div className="field">
          <div className="k">Timeline</div>
          <div className={`v${lead?.timeline ? "" : " empty"}`}>{lead?.timeline ?? "—"}</div>
        </div>
      </div>
      {pains.length > 0 && (
        <div className="pains">
          {pains.map((p) => (
            <span className="chip" key={p}>
              {p}
            </span>
          ))}
        </div>
      )}
      <div className="stepper">
        {STAGES.map((s, i) => (
          <div
            className={`step${i < stageIndex || booked ? " done" : ""}${i === stageIndex && !booked ? " now" : ""}`}
            key={s.key}
          >
            <i />
            {s.label}
            <span className="bar" />
          </div>
        ))}
        <div className={`step last${booked ? " now" : ""}${notAFit ? " off" : ""}`}>
          <i />
          {notAFit ? "Not a fit" : "Booked"}
        </div>
      </div>
    </section>
  );
}
