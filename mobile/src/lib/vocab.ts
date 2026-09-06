/**
 * What the console calls things the backend names in snake_case. Copied from
 * frontend/lib/vocab.tsx so a tool is described the same way on both surfaces
 * — a demo where the phone and the laptop use different words for the same
 * moment is a demo that looks like two products.
 */

/** Present tense, shown while a tool is in flight. */
const TOOL_BUSY: Record<string, string> = {
  search_pricing_rag: 'Pulling those numbers up',
  check_inventory: 'Checking what is in stock',
  crm_upsert_lead: 'Writing to the CRM',
  crm_qualify_lead: 'Qualifying the lead',
  log_objection: 'Noting that',
  update_sentiment: 'Reading the room',
  negotiate_deal: 'Checking with the deal desk',
  calendar_check_availability: 'Looking at the calendar',
  calendar_book_meeting: 'Booking it',
  ask_solutions_engineer: 'Asking a solutions engineer',
  escalate_to_human: 'Bringing a person in',
};

export function toolBusy(name: string): string {
  return TOOL_BUSY[name] ?? `Running ${name.replace(/_/g, ' ')}`;
}

/** app/sessions/models.py::Outcome, in words a person would say. */
const OUTCOME: Record<string, string> = {
  meeting_booked: 'Meeting booked',
  escalated: 'Handed to a person',
  qualified: 'Qualified',
  disqualified: 'Not a fit',
  follow_up: 'Follow-up needed',
};

export function outcomeLabel(outcome: string | null): string {
  if (!outcome) return 'Call ended';
  return OUTCOME[outcome] ?? outcome.replace(/_/g, ' ');
}

export function outcomeTone(outcome: string | null): 'good' | 'warn' | 'bad' | 'neutral' {
  if (outcome === 'meeting_booked' || outcome === 'qualified') return 'good';
  if (outcome === 'escalated') return 'warn';
  if (outcome === 'disqualified') return 'bad';
  return 'neutral';
}

/** mm:ss, the console's clock format. */
export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/** "2m ago" — relative age of an escalation, from its ISO created_at. */
export function timeAgo(iso: string): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return '';
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (seconds < 45) return 'just now';
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}
