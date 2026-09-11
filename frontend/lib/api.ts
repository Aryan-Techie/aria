const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface StartCallResponse {
  session_id: string;
  channel_name: string;
  app_id: string;
  uid: number;
  rtc_token: string;
  rtm_token: string;
  agent_id: string | null;
}

export interface EndCallResponse {
  session_id: string;
  status: string;
  outcome: string;
}

export async function startCall(): Promise<StartCallResponse> {
  const res = await fetch(`${BACKEND_URL}/api/call/start`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to start call: ${res.status}`);
  return res.json();
}

export async function endCall(sessionId: string): Promise<EndCallResponse> {
  const res = await fetch(`${BACKEND_URL}/api/call/${sessionId}/end`, { method: "POST" });
  if (!res.ok) throw new Error(`Failed to end call: ${res.status}`);
  return res.json();
}

export interface SessionEventEnvelope {
  type: string;
  payload: Record<string, unknown>;
  ts: string;
}

/** app/memory/schema.py::LeftBrain - the CRM-shaped facts. */
export interface LeftBrain {
  name?: string | null;
  title?: string | null;
  company?: string | null;
  industry?: string | null;
  email?: string | null;
  phone?: string | null;
  user_count?: number | null;
  budget_range?: string | null;
  timeline?: string | null;
  pain_points?: string[];
  decision_stage?: string | null;
  status?: string | null;
}

export type Sentiment = "positive" | "neutral" | "skeptical" | "frustrated";

export interface Objection {
  topic: "pricing" | "trust" | "product";
  raised_text: string;
  resolution_text?: string | null;
  resolved: boolean;
  attempts: number;
}

/** app/memory/schema.py::RightBrain - the softer signals that drive the
 * escalation guardrails. Only reachable through the poll; nothing publishes
 * sentiment as an event of its own. */
export interface RightBrain {
  objections: Objection[];
  sentiment: Sentiment;
  sentiment_history: Sentiment[];
  competitor_mentions: string[];
}

export interface SessionEventsResponse {
  events: SessionEventEnvelope[];
  cursor: number;
  status: string | null;
  outcome: string | null;
  left_brain?: LeftBrain;
  right_brain?: RightBrain;
}

/** app/handoff/models.py::CallSummary - the wrap-up the rep is sent. */
export interface CallSummary {
  session_id: string;
  lead_id: string | null;
  company: string | null;
  contact: string | null;
  outcome: string;
  headline: string;
  recommended_action: string;
  urgency: "now" | "today" | "this_week" | "none";
  facts: string[];
  agreed: string[];
  owed: string[];
  risks: string[];
  duration_seconds: number;
  turn_count: number;
  minutes_saved: number;
}

/**
 * The wrap-up is written in the background after End Call returns (it costs
 * a model call), so it is not there the instant the call ends. 404 until it
 * is; the caller polls.
 */
export async function fetchSummary(sessionId: string): Promise<CallSummary | null> {
  const res = await fetch(`${BACKEND_URL}/api/summaries/${sessionId}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to fetch summary: ${res.status}`);
  return res.json();
}

/**
 * Polled source for the live panels.
 *
 * The backend also publishes these envelopes over Agora RTM, but they were
 * not reaching the page (the REST publish returned 200 while the browser
 * never fired its message handler). These panels are cosmetic rather than
 * call-critical, so they read from our own backend over plain HTTP, which we
 * can actually observe and debug.
 */
export async function fetchSessionEvents(
  sessionId: string,
  since: number
): Promise<SessionEventsResponse> {
  const res = await fetch(`${BACKEND_URL}/api/session/${sessionId}/events?since=${since}`);
  if (!res.ok) throw new Error(`Failed to fetch session events: ${res.status}`);
  return res.json();
}

/**
 * Layer 3, in one click: a human signing off a discount while the call is
 * still running. The backend writes the figure onto the live session and
 * Aria offers it on her next turn - see routes/admin.py::approve_discount.
 */
export async function approveDiscount(
  escalationId: string,
  approvedPct: number,
  approvedBy = "sales manager"
): Promise<{ approved_pct: number; applied_to_live_call: boolean }> {
  const res = await fetch(`${BACKEND_URL}/api/inbox/${escalationId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved_pct: approvedPct, approved_by: approvedBy }),
  });
  if (!res.ok) throw new Error(`Approval failed: ${res.status}`);
  return res.json();
}

