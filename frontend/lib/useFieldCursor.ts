import { useEffect, useRef, useState } from "react";
import type { LeftBrain } from "@/lib/api";

/** Which `data-field` on LeadCard a LeftBrain key change should visit. */
const FIELD_FOR_KEY: Partial<Record<keyof LeftBrain, string>> = {
  name: "name",
  title: "name",
  company: "company",
  industry: "company",
  email: "reach",
  phone: "reach",
  user_count: "devices",
  budget_range: "budget",
  timeline: "timeline",
  decision_stage: "stage",
  pain_points: "pains",
};

// Visit order when several fields change in the same snapshot (the polling
// fallback can deliver a batch at once) - reading order a person would fill
// a form in, not whatever order Object.keys happens to return.
const VISIT_ORDER = ["name", "company", "reach", "devices", "budget", "timeline", "pains", "stage"];

const HOLD_MS = 900;
const FADE_DELAY_MS = 500;

export interface FieldCursorState {
  x: number;
  y: number;
  visible: boolean;
  field: string | null;
}

/**
 * Drives the floating "she's writing this down" cursor: diffs each new
 * LeftBrain snapshot against the last one, queues whichever fields actually
 * changed, and walks the queue one at a time, positioning at the target
 * field's live screen position (data-field="...") on `container`.
 *
 * Movement itself is a CSS transition on the returned x/y (see
 * FieldCursor.tsx) - this hook only decides WHERE and WHEN, never animates
 * a value itself, so a redirect mid-flight is just a new target, not a
 * fight between two animation loops.
 */
export function useFieldCursor(
  lead: LeftBrain | null,
  active: boolean,
  containerRef: React.RefObject<HTMLElement | null>
): FieldCursorState {
  const [state, setState] = useState<FieldCursorState>({ x: 0, y: 0, visible: false, field: null });
  const prevRef = useRef<LeftBrain | null>(null);
  const queueRef = useRef<string[]>([]);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reducedMotionRef = useRef(false);

  useEffect(() => {
    reducedMotionRef.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  // Diff incoming snapshots into the queue.
  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = lead;
    if (!active || reducedMotionRef.current || !lead) return;

    const changed = new Set<string>();
    (Object.keys(FIELD_FOR_KEY) as (keyof LeftBrain)[]).forEach((key) => {
      const before = prev ? prev[key] : undefined;
      const after = lead[key];
      const beforeStr = Array.isArray(before) ? before.join("|") : before;
      const afterStr = Array.isArray(after) ? after.join("|") : after;
      if (afterStr != null && afterStr !== "" && beforeStr !== afterStr) {
        const field = FIELD_FOR_KEY[key];
        if (field) changed.add(field);
      }
    });
    if (changed.size === 0) return;

    const ordered = VISIT_ORDER.filter((f) => changed.has(f));
    queueRef.current.push(...ordered.filter((f) => !queueRef.current.includes(f)));
  }, [lead, active]);

  // Walk the queue.
  useEffect(() => {
    if (!active) {
      setState((s) => ({ ...s, visible: false }));
      return;
    }

    const tick = () => {
      const container = containerRef.current;
      const next = queueRef.current.shift();
      if (!next || !container) {
        setState((s) => (s.visible ? { ...s, visible: false } : s));
        timerRef.current = setTimeout(tick, FADE_DELAY_MS);
        return;
      }
      const el = container.querySelector<HTMLElement>(`[data-field="${next}"]`);
      if (!el) {
        timerRef.current = setTimeout(tick, 50);
        return;
      }
      const rect = el.getBoundingClientRect();
      const containerRect = container.getBoundingClientRect();
      setState({
        x: rect.left + rect.width / 2 - containerRect.left,
        y: rect.top + rect.height / 2 - containerRect.top,
        visible: true,
        field: next,
      });
      el.classList.add("field-fill-pulse");
      timerRef.current = setTimeout(() => {
        el.classList.remove("field-fill-pulse");
        tick();
      }, HOLD_MS);
    };

    timerRef.current = setTimeout(tick, 50);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return state;
}
