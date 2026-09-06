/**
 * Typed client for the Aria backend. Port of frontend/lib/api.ts, plus the two
 * rep endpoints the console never needed (it links out to routes/rep.py's own
 * HTML page instead).
 *
 * The one structural difference from the web client: the base URL is not a
 * build-time constant. The tunnel hostname rotates on every `run.bat`, so it
 * lives in AsyncStorage and is set here at boot and whenever Settings changes
 * it. Reading it from a module variable rather than threading it through props
 * keeps every call site a plain function call.
 */

import { getBaseUrl } from './storage';

let baseUrl = '';

export function setApiBase(url: string): void {
  baseUrl = url;
}

export function getApiBase(): string {
  return baseUrl;
}

export async function loadApiBase(): Promise<string> {
  baseUrl = await getBaseUrl();
  return baseUrl;
}

/** Thrown when no base URL is configured — Settings has never been filled in. */
export class NotConfiguredError extends Error {
  constructor() {
    super('No server address set. Open Settings and paste the backend URL.');
    this.name = 'NotConfiguredError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (!baseUrl) throw new NotConfiguredError();
  const res = await fetch(`${baseUrl}${path}`, init);
  if (!res.ok) throw new HttpError(res.status, await safeDetail(res));
  return res.json() as Promise<T>;
}

export class HttpError extends Error {
  constructor(
    public status: number,
    public detail: string
  ) {
    super(detail || `Request failed: ${status}`);
    this.name = 'HttpError';
  }
}

/** FastAPI puts its message in `detail`; anything else, fall back to the code. */
async function safeDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (body && typeof body.detail === 'string') return body.detail;
  } catch {
    // Not JSON. The status alone will have to do.
  }
  return '';
}

// ---------------------------------------------------------------- the call

export interface StartCallResponse {
  session_id: string;
  channel_name: string;
  app_id: string;
  uid: number;
  rtc_token: string;
  /** Unused on mobile — see lib/agora.ts for why RTM is not wired up here. */
  rtm_token: string;
  agent_id: string | null;
}

export interface EndCallResponse {
  session_id: string;
  status: string;
  outcome: string;
}

export function startCall(): Promise<StartCallResponse> {
  return request<StartCallResponse>('/api/call/start', { method: 'POST' });
}

export function endCall(sessionId: string): Promise<EndCallResponse> {
  return request<EndCallResponse>(`/api/call/${sessionId}/end`, { method: 'POST' });
}

// ------------------------------------------------------------ session poll

export interface SessionEventEnvelope {
  type: string;
  payload: Record<string, unknown>;
  ts: string;
}

/** app/memory/schema.py::LeftBrain — the CRM-shaped facts. */
export interface LeftBrain {
  company?: string | null;
  user_count?: number | null;
  budget_range?: string | null;
  timeline?: string | null;
  pain_points?: string[];
  decision_stage?: string | null;
}

export type Sentiment = 'positive' | 'neutral' | 'skeptical' | 'frustrated';

export interface Objection {
  topic: 'pricing' | 'trust' | 'product';
  raised_text: string;
  resolution_text?: string | null;
  resolved: boolean;
  attempts: number;
}

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
  /** Absent when the session is unknown — routes/call.py returns a short form. */
  left_brain?: LeftBrain;
  right_brain?: RightBrain;
}

/**
 * The live source of truth. The backend also publishes these envelopes over
 * Agora RTM, but frontend/lib/api.ts:107-115 records that the REST publish
 * returned 200 while the client never fired its handler — so HTTP polling is
 * what the console actually runs on, and what this app runs on too.
 *
 * `since` is a count, not a timestamp: pass back the previous cursor.
 */
export function fetchSessionEvents(
  sessionId: string,
  since: number
): Promise<SessionEventsResponse> {
  return request<SessionEventsResponse>(`/api/session/${sessionId}/events?since=${since}`);
}

// ----------------------------------------------------------------- wrap-up

