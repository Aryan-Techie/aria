"use client";

import { Orb } from "@/components/Orb";

/**
 * The console's orb, standalone, for the /about hero. No live call to drive
 * it - `phase="idle"` already gives it the same synthetic-breath animation
 * the console shows before a call starts, so it needs no new mode of its own.
 */
export function StoryOrb() {
  return <Orb phase="idle" speaker="none" hold={false} getLevel={() => 0} />;
}
