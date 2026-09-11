"use client";

import { Fragment, useState } from "react";
import { approveDiscount } from "@/lib/api";

export interface DealConcession {
  kind: string;
  detail: string;
}

export interface DealQuote {
  units: number;
  tier_name: string;
  effective_total: number;
  total_savings: number;
  term_months: number;
}

/** One `deal_offer_made` envelope, as the backend authorised it. */
export interface DealRound {
  round: number;
  requested_pct: number | null;
  granted_pct: number;
  authorised_by: string;
  clamped: boolean;
  clamp_reason: string | null;
  asked_in_return: string[];
  price_summary?: string;
  rationale?: string;
  quote?: DealQuote | null;
  concessions?: DealConcession[];
  commitments?: DealConcession[];
  requires_human?: boolean;
  declined?: boolean;
}

// Same approximate rate Aria uses to understand a rupee figure spoken on the
// call (app/tools/prompts.py) - display-only, the deal math stays in USD.
const USD_TO_INR = 83;

const moneyIn = (currency: "USD" | "INR") => (n: number) =>
  currency === "USD"
    ? n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 })
    : (n * USD_TO_INR).toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });

// app/deal/policy.py - the three numbers the engine enforces. Drawn as
// stops on the track so a clamped offer reads as hitting a limit.
const ARIA_CEILING = 3;
const DESK_CEILING = 10;
const FLOOR = 18;

/**
 * The negotiation as a track with hard stops. Discount only ever moves one
 * way on a call, and the interesting fact is not where it landed but which
 * layer said yes and whether a limit stopped it going further. The approve
 * control is layer 3: a person signs a figure while the customer is still
 * on the line, and Aria offers it on her next turn.
 */
export function DealCard({
  rounds,
  pendingApprovalId,
  requestedPct,
  approvedPct,
  approvedBy,
}: {
  rounds: DealRound[];
  pendingApprovalId: string | null;
  requestedPct: number | null;
  approvedPct: number | null;
  approvedBy: string | null;
}) {
  const [amount, setAmount] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currency, setCurrency] = useState<"USD" | "INR">("USD");
  const money = moneyIn(currency);

  const latest = rounds.length ? rounds[rounds.length - 1] : null;
  const granted = approvedPct ?? latest?.granted_pct ?? 0;
  const pct = (v: number) => `${Math.min(100, (v / FLOOR) * 100)}%`;
  const askDefault = requestedPct != null ? String(requestedPct) : String(DESK_CEILING + 2);

  const onApprove = async () => {
    if (!pendingApprovalId) return;
    setSubmitting(true);
    setError(null);
    try {
      await approveDiscount(pendingApprovalId, Number(amount || askDefault));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className={`card${pendingApprovalId && approvedPct === null ? " awaiting" : ""}`}>
      <h3>
        Deal
        <span>{rounds.length === 0 ? "no offer yet" : `${granted}% in force`}</span>
        <button
          type="button"
          className="ghost"
          onClick={() => setCurrency((c) => (c === "USD" ? "INR" : "USD"))}
          aria-label="Toggle currency display"
          style={{ marginLeft: "auto" }}
        >
          {currency}
        </button>
      </h3>
      <div className="ladder">
        <div className="track" role="img" aria-label={`${granted}% granted; stops at ${ARIA_CEILING}, ${DESK_CEILING} and ${FLOOR} percent`}>
          <div className="fill" style={{ width: pct(granted) }} />
          <div className={`stop${granted >= ARIA_CEILING ? " hit" : ""}`} style={{ left: pct(ARIA_CEILING) }}>
            <i />
            <b>
              {ARIA_CEILING}%<small>Aria</small>
            </b>
          </div>
          <div className={`stop${granted >= DESK_CEILING ? " hit" : ""}`} style={{ left: pct(DESK_CEILING) }}>
            <i />
            <b>
              {DESK_CEILING}%<small>Deal desk</small>
            </b>
          </div>
          <div className={`stop${granted >= FLOOR ? " hit" : ""}`} style={{ left: pct(FLOOR) }}>
            <i />
            <b>
              {FLOOR}%<small>Floor</small>
            </b>
          </div>
          {rounds.length > 0 && (
            <div className="knob" style={{ left: pct(granted) }}>
              <span>{granted}%</span>
            </div>
          )}
        </div>
      </div>

      {rounds.length > 0 && (
        <div className="rounds">
          {rounds.map((r) => {
            const hasDetail =
              r.price_summary || r.rationale || r.quote || r.concessions?.length || r.commitments?.length;
            return (
              <Fragment key={r.round}>
                <div className="rnd">
                  <span className="n">R{r.round}</span>
                  <span className="d">
                    {r.requested_pct != null ? `Asked ${r.requested_pct}%` : "Asked for a discount"} →{" "}
                    <b>{r.granted_pct}% off</b>
                    {r.asked_in_return?.length ? `, for ${r.asked_in_return.join("; ")}` : ""}
                  </span>
                  <span
                    className={`a${r.authorised_by === "human" ? " human" : r.clamped ? " clamp" : ""}`}
                    title={r.clamp_reason ?? undefined}
                  >
                    {r.clamped ? `held at ${r.granted_pct}` : r.authorised_by.replace("_", " ")}
                  </span>
                </div>
                {hasDetail && (
                  <details className="rnd-detail">
                    <summary>the full round</summary>
                    {r.price_summary && <p>{r.price_summary}</p>}
                    {r.quote && (
                      <p className="q-line">
                        {r.quote.tier_name} tier · {r.quote.units} units ·{" "}
                        <b>{money(r.quote.effective_total)}</b>
                        {r.quote.total_savings > 0 && ` · ${money(r.quote.total_savings)} saved`}
                        {r.quote.term_months > 0 && ` · ${r.quote.term_months}mo term`}
                      </p>
                    )}
                    {(r.concessions?.length || r.commitments?.length) && (
                      <div className="rnd-chips">
                        {r.concessions
                          ?.filter((c) => c.kind !== "discount")
                          .map((c, i) => (
                            <span className="chip" key={`c${i}`}>
                              {c.detail}
                            </span>
                          ))}
                        {r.commitments?.map((c, i) => (
                          <span className="chip warn" key={`m${i}`}>
                            {c.detail}
                          </span>
                        ))}
                      </div>
                    )}
                    {r.rationale && <p className="rationale">{r.rationale}</p>}
                  </details>
                )}
              </Fragment>
            );
          })}
        </div>
      )}

      {approvedPct !== null && (
        <div className="approval done">
          <div>
            <b>{approvedPct}% signed off</b>
            <span>by {approvedBy ?? "a manager"}, mid-call. Aria offers it on her next turn.</span>
          </div>
        </div>
      )}

      {pendingApprovalId && approvedPct === null && (
        <div className="approval">
          <div>
            <b>{requestedPct != null ? `${requestedPct}% needs a signature` : "A signature is needed"}</b>
            <span>The desk stops at {DESK_CEILING}%. The customer is still on the line.</span>
            {error && <span className="tone-bad">{error}</span>}
          </div>
          <div className="approve-row">
            <input
              className="pct"
              type="number"
              min={0}
              max={FLOOR}
              step={0.5}
              placeholder={askDefault}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              aria-label="Discount percent to approve"
            />
            <button className="primary small" onClick={onApprove} disabled={submitting}>
              {submitting ? "Signing…" : "Approve"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
