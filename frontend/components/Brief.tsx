"use client";

import { useState } from "react";
import type { CallSummary, LeftBrain, RightBrain, Sentiment } from "@/lib/api";
import type { DealRound } from "@/components/DealCard";
import { OUTCOME_LABEL, minutesHandled } from "@/lib/vocab";

function fmt(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

const URGENCY: Record<string, string> = { now: "now", today: "today", this_week: "this week", none: "when convenient" };
const MOOD_Y: Record<Sentiment, number> = { positive: 8, neutral: 30, skeptical: 48, frustrated: 60 };

/**
 * The end-of-call brief. The backend writes the real one (CallSummary) a
 * few seconds after End Call returns, because its top two lines cost a
 * model call. Until it lands, the facts are assembled here from the same
 * records it reads - lead, negotiation, objections - so the operator is
 * never looking at a spinner; only the headline waits.
 */
export function Brief({
  summary,
  outcome,
  durationSeconds,
  turnCount,
  tools,
  lead,
  brain,
  rounds,
  approvedPct,
  approvedBy,
  booked,
  escalated,
  leadId,
}: {
  summary: CallSummary | null;
  outcome: string | null;
  durationSeconds: number;
  turnCount: number;
  tools: string[];
  lead: LeftBrain | null;
  brain: RightBrain | null;
  rounds: DealRound[];
  approvedPct: number | null;
  approvedBy: string | null;
  booked: boolean;
  escalated: boolean;
  leadId: string | null;
}) {
  const [copied, setCopied] = useState(false);

  const resolvedOutcome = summary?.outcome ?? outcome ?? "follow_up";
  const label = OUTCOME_LABEL[resolvedOutcome] ?? { tone: "info" as const, text: resolvedOutcome.replace(/_/g, " ") };
  const latest = rounds.length ? rounds[rounds.length - 1] : null;
  const discount = approvedPct ?? latest?.granted_pct ?? 0;

  // Mirrors app/handoff/builder.py::_facts/_agreed/_owed/_risks, used only
  // until the backend's own lists arrive.
  const facts =
    summary?.facts ??
    [
      lead?.user_count != null && `${lead.user_count} devices`,
      lead?.budget_range && `Budget ${lead.budget_range}`,
      lead?.timeline && `Timeline ${lead.timeline}`,
      lead?.decision_stage && `Decision stage: ${lead.decision_stage.replace(/_/g, " ")}`,
      lead?.pain_points?.length && `Driving it: ${lead.pain_points.join(", ")}`,
    ].filter((x): x is string => Boolean(x));
  const agreed =
    summary?.agreed ??
    [
      latest && `${latest.granted_pct}% off list was offered and stands (round ${latest.round}, authorised by ${latest.authorised_by.replace("_", " ")})`,
      approvedPct != null && `${approvedPct}% approved by ${approvedBy ?? "a manager"} during the call`,
      booked && "A meeting was booked and the invite has gone out",
    ].filter((x): x is string => Boolean(x));
  const owed =
    summary?.owed ??
    Array.from(new Set(rounds.flatMap((r) => r.asked_in_return ?? []))).map((x) => `They were asked for: ${x}`);
  const risks =
    summary?.risks ??
    [
      ...(brain?.objections ?? []).filter((o) => !o.resolved).map((o) => `Unresolved ${o.topic} objection: ${o.raised_text}`),
      brain && (brain.sentiment === "skeptical" || brain.sentiment === "frustrated") && `They ended the call sounding ${brain.sentiment}`,
      brain?.competitor_mentions?.length && `Competing quotes in play: ${brain.competitor_mentions.join(", ")}`,
      escalated && "This call was escalated to a human",
    ].filter((x): x is string => Boolean(x));

  const history: Sentiment[] = brain?.sentiment_history?.length ? brain.sentiment_history : ["neutral"];
  const points = history.map((s, i) => [(i / Math.max(1, history.length - 1)) * 100, MOOD_Y[s]] as const);
  const path = points.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)} ${p[1]}`).join(" ");
  const mood = history[history.length - 1];

  const duration = summary?.duration_seconds || durationSeconds;
  const turns = summary?.turn_count || turnCount;
  const minutes = summary ? Math.round(summary.minutes_saved) : minutesHandled(tools, booked);
  const who = [summary?.company ?? lead?.company, summary?.contact].filter(Boolean).join(" · ") || "Unknown caller";

  const copy = async () => {
    const lines = [
      `${who} - ${label.text}`,
      "",
      summary?.headline ?? "",
      "",
      summary ? `Do next (${URGENCY[summary.urgency] ?? summary.urgency}): ${summary.recommended_action}` : "",
    ];
    for (const [title, items] of [
      ["What they need", facts],
      ["What was agreed", agreed],
      ["What we owe them", owed],
      ["Watch out for", risks],
    ] as const) {
      if (items.length) lines.push("", `${title}:`, ...items.map((i) => `- ${i}`));
    }
    lines.push("", `Call length ${Math.floor(duration / 60)}m ${duration % 60}s, ${turns} turns, handled end to end by Aria.`);
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard blocked - nothing to do but leave the button as it was
    }
  };

  return (
    <div className="brief">
      <div className="sum-top">
        <span className={`pill ${label.tone}`}>{label.text}</span>
        <span>{who}</span>
        <span>·</span>
        <span>
          {fmt(duration)}, {turns} turns
        </span>
      </div>

      {summary ? (
        <h1 className="headline">{summary.headline}</h1>
      ) : (
        <h1 className="headline pending" aria-live="polite">
          Writing the brief…
        </h1>
      )}

      {summary && summary.recommended_action && (
        <div className="action">
          <div>
            <div className="k">Do next · {URGENCY[summary.urgency] ?? summary.urgency}</div>
            <div className="v">{summary.recommended_action}</div>
          </div>
          {(summary.lead_id ?? leadId) && <span className="ref">Lead {summary.lead_id ?? leadId}</span>}
        </div>
      )}

      <div className="stats">
        <Stat k="On the call" v={fmt(duration)} />
        <Stat
          k="Rep time handled"
          v={minutes >= 60 ? `${Math.floor(minutes / 60)}h ${minutes % 60}` : String(minutes)}
          unit="min"
        />
        <Stat k="Discount in force" v={String(discount)} unit="%" />
        <Stat k="Tool calls" v={String(tools.length)} />
      </div>

      <div className="lists">
        <List title="What they need" items={facts} />
        <List title="What was agreed" items={agreed} cls="agreed" />
        <List title="What we owe them" items={owed} cls="owed" />
        <List title="Watch out for" items={risks} cls="risk" />
      </div>

      <div className="arc">
        <div className="k">
          <span>How it felt, start to finish</span>
          <span className={`m-${mood} strong`}>{mood}</span>
        </div>
        <svg viewBox="0 0 100 68" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="moodGradient" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#34c759" />
              <stop offset=".5" stopColor="#ff9f0a" />
              <stop offset="1" stopColor="#ff3b30" />
            </linearGradient>
          </defs>
          <path d={path} fill="none" stroke="url(#moodGradient)" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
          {points.map((p, i) => (
            <circle key={i} cx={p[0]} cy={p[1]} r="3" fill="var(--surface)" stroke="var(--ink-2)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
      </div>

      <div className="sum-foot">
        <span>Handled end to end by Aria.</span>
        <span>{summary ? "Also in the CRM, Slack and the rep's inbox." : "The rep's copy is on its way."}</span>
        <button className="ghost" onClick={copy} disabled={!summary}>
          {copied ? "Copied" : "Copy brief"}
        </button>
      </div>
    </div>
  );
}

function Stat({ k, v, unit }: { k: string; v: string; unit?: string }) {
  return (
    <div className="stat">
      <div className="k">{k}</div>
      <div className="v">
        {v}
        {unit && <small>{unit}</small>}
      </div>
    </div>
  );
}

function List({ title, items, cls }: { title: string; items: string[]; cls?: string }) {
  return (
    <div className={`list${cls ? ` ${cls}` : ""}`}>
      <h4>{title}</h4>
      <ul>
        {items.length === 0 && <li className="empty">Nothing captured</li>}
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
