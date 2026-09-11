"use client";

import { useEffect, useRef, useState } from "react";
import { updateLeadManually, type LeadEdit, type LeftBrain } from "@/lib/api";
import { OUTCOME_LABEL, STAGES } from "@/lib/vocab";

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

export function LeadCard({
  lead,
  booked,
  escalated,
  sessionId,
}: {
  lead: LeftBrain | null;
  booked: boolean;
  escalated: boolean;
  /** Set once a call is live - lets the operator type in what the customer
   * hasn't said yet, same record either way (routes/call.py::update_lead_manually). */
  sessionId: string | null;
}) {
  const users = useTween(lead?.user_count);
  const [hot, setHot] = useState(false);
  useEffect(() => {
    if (lead?.user_count == null) return;
    setHot(true);
    const id = setTimeout(() => setHot(false), 1600);
    return () => clearTimeout(id);
  }, [lead?.user_count]);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<LeadEdit>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setDraft({
      name: lead?.name ?? "",
      title: lead?.title ?? "",
      company: lead?.company ?? "",
      industry: lead?.industry ?? "",
      email: lead?.email ?? "",
      phone: lead?.phone ?? "",
      user_count: lead?.user_count ?? undefined,
      budget_range: lead?.budget_range ?? "",
      timeline: lead?.timeline ?? "",
    });
    setError(null);
    setEditing(true);
  };

  const save = async () => {
    if (!sessionId) return;
    setSaving(true);
    setError(null);
    try {
      await updateLeadManually(sessionId, draft);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const stageIndex = STAGES.findIndex((s) => s.key === lead?.decision_stage);
  const notAFit = lead?.decision_stage === "not_a_fit";
  const pains = lead?.pain_points ?? [];

  return (
    <section className="card">
      <h3>
        Lead
        {booked && <span className="tone-good">Booked</span>}
        {!booked && escalated && <span className="tone-bad">Handed off</span>}
        {!editing && sessionId && !booked && !escalated && (
          <button className="ghost" onClick={startEdit} style={{ marginLeft: "auto" }}>
            Edit
          </button>
        )}
      </h3>
      {editing ? (
        <>
          <div className="edit-fields">
            {(
              [
                ["name", "Name"],
                ["title", "Role"],
                ["company", "Company"],
                ["industry", "Industry"],
                ["email", "Email"],
                ["phone", "Phone"],
                ["budget_range", "Budget"],
                ["timeline", "Timeline"],
              ] as const
            ).map(([key, label]) => (
              <div key={key}>
                <label htmlFor={`lead-${key}`}>{label}</label>
                <input
                  id={`lead-${key}`}
                  value={draft[key] ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
                />
              </div>
            ))}
            <div>
              <label htmlFor="lead-user_count">Devices</label>
              <input
                id="lead-user_count"
                type="number"
                min={1}
                value={draft.user_count ?? ""}
                onChange={(e) =>
                  setDraft((d) => ({
                    ...d,
                    user_count: e.target.value === "" ? undefined : Number(e.target.value),
                  }))
                }
              />
            </div>
          </div>
          <div className="edit-actions">
            <button className="primary small" onClick={save} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="ghost" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </button>
            {error && <span className="tone-bad">{error}</span>}
          </div>
        </>
      ) : (
        <>
          {lead?.name && (
        <div className="contact">
          {lead.name}
          {lead.title && <span className="role"> · {lead.title}</span>}
        </div>
      )}
      <div className={`company${lead?.company ? "" : " empty"}`}>
        {lead?.company ?? "Listening for a company…"}
        {lead?.industry && <span className="role"> · {lead.industry}</span>}
      </div>
      {(lead?.email || lead?.phone) && (
        <div className="reach">
          {lead.email && <span>{lead.email}</span>}
          {lead.phone && <span>{lead.phone}</span>}
        </div>
      )}
      {lead?.status && lead.status !== "new" && OUTCOME_LABEL[lead.status] && (
        <span className={`pill ${OUTCOME_LABEL[lead.status].tone}`} style={{ marginTop: 6 }}>
          {OUTCOME_LABEL[lead.status].text}
        </span>
      )}
        </>
      )}
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