/** app/handoff/models.py::CallSummary. */
export interface CallSummary {
  session_id: string;
  lead_id: string | null;
  company: string | null;
  contact: string | null;
  outcome: string;
  headline: string;
  recommended_action: string;
  urgency: 'now' | 'today' | 'this_week' | 'none';
  facts: string[];
  agreed: string[];
  owed: string[];
  risks: string[];
  duration_seconds: number;
  turn_count: number;
  minutes_saved: number;
}

/**
 * Written in the background after the call ends, because it costs a model
 * call. 404 until it lands; the caller polls. Null here means "not yet",
 * not "failed".
 */
export async function fetchSummary(sessionId: string): Promise<CallSummary | null> {
  try {
    return await request<CallSummary>(`/api/summaries/${sessionId}`);
  } catch (err) {
    if (err instanceof HttpError && err.status === 404) return null;
    throw err;
  }
}

// --------------------------------------------------------------- the rep

export type EscalationKind = 'handoff' | 'deal_approval';

export type TriggerSource =
  | 'llm'
  | 'frustration_streak'
  | 'objection_retry'
  | 'low_confidence'
  | 'deal_approval';

export interface EscalationBrief {
  issue: string;
  blocker: string;
  sentiment: string;
  recommended_action: string;
}

/** app/escalation/models.py::EscalationRecord, as returned by /api/inbox. */
export interface EscalationRecord {
  id: string;
  session_id: string;
  lead_id: string | null;
  reason: string;
  trigger_source: TriggerSource;
  kind: EscalationKind;
  resolved_at: string | null;
  approved_pct: number | null;
  approved_by: string | null;
  brief: EscalationBrief;
  left_brain: LeftBrain;
  right_brain: RightBrain;
  created_at: string;
}

/**
 * The whole inbox, every kind, oldest first, no cursor and no filter — see
 * routes/admin.py:28. Callers filter client-side; this app keeps only
 * `kind === "handoff"`, since discounts are settled by Aria's own ceiling and
 * the deal desk rather than by a person on a phone.
 */
export function fetchInbox(): Promise<EscalationRecord[]> {
  return request<EscalationRecord[]>('/api/inbox');
}

export interface HandoffDetails {
  escalation_id: string;
  session_id: string;
  rep_name: string;
  call_live: boolean;
  aria_on_call: boolean;
  reason: string;
  trigger_source: TriggerSource;
  brief: EscalationBrief;
  /** Renamed from left_brain/right_brain by routes/rep.py:60-78. */
  lead: LeftBrain;
  signals: RightBrain;
  transcript: { role: 'user' | 'assistant'; content: string }[];
  rtc: { app_id: string; channel: string; uid: number; token: string };
}

/**
 * Everything needed to join, in one call: the brief and a freshly minted RTC
 * token for the rep's fixed uid (2 — distinct from Aria's 1 and the customer's
 * random >= 100000).
 *
 * 404s once the call is over ("That call is no longer live", rep.py:53) — that
 * is an expected state, not a failure, and the list shows it as such.
 */
export function fetchHandoff(escalationId: string): Promise<HandoffDetails> {
  return request<HandoffDetails>(`/api/handoff/${escalationId}`);
}

/**
 * Called only after the mic is actually publishing. The backend replies
 * `handing_over`, has Aria speak her closing line, waits five seconds, then
 * removes her from the channel (rep.py:81-98). Calling it early would hand the
 * call to a rep who cannot yet be heard.
 */
export function markRepJoined(
  escalationId: string
): Promise<{ status: 'handing_over' | 'joined'; rep_name: string }> {
  return request(`/api/handoff/${escalationId}/joined`, { method: 'POST' });
}

/** Cheap reachability probe for the Settings screen. */
export async function ping(url: string): Promise<boolean> {
  try {
    const res = await fetch(`${url}/healthz`);
    return res.ok;
  } catch {
    return false;
  }
}
