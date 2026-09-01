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

export interface SessionEventsResponse {
  events: SessionEventEnvelope[];
  cursor: number;
  status: string | null;
  outcome: string | null;
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
