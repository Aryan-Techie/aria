"use client";

import type { FieldCursorState } from "@/lib/useFieldCursor";

/**
 * The floating "she's writing this down" cursor - a small glowing dot, not a
 * literal mouse-pointer graphic, so it reads as "attention" rather than
 * "someone's cursor" (this app is voice-first; a pointer icon would suggest
 * a mouse driving the call, which is the opposite of the point). Positioned
 * absolutely inside whatever container passes its position in - see
 * useFieldCursor's containerRef.
 */
export function FieldCursor({ x, y, visible }: FieldCursorState) {
  return (
    <div
      className={`field-cursor${visible ? " visible" : ""}`}
      style={{ transform: `translate(${x}px, ${y}px)` }}
      aria-hidden="true"
    >
      <span className="field-cursor-ring" />
      <span className="field-cursor-dot" />
    </div>
  );
}
