import { useCallback, useEffect, useRef, useState } from 'react';

import { fetchSessionEvents, type LeftBrain, type SessionEventEnvelope } from './api';

/**
 * The live call, assembled from the event poll.
 *
 * A trimmed port of the console's reducer (frontend/app/page.tsx:151-251). The
 * deal-round and discount-approval branches are deliberately absent: on this
 * app a discount is settled by Aria's own ceiling and the deal desk, never by
 * a person on a phone, so those envelopes are read and ignored.
 *
 * Two details from the console are load-bearing and kept exactly:
 * transcript turns are upserted by `turn-{role}-{turn_id}` so a reply that
 * streams in updates in place instead of printing twice, and tool
 * started/finished are matched FIFO per tool name because the two envelopes
 * share no id.
 */

export type Turn = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  final: boolean;
};

export type CallNote = {
  id: string;
  tone: 'good' | 'warn' | 'bad' | 'info';
  text: string;
};

export type SessionState = {
  turns: Turn[];
  notes: CallNote[];
  /** Name of the tool currently running, for the caption. */
  busyTool: string | null;
  outcome: string | null;
  status: string | null;
  lead: LeftBrain | null;
  /** Set once a person has taken the call. */
  repOnCall: string | null;
  ariaLeft: boolean;
  escalated: boolean;
};

const EMPTY: SessionState = {
  turns: [],
  notes: [],
  busyTool: null,
  outcome: null,
  status: null,
  lead: null,
  repOnCall: null,
  ariaLeft: false,
  escalated: false,
};

export function useSessionPoll(sessionId: string | null, active: boolean): SessionState {
  const [state, setState] = useState<SessionState>(EMPTY);
  // In-flight tool starts, per tool name, oldest first.
  const inFlight = useRef<Map<string, number>>(new Map());

  const apply = useCallback((envelope: SessionEventEnvelope) => {
    const p = envelope.payload;
    setState((prev) => {
      switch (envelope.type) {
        case 'transcript_turn': {
          const role = p.role === 'user' ? 'user' : 'assistant';
          const text = String(p.text ?? '');
          if (!text) return prev;
          const id = `turn-${role}-${String(p.turn_id ?? envelope.ts)}`;
          const turn: Turn = { id, role, text, final: Boolean(p.final) };
          const i = prev.turns.findIndex((t) => t.id === id);
          if (i >= 0) {
            const turns = [...prev.turns];
            turns[i] = turn;
            return { ...prev, turns };
          }
          return { ...prev, turns: [...prev.turns, turn] };
        }
        case 'tool_call_started': {
          const tool = String(p.tool_name ?? 'tool');
          inFlight.current.set(tool, (inFlight.current.get(tool) ?? 0) + 1);
          return { ...prev, busyTool: tool };
        }
        case 'tool_call_finished': {
          const tool = String(p.tool_name ?? 'tool');
          const open = (inFlight.current.get(tool) ?? 0) - 1;
          if (open > 0) inFlight.current.set(tool, open);
          else inFlight.current.delete(tool);
          const stillBusy = inFlight.current.keys().next();
          return { ...prev, busyTool: stillBusy.done ? null : stillBusy.value };
        }
        case 'qualification_updated':
          return { ...prev, lead: p as LeftBrain };
        case 'escalation_triggered':
          return {
            ...prev,
            escalated: true,
            notes: [
              ...prev.notes,
              {
                id: `note-${envelope.ts}`,
                tone: 'bad',
                text: p.reason
                  ? `Handed to a person: ${String(p.reason)}`
                  : 'Handed to a person with a written brief',
              },
            ],
          };
        case 'call_outcome_set': {
          const outcome = String(p.outcome ?? '');
          const notes =
            outcome === 'meeting_booked'
              ? [
                  ...prev.notes,
                  {
                    id: `note-${envelope.ts}`,
                    tone: 'good' as const,
                    text: 'Meeting booked. The invite is on its way.',
                  },
                ]
              : prev.notes;
          return { ...prev, outcome, notes };
        }
        case 'rep_joined': {
          const name = String(p.rep_name ?? 'A colleague');
          return {
            ...prev,
            repOnCall: name,
            notes: [
              ...prev.notes,
              { id: `note-${envelope.ts}`, tone: 'good', text: `${name} is on the call.` },
            ],
          };
        }
        case 'aria_left':
          return {
            ...prev,
            ariaLeft: true,
            notes: [
              ...prev.notes,
              { id: `note-${envelope.ts}`, tone: 'info', text: 'Aria has left the call.' },
            ],
          };
        default:
          // objection_logged and the deal envelopes surface elsewhere or not
          // at all on this app. Read and dropped on purpose.
          return prev;
      }
    });
  }, []);

  // Reset whenever a new call starts, so a second call never inherits the
  // first one's transcript.
  useEffect(() => {
    inFlight.current.clear();
    setState(EMPTY);
  }, [sessionId]);

  useEffect(() => {
    if (!active || !sessionId) return;
    let cancelled = false;
    let cursor = 0;

    const poll = async () => {
      try {
        const data = await fetchSessionEvents(sessionId, cursor);
        if (cancelled) return;
        cursor = data.cursor;
        for (const envelope of data.events) apply(envelope);
        setState((prev) => ({
          ...prev,
          status: data.status,
          outcome: data.outcome ?? prev.outcome,
          lead: data.left_brain ?? prev.lead,
        }));
      } catch {
        // Transient. The next tick retries — the console does the same, and a
        // dropped poll on a moving tunnel is not worth showing the user.
      }
    };

    void poll();
    const timer = setInterval(poll, 1000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [sessionId, active, apply]);

  return state;
}
