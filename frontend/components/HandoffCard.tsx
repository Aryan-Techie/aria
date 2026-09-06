"use client";

import { useState } from "react";
import type { RightBrain } from "@/lib/api";
import { TRIGGER_LABEL } from "@/lib/vocab";

export interface Escalation {
  trigger_source: string;
  reason: string | null;
  escalation_id: string | null;
  inbox_position: number | null;
  /** Where a person opens the call - backend routes/rep.py. */
  handoff_url: string | null;
  rep_name: string | null;
}

// app/escalation/triggers.py - the same thresholds the backend checks
// every turn, so the console shows how close each guardrail is to firing
// rather than only that one did.
const FRUSTRATION_STREAK_LEN = 2;
const OBJECTION_MAX_ATTEMPTS = 3;

/**
 * When a person gets pulled in. Three deterministic guardrails plus Aria's
 * own judgment; each is shown with how far along it is, and the whole card
 * turns red the moment one trips. This is the old alarm channel, with the
 * meter replaced by the actual numbers behind it.
 */
export function HandoffCard({
  brain,
  escalation,
  repOnCall,
}: {
  brain: RightBrain | null;
  escalation: Escalation | null;
  /** Set once the rep's mic is live on the channel (rep_joined event). */
  repOnCall: string | null;
}) {
  const history = brain?.sentiment_history ?? [];
  const recent = history.slice(-FRUSTRATION_STREAK_LEN);
  const streak = recent.filter((s) => s === "skeptical" || s === "frustrated").length;
  const worstObjection = (brain?.objections ?? [])
    .filter((o) => !o.resolved)
    .reduce((max, o) => Math.max(max, o.attempts), 0);

  const tripped = escalation !== null;

  return (
    <section className={`card${tripped ? " tripped" : ""}`} role="status">
      <h3>
        Handoff
        <span className={repOnCall ? "tone-good" : tripped ? "tone-bad" : ""}>
          {repOnCall ? `${repOnCall} has it` : tripped ? "Waiting for a person" : "Aria has it"}
        </span>
      </h3>

      {tripped ? (
        <div className="handoff">
          <b>{TRIGGER_LABEL[escalation.trigger_source] ?? escalation.trigger_source.replace(/_/g, " ")}</b>
          {escalation.reason && <p>{escalation.reason}</p>}
          <p className="meta">
            Brief written.
            {escalation.inbox_position != null && ` Number ${escalation.inbox_position} in the inbox.`}
          </p>
          {escalation.handoff_url && !repOnCall && <JoinLink url={escalation.handoff_url} name={escalation.rep_name ?? "the rep"} />}
          {repOnCall && <p className="meta">{repOnCall} joined the call. Aria has handed over and left.</p>}
        </div>
      ) : (
        <div className="guards">
          <Guard
            label="Frustration streak"
            hint={`${FRUSTRATION_STREAK_LEN} turns in a row`}
            value={streak}
            max={FRUSTRATION_STREAK_LEN}
          />
          <Guard
            label="Objection keeps returning"
            hint={`${OBJECTION_MAX_ATTEMPTS} attempts unresolved`}
            value={worstObjection}
            max={OBJECTION_MAX_ATTEMPTS}
          />
          <Guard label="Low-confidence answer" hint="knowledge base miss" value={0} max={1} />
          <p className="meta">Aria can also ask for a person herself. Any of these ends the call with a written brief.</p>
        </div>
      )}
    </section>
  );
}

/** The one thing the operator does at a handoff: get the link to the
 * person who is taking the call. Copied, not emailed - for the demo it goes
 * over whatever chat is already open. */
function JoinLink({ url, name }: { url: string; name: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Copy this link", url);
    }
  };
  return (
    <div className="joinlink">
      <button className="primary small" onClick={copy}>
        {copied ? "Copied" : `Copy join link for ${name}`}
      </button>
      <a href={url} target="_blank" rel="noreferrer">
        {url.replace(/^https?:\/\//, "")}
      </a>
    </div>
  );
}

function Guard({ label, hint, value, max }: { label: string; hint: string; value: number; max: number }) {
  const level = value >= max ? "bad" : value > 0 ? "warn" : "ok";
  return (
    <div className={`guard ${level}`}>
      <div className="g-text">
        <span className="g-label">{label}</span>
        <span className="g-hint">{hint}</span>
      </div>
      <div className="g-dots" aria-label={`${value} of ${max}`}>
        {Array.from({ length: max }).map((_, i) => (
          <i key={i} className={i < value ? "on" : ""} />
        ))}
      </div>
    </div>
  );
}
