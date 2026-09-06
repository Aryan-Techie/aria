"use client";

import type { RightBrain } from "@/lib/api";
import { CheckIcon } from "@/lib/vocab";

/**
 * The softer half of the record: how the call feels, who else is in the
 * running, and what the customer pushed back on. Read straight off
 * right_brain on every poll - none of this is published as an event.
 */
export function SignalsCard({ brain }: { brain: RightBrain | null }) {
  const sentiment = brain?.sentiment ?? "neutral";
  const history = brain?.sentiment_history?.length ? brain.sentiment_history : ["neutral"];
  const competitors = brain?.competitor_mentions ?? [];
  const objections = brain?.objections ?? [];

  return (
    <section className="card">
      <h3>Signals</h3>
      <div className="mood">
        <div className={`word m-${sentiment}`}>{sentiment}</div>
        <div className="trail" aria-label={`Sentiment over the last ${history.length} readings`}>
          {history.slice(-14).map((s, i) => (
            <i className={`m-${s}`} key={i} />
          ))}
        </div>
      </div>
      {competitors.length > 0 && (
        <div className="competitors">
          <span className="k">Against</span>
          {competitors.map((c) => (
            <span className="chip warn" key={c}>
              {c}
            </span>
          ))}
        </div>
      )}
      {objections.length > 0 && (
        <div className="objs">
          {objections.map((o, i) => (
            <div className={`obj${o.resolved ? " ok" : ""}`} key={i}>
              <span className="t">{o.topic}</span>
              <span className="q">
                <i>“{o.raised_text}”</i>
                {!o.resolved && o.attempts > 1 && <small> · raised {o.attempts}×</small>}
              </span>
              <span className="s">
                <CheckIcon />
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
