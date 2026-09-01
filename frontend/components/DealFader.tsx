"use client";

import { useState } from "react";
import { approveDiscount } from "@/lib/api";

/**
 * The negotiation as a channel fader with hard travel stops.
 *
 * This is the one panel where the console metaphor is not decoration. A
 * discount IS a fader: it only moves one way during a call, each move is
 * smaller than the last, and it has physical stops on its travel — 3% is as
 * far as Aria can push it alone, 10% is as far as the deal desk can, and 18%
 * is the end of the slot. What makes the panel worth watching is the stop
 * marks, because they are enforced in the backend rather than drawn here:
 * `clamped` means the desk asked for more travel and the engine refused.
 *
 * The approve control is layer 3 in one click. It writes the manager's figure
 * onto the live session, and Aria offers it on her very next turn.
 */

export interface DealRound {
  round: number;
  requested_pct: number | null;
  granted_pct: number;
  authorised_by: string;
  clamped: boolean;
  clamp_reason: string | null;
  asked_in_return: string[];
}

const ARIA_CEILING = 3;
const DESK_CEILING = 10;
const FLOOR = 18;

export function DealFader({
  rounds,
  pendingApprovalId,
  approvedPct,
  approvedBy,
}: {
  rounds: DealRound[];
  pendingApprovalId: string | null;
  approvedPct: number | null;
  approvedBy: string | null;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [amount, setAmount] = useState("13");

  const latest = rounds.length ? rounds[rounds.length - 1] : null;
  const granted = latest?.granted_pct ?? 0;
  const ceiling = approvedPct ?? DESK_CEILING;
  const travel = Math.min(100, (granted / FLOOR) * 100);

  const layer = approvedPct !== null ? "human" : (latest?.authorised_by ?? "aria");

  const onApprove = async () => {
    if (!pendingApprovalId) return;
    setSubmitting(true);
    setError(null);
    try {
      await approveDiscount(pendingApprovalId, Number(amount));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={`deal${pendingApprovalId ? " awaiting" : ""}`}>
      <div className="deal-head">
        <span className="panel-label">Deal desk</span>
        <span className={`deal-layer ${layer}`}>
          {rounds.length === 0 ? "IDLE" : `L${layerNumber(layer)} ${layer.replace("_", " ")}`}
        </span>
      </div>

      <div className="deal-fader" role="img" aria-label={`${granted}% granted, ceiling ${ceiling}%`}>
        <div className="deal-track">
          <div className="deal-travel" style={{ width: `${travel}%` }} />
          <i className="deal-stop aria" style={{ left: `${(ARIA_CEILING / FLOOR) * 100}%` }} />
          <i className="deal-stop desk" style={{ left: `${(DESK_CEILING / FLOOR) * 100}%` }} />
          <i className="deal-cap" style={{ left: `${(ceiling / FLOOR) * 100}%` }} />
        </div>
        <div className="deal-scale mono">
          <span>0%</span>
          <span>{ARIA_CEILING}% Aria</span>
          <span>{DESK_CEILING}% desk</span>
          <span>{FLOOR}% floor</span>
        </div>
      </div>

      <div className="deal-readout">
        <span className="mono deal-value">{granted.toFixed(1)}%</span>
        <span className="deal-caption">
          {rounds.length === 0
            ? "no discount requested yet"
            : `granted, round ${latest?.round} of ${rounds.length}`}
        </span>
      </div>

      {latest?.clamped && latest.clamp_reason && (
        <p className="deal-clamp">
          <b>Clamped.</b> {latest.clamp_reason}
        </p>
      )}

      {latest?.asked_in_return?.length ? (
        <p className="deal-trade">Asked in return: {latest.asked_in_return.join("; ")}</p>
      ) : null}

      {approvedPct !== null && (
        <p className="deal-approved">
          {approvedPct}% approved by {approvedBy ?? "a manager"} — live on the call.
        </p>
      )}

      {pendingApprovalId && approvedPct === null && (
        <div className="deal-approve">
          <p className="deal-ask">
            The desk is at its ceiling and has asked for a signature. The customer is still on
            the line.
          </p>
          <div className="deal-approve-row">
            <input
              className="deal-input mono"
              type="number"
              min={0}
              max={FLOOR}
              step={0.5}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              aria-label="Discount percent to approve"
            />
            <button className="switch live" onClick={onApprove} disabled={submitting}>
              {submitting ? "Signing…" : "Approve"}
            </button>
          </div>
          {error && <p className="deal-clamp">{error}</p>}
        </div>
      )}

      {rounds.length > 1 && (
        <ol className="deal-rounds mono">
          {rounds.map((round) => (
            <li key={round.round}>
              <span>R{round.round}</span>
              <span>{round.requested_pct !== null ? `asked ${round.requested_pct}%` : "asked —"}</span>
              <span>gave {round.granted_pct}%</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function layerNumber(layer: string): number {
  if (layer === "human") return 3;
  if (layer === "deal_desk") return 2;
  return 1;
}
