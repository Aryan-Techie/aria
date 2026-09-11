/**
 * The words and pictures the console uses for things the backend names in
 * snake_case. Kept in one place so the transcript pill, the activity list
 * and the brief all call a tool the same thing.
 */

/** What a tool did, past tense - shown once it has returned. */
export const TOOL_DONE: Record<string, string> = {
  search_pricing_rag: "Looked up pricing",
  check_inventory: "Checked live stock",
  crm_upsert_lead: "Updated the lead",
  crm_qualify_lead: "Qualified the lead",
  log_objection: "Logged an objection",
  update_sentiment: "Read the room",
  negotiate_deal: "Went to the deal desk",
  calendar_check_availability: "Checked the calendar",
  calendar_book_meeting: "Booked the meeting",
  ask_solutions_engineer: "Asked a solutions engineer",
  escalate_to_human: "Escalated to a human",
};

/** What a tool is doing, present tense - shown while it is in flight. */
export const TOOL_BUSY: Record<string, string> = {
  search_pricing_rag: "Pulling those numbers up",
  check_inventory: "Checking what is in stock",
  crm_upsert_lead: "Writing to the CRM",
  crm_qualify_lead: "Qualifying the lead",
  log_objection: "Noting that",
  update_sentiment: "Reading the room",
  negotiate_deal: "Checking with the deal desk",
  calendar_check_availability: "Looking at the calendar",
  calendar_book_meeting: "Booking it",
  ask_solutions_engineer: "Asking a solutions engineer",
  escalate_to_human: "Bringing a person in",
};

export function toolDone(name: string): string {
  return TOOL_DONE[name] ?? name.replace(/_/g, " ");
}
export function toolBusy(name: string): string {
  return TOOL_BUSY[name] ?? `Running ${name.replace(/_/g, " ")}`;
}

/** app/metrics/savings.py - the same baselines and once-per-call set, so
 * the running figure on the console matches the one in the brief. */
export const BASELINE_MINUTES: Record<string, number> = {
  crm_upsert_lead: 3,
  crm_qualify_lead: 1,
  search_pricing_rag: 2,
  check_inventory: 3,
  ask_solutions_engineer: 12,
  negotiate_deal: 20,
  calendar_check_availability: 4,
  calendar_book_meeting: 11,
  log_objection: 0.5,
  update_sentiment: 0,
  escalate_to_human: 0,
};
export const ONCE_PER_CALL = new Set(["crm_upsert_lead", "crm_qualify_lead", "calendar_book_meeting"]);
export const CONFIRMATION_MINUTES = 4;

export function minutesHandled(tools: string[], booked: boolean): number {
  const seen = new Set<string>();
  let minutes = 0;
  for (const tool of tools) {
    if (ONCE_PER_CALL.has(tool)) {
      if (seen.has(tool)) continue;
      seen.add(tool);
    }
    minutes += BASELINE_MINUTES[tool] ?? 0;
  }
  if (booked) minutes += CONFIRMATION_MINUTES;
  return Math.round(minutes);
}

export const OUTCOME_LABEL: Record<string, { tone: "good" | "info" | "warn" | "bad"; text: string }> = {
  meeting_booked: { tone: "good", text: "Meeting booked" },
  qualified: { tone: "info", text: "Qualified" },
  disqualified: { tone: "warn", text: "Disqualified" },
  follow_up: { tone: "warn", text: "Follow up" },
  escalated: { tone: "bad", text: "Escalated" },
};

export const TRIGGER_LABEL: Record<string, string> = {
  llm: "Aria asked for a person",
  frustration_streak: "Two turns in a row sounded frustrated",
  objection_retry: "An objection came back a third time",
  low_confidence: "She could not find a confident answer",
};

/** app/crm/models.py::DecisionStage, in buying order. `not_a_fit` is a
 * dead end rather than a step, so the stepper shows it separately. */
export const STAGES: { key: string; label: string }[] = [
  { key: "discovery", label: "Discovery" },
  { key: "evaluating", label: "Evaluating" },
  { key: "ready_to_buy", label: "Ready to buy" },
];

const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const };

export function ToolIcon({ tool }: { tool: string }) {
  if (tool.startsWith("search")) {
    return (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" />
      </svg>
    );
  }
  if (tool === "check_inventory") {
    return (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M3 8.5 12 4l9 4.5v7L12 20l-9-4.5z" />
        <path d="M3 8.5 12 13l9-4.5M12 13v7" />
      </svg>
    );
  }
  if (tool.startsWith("crm")) {
    return (
      <svg viewBox="0 0 24 24" {...stroke}>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
      </svg>
    );
  }
  if (tool.startsWith("calendar")) {
    return (
      <svg viewBox="0 0 24 24" {...stroke}>
        <rect x="3" y="5" width="18" height="16" rx="3" />
        <path d="M3 10h18M8 3v4M16 3v4" />
      </svg>
    );
  }
  if (tool === "negotiate_deal") {
    return (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 3v18M17 7.5c0-1.7-2.2-2.5-5-2.5S7 5.8 7 7.5 9.2 10 12 10s5 .8 5 2.5-2.2 2.5-5 2.5-5-.8-5-2.5" />
      </svg>
    );
  }
  if (tool === "escalate_to_human") {
    return (
      <svg viewBox="0 0 24 24" {...stroke}>
        <path d="M12 4v9M12 17v.5" />
        <circle cx="12" cy="12" r="9" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" {...stroke}>
      <path d="M5 21V4M5 4h12l-2 4 2 4H5" />
    </svg>
  );
}

export function SpinIcon() {
  return (
    <svg viewBox="0 0 24 24" {...stroke}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}

export function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <path d="m5 12 5 5L20 7" />
    </svg>
  );
}
