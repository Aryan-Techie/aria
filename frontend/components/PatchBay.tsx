"use client";

export interface LeftBrainView {
  company?: string | null;
  user_count?: number | null;
  budget_range?: string | null;
  timeline?: string | null;
  pain_points?: string[];
  decision_stage?: string | null;
}

export function PatchBay({ leftBrain }: { leftBrain: LeftBrainView | null }) {
  const painPoints = leftBrain?.pain_points?.length ? leftBrain.pain_points.join(", ") : null;

  return (
    <div>
      <span className="panel-label">Qualification patch bay</span>
      <div className="patch-grid" style={{ marginTop: 10 }}>
        <Cell label="Company" value={leftBrain?.company} />
        <Cell label="Users" value={leftBrain?.user_count} />
        <Cell label="Budget" value={leftBrain?.budget_range} />
        <Cell label="Timeline" value={leftBrain?.timeline} />
        <Cell label="Stage" value={leftBrain?.decision_stage} wide />
        <Cell label="Pain points" value={painPoints} wide />
      </div>
    </div>
  );
}

function Cell({
  label,
  value,
  wide,
}: {
  label: string;
  value: string | number | null | undefined;
  wide?: boolean;
}) {
  return (
    <div className={`patch-cell${wide ? " wide" : ""}`}>
      <div className="label">{label}</div>
      <div className={`value${value === null || value === undefined ? " empty" : ""}`}>
        {value ?? "unpatched"}
      </div>
    </div>
  );
}
