"use client";

export type CallStatus = "idle" | "connecting" | "active" | "ending" | "ended";

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0");
  const s = Math.floor(seconds % 60)
    .toString()
    .padStart(2, "0");
  return `${m}:${s}`;
}

function stateLabel(status: CallStatus): string {
  switch (status) {
    case "idle":
      return "STANDBY";
    case "connecting":
      return "CONNECTING";
    case "active":
      return "ON AIR";
    case "ending":
      return "ENDING";
    case "ended":
      return "PARKED";
  }
}

export function TransportRail({
  status,
  outcome,
  elapsedSeconds,
  onStart,
  onEnd,
}: {
  status: CallStatus;
  outcome: string | null;
  elapsedSeconds: number;
  onStart: () => void;
  onEnd: () => void;
}) {
  const lit = status === "connecting" || status === "active" || status === "ending";

  return (
    <aside className="rail rail-transport">
      <div className="brand">
        <span className="name">ARIA</span>
        <span className="unit">CALL CONSOLE</span>
      </div>

      <div className={`lamp-housing${lit ? " on" : ""}`}>
        <span className={`lamp${lit ? " on" : ""}`} aria-hidden="true" />
        <div className="lamp-text">
          <span className="lamp-caption">CHANNEL 1</span>
          <span className="lamp-state">{stateLabel(status)}</span>
        </div>
      </div>

      <div className="readout">
        <span className={`value mono${lit ? "" : " dim"}`}>{formatElapsed(elapsedSeconds)}</span>
        <div className="label">Elapsed</div>
      </div>

      {status === "ended" && (
        <div className="readout">
          <span className="value mono" style={{ fontSize: 15 }}>
            {outcome ?? "unresolved"}
          </span>
          <div className="label">Session outcome</div>
        </div>
      )}

      <div className="transport">
        {status === "idle" || status === "ended" ? (
          <button className="switch live" onClick={onStart}>
            Start call
          </button>
        ) : (
          <button
            className="switch"
            onClick={onEnd}
            disabled={status === "connecting" || status === "ending"}
          >
            End call
          </button>
        )}
      </div>
    </aside>
  );
}