/** app/crm/models.py::Lead - one row per lead the CRM has ever seen, across
 * every call (live and past) - the dashboard's proof of "multiple calls at
 * once", not just the single lead a live call's own panel shows. */
export interface LeadRecord {
  id: string;
  name: string | null;
  company: string | null;
  status: string;
  decision_stage: string | null;
  updated_at?: string;
}

/** app/escalation/models.py::EscalationRecord, minus the transcript/brains -
 * just enough for the dashboard's open-escalations list. */
export interface EscalationRecord {
  id: string;
  session_id: string;
  reason: string;
  kind: "handoff" | "deal_approval";
  resolved_at: string | null;
  brief: { issue: string; blocker: string; sentiment: string; recommended_action: string };
}

/** app/metrics/capacity.py::snapshot - the "how many calls at once" numbers. */
export interface CapacitySnapshot {
  calls_total: number;
  calls_live_now: number;
  peak_concurrent_calls: number;
  reps_needed_for_peak: number;
  meetings_booked: number;
  escalated_to_human: number;
  containment_rate: number;
}

export async function fetchCapacity(): Promise<CapacitySnapshot> {
  const res = await fetch(`${BACKEND_URL}/api/metrics/capacity`);
  if (!res.ok) throw new Error(`Failed to fetch capacity: ${res.status}`);
  return res.json();
}

export async function fetchLeads(): Promise<LeadRecord[]> {
  const res = await fetch(`${BACKEND_URL}/api/leads`);
  if (!res.ok) throw new Error(`Failed to fetch leads: ${res.status}`);
  return res.json();
}

export async function fetchInbox(): Promise<EscalationRecord[]> {
  const res = await fetch(`${BACKEND_URL}/api/inbox`);
  if (!res.ok) throw new Error(`Failed to fetch inbox: ${res.status}`);
  return res.json();
}

/** app/tasks/models.py::Task - a follow-up for a rep to work later, written
 * by the schedule_followup tool - not a meeting, not a transcript line. */
export interface TaskRecord {
  id: string;
  session_id: string;
  lead_id: string | null;
  note: string;
  due: string | null;
  completed: boolean;
  created_at: string;
}

export async function fetchTasks(): Promise<TaskRecord[]> {
  const res = await fetch(`${BACKEND_URL}/api/tasks`);
  if (!res.ok) throw new Error(`Failed to fetch tasks: ${res.status}`);
  return res.json();
}

/** routes/admin.py::list_products - pricing.json's device_lineup joined
 * against live stock, plus anything added through createProduct below. */
export interface ProductListing {
  name: string;
  category: string | null;
  price_usd: number | null;
  note: string | null;
  stock_qty: number | null;
  status: string | null;
}

export interface ProductDraft {
  name: string;
  category?: string;
  price_usd: number;
  description?: string;
  stock_qty?: number;
}

export async function fetchProducts(): Promise<ProductListing[]> {
  const res = await fetch(`${BACKEND_URL}/api/products`);
  if (!res.ok) throw new Error(`Failed to fetch products: ${res.status}`);
  return res.json();
}

/**
 * The backend-team upload path - routes/admin.py::create_product. Writes the
 * stock row, appends a section to custom_products.md, and drops the cached
 * RAG index, so the next question asked can already find it.
 */
export async function createProduct(draft: ProductDraft): Promise<{ sku: string; name: string; price_usd: number }> {
  const res = await fetch(`${BACKEND_URL}/api/products`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
  if (!res.ok) throw new Error(`Failed to add product: ${res.status}`);
  return res.json();
}

export interface LeadEdit {
  name?: string;
  title?: string;
  company?: string;
  industry?: string;
  email?: string;
  phone?: string;
  user_count?: number;
  budget_range?: string;
  timeline?: string;
}

/**
 * Typed in rather than said out loud - see routes/call.py::update_lead_manually.
 * Written through the same crm_upsert_lead path the voice tools use, so the
 * next qualification_updated event carries it and Aria never asks again.
 */
export async function updateLeadManually(sessionId: string, edit: LeadEdit): Promise<{ lead: LeftBrain }> {
  const res = await fetch(`${BACKEND_URL}/api/session/${sessionId}/lead`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(edit),
  });
  if (!res.ok) throw new Error(`Lead update failed: ${res.status}`);
  return res.json();
}
