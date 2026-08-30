# Demo script — Apple for Business pitch (the 4 required beats)

Rehearse this at least twice before the mentor call: once for functional correctness, once timed against the 800ms turn-taking target.

1. **Pricing question** — "Hi, we're looking at switching our team to Mac and iPhone — what would that cost us?"
   Aria should call `search_pricing_rag` and answer with real tier pricing (e.g. MacBook Air from $999/device), not a canned number.

2. **Competitor interruption** — while Aria is mid-answer, cut in with: "wait, that's a lot more than what we pay for our Windows laptops right now."
   Barge-in should stop Aria's audio immediately; Aria should address the total-cost-of-ownership comparison directly (grounded via RAG — support tickets, device lifespan, resale value) rather than restarting the pricing answer from scratch.

3. **Requirement change** — "Actually, it'd be more like 50 people, not 10."
   Aria should call `crm_upsert_lead` again with the corrected `user_count` — same lead record, not a new one — and can re-quote volume pricing if asked (20+ devices unlocks volume pricing).

4. **Move to next step** — "Can we get someone to walk our IT team through this?"
   Aria should call `calendar_check_availability`, offer real slot options, then `calendar_book_meeting` on your choice — ending the call with a concrete booked outcome with an Apple Business specialist.

## What to watch on the admin panel during rehearsal
- `GET /api/leads` — the qualification record should show `user_count: 50`, not 10, under the same lead id.
- `GET /api/calendar/slots` — the booked slot should disappear from availability.
- `GET /api/inbox` — only populated if an escalation guardrail or explicit ask fired.

## Objection lines worth rehearsing (from `app/rag/docs/competitor_comparison.md`)
- "It's more expensive than a PC" → total cost of ownership, not sticker price.
- "Our team knows Windows, switching is risky" → real migration tooling + most employees already use iPhone personally.
- "Will our software still work?" → Microsoft 365 / Google Workspace / Slack / Zoom / Adobe all run natively on Mac.

## Latency check
Watch `tool_call_started`/`tool_call_finished` RTM event timestamps (or `AGENT_METRICS` if enabled) for any hop taking noticeably longer than the rest — the RAG search and the tool-calling round trip to the LLM are the most likely candidates if a turn feels sluggish.
