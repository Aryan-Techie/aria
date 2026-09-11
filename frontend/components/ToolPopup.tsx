"use client";

import { useEffect, useState } from "react";
import type { ToolRecord } from "@/components/ActivityCard";
import { toolBusy, toolDone } from "@/lib/vocab";

/** The two tools a customer actually experiences as "look something up
 * for me" - a discount or a booking isn't a lookup, so it stays out of
 * this popup and in the activity log where it belongs. */
const POPUP_TOOLS = new Set(["search_pricing_rag", "check_inventory"]);
const AUTO_HIDE_MS = 3200;

function firstStringArg(args: Record<string, unknown> | undefined): string | null {
  if (!args) return null;
  for (const key of ["query", "product"]) {
    const value = args[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

/**
 * A brief 3D card that pops up near the orb while Aria is looking up a
 * product - makes the "she's actually checking, not making it up" moment
 * visible instead of just a latency gap. Purely decorative: reuses the
 * same tool-call data ActivityCard already renders, no backend change.
 */
export function ToolPopup({ tools }: { tools: ToolRecord[] }) {
  const latest = tools.length ? tools[tools.length - 1] : null;
  const relevant = latest && POPUP_TOOLS.has(latest.tool) ? latest : null;
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!relevant) return;
    setVisible(true);
    if (relevant.ms === null) return;
    const id = setTimeout(() => setVisible(false), AUTO_HIDE_MS);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [relevant?.id, relevant?.ms]);

  if (!relevant || !visible) return null;

  const done = relevant.ms !== null;
  const query = firstStringArg(relevant.args);

  return (
    <div className={`tool-popup${done ? " done" : ""}`} key={relevant.id} aria-hidden="true">
      <div className="tool-popup-inner">
        <span className="tp-label">{done ? toolDone(relevant.tool) : toolBusy(relevant.tool)}</span>
        {query && <span className="tp-query">{query}</span>}
      </div>
    </div>
  );
}
