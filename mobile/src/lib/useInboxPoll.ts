import * as Haptics from 'expo-haptics';
import { useEffect, useRef, useState } from 'react';

import { fetchInbox, type EscalationRecord } from './api';
import { getRepUnlocked } from './storage';

/**
 * Waiting handoffs, for the rep.
 *
 * Poll-only, by design: there is no push path to a rep anywhere in the backend
 * — app/rtm/publisher.py addresses the customer's own channel and nothing
 * else, and the only outbound notifications are a Slack webhook and an email
 * with a join link. So the app asks, every five seconds, while it is open.
 *
 * /api/inbox has no cursor, no filter and no updated_at (routes/admin.py:28),
 * so this fetches the lot and diffs on id. The list is short — it is one
 * demo's worth of escalations, not a queue.
 *
 * `deal_approval` records are dropped here rather than shown and disabled.
 * Aria settles discounts against her own ceiling and the deal desk's; a person
 * on a phone is only ever wanted for the other kind.
 */

const INTERVAL_MS = 5000;

export function useInboxPoll(enabled: boolean): {
  handoffs: EscalationRecord[];
  /** Ids that arrived after this hook started watching. */
  fresh: Set<string>;
  clearFresh: () => void;
} {
  const [handoffs, setHandoffs] = useState<EscalationRecord[]>([]);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const all = await fetchInbox();
        if (cancelled) return;
        const open = all.filter((r) => r.kind === 'handoff');

        // The first response establishes the baseline. Without this every
        // escalation from earlier in the day would buzz the phone at launch.
        if (seen.current === null) {
          seen.current = new Set(open.map((r) => r.id));
        } else {
          const arrivals = open.filter((r) => !seen.current!.has(r.id));
          if (arrivals.length > 0) {
            arrivals.forEach((r) => seen.current!.add(r.id));
            setFresh((prev) => new Set([...prev, ...arrivals.map((r) => r.id)]));
            void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
          }
        }

        // Newest first: the person waiting longest is not the urgent one, the
        // person who just arrived is.
        setHandoffs([...open].reverse());
      } catch {
        // Transient. Next tick retries.
      }
    };

    void poll();
    const timer = setInterval(poll, INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled]);

  return { handoffs, fresh, clearFresh: () => setFresh(new Set()) };
}

/** Whether the rep screen has been revealed. Re-checked on focus. */
export function useRepUnlocked(): [boolean, (on: boolean) => void] {
  const [unlocked, setUnlocked] = useState(false);
  useEffect(() => {
    void getRepUnlocked().then(setUnlocked);
  }, []);
  return [unlocked, setUnlocked];
}
