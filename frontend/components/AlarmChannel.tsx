"use client";

export function AlarmChannel({ reason }: { reason: string | null }) {
  const tripped = reason !== null;

  return (
    <div className={`alarm${tripped ? " tripped" : ""}`} role="status">
      <div className="alarm-head">
        <span className="panel-label">Escalation channel</span>
        <span className="mono" style={{ fontSize: 11, color: tripped ? "var(--meter-red)" : "var(--text-faint)" }}>
          {tripped ? "TRIPPED" : "CLEAR"}
        </span>
      </div>
      <div className="alarm-zone" aria-hidden="true">
        {Array.from({ length: 12 }).map((_, i) => (
          <i key={i} />
        ))}
      </div>
      <p className="alarm-message">
        {reason ??
          "No handoff triggered. Guardrails watch every turn for a frustration streak, a repeated objection, or a low-confidence answer."}
      </p>
    </div>
  );
}
