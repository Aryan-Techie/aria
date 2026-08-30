# Mentor session prep — Aria

For Shipra, Ishtiyaque, and Aryan. Goal of this session: leave with a second opinion on the design decisions we're least sure of, not just a "looks good." A ~20-minute structure below — trim the middle if the slot is shorter, the ask at the end is the part not to cut.

Reference: `story.md` (the narrative), `present.html` (the pitch page — see link once published), `docs/demo_script.md` (the 4-beat script).

---

## The one-line pitch

"Aria is a voice AI that qualifies and sells like a real salesperson, not a phone tree. For this demo she's selling Apple Mac/iPhone/iPad fleets to businesses — real pricing, real objection-handling, live over an actual phone call."

---

## Run of show (~20 min)

| Time | What | Notes |
|---|---|---|
| 0–2 min | The problem, in one breath | Don't over-explain — the mentor already knows the track brief. One sentence on why Aria is different (tool-calling brain, not a script), then move on. |
| 2–6 min | Architecture walkthrough | Share the artifact link, walk the diagram left to right: browser → Agora (owns audio + barge-in) → our backend (owns reasoning) → tool fan-out. Point out the inversion explicitly: Agora calls us, not the other way around. |
| 6–13 min | **Live call, for real** | This is the headline now — see below. It works. Do it live. |
| 13–16 min | What we found by actually running it | The 3 live-only bugs (see story.md §6) — this is the strongest engineering signal in the whole session. |
| 16–18 min | Roadmap | Tied to real dates (Sep 6 submission, Sep 12 finale). |
| 18–20 min | The ask | The three questions at the bottom of story.md §9. Ask them directly — this is what makes it a working session instead of a pitch. |

---

## Do the live call

This changed since our last prep pass: **a real call now works.** Don't fall back to describing it — place the call in front of the mentor and run the 4-beat script from `docs/demo_script.md`:

1. "We're thinking about switching our team to Mac and iPhone — what would that cost?"
2. *(interrupt mid-answer)* "wait, that's a lot more than our Windows laptops"
3. "actually it's more like 50 people, not 10"
4. "can we get someone to walk our IT team through this?"

While it's running, pull up `GET /api/leads` in a second tab so the mentor can see the qualification record update live. If anything breaks mid-call, that's fine — say so, show the backend log, and pivot to explaining what you're seeing. A live failure explained clearly is still stronger material than a fake success.

**Fallback if the tunnel/call isn't cooperating that day:** run the test suite live (`cd backend && source .venv/bin/activate && python -m pytest tests/ -q`) and walk the console UI shell instead — both are still real and running, just not a live phone call.

---

## Tech stack — simple version, with the deep-dive ready

Lead with the plain-language column. If the mentor pushes on any row, the deep-dive is right there — don't over-explain up front.

| What it is (say this) | The real detail (if asked) |
|---|---|
| "Agora handles the actual phone call — hearing the customer, noticing when they interrupt, speaking Aria's replies." | Agora's Conversational AI Engine: streaming ASR, native VAD-based barge-in, streaming TTS. We never call Agora's LLM — Agora calls *our* server once per turn, at a URL we mint per session. |
| "The actual speech recognition and voice come from Deepgram and MiniMax, but we don't pay them directly — it's bundled into Agora." | `credential_mode: "managed"` — Agora validates the vendor's real endpoint URL against its own allowlist and injects its own key server-side. We only found the exact working URL/model combo by testing directly against Agora's live validation errors; the general docs weren't precise enough. |
| "Anthropic's model is the actual brain — it decides what to say and when to look something up or update a record." | Called via Anthropic's Messages API with a tool-calling loop (up to 4 hops per turn) against a fixed toolset: search product info, update the lead, check/book calendar, log an objection, escalate. |
| "We wrote our own server that Agora talks to — that's where all the actual 'sales agent' logic lives." | Python, FastAPI. Endpoint: `POST /agent/{session_id}/v1/chat/completions`, OpenAI-chat-completions-shaped in and out. |
| "Aria looks things up in a small real knowledge base instead of making stuff up." | Plain keyword search (TF-IDF), not an embeddings model — a deliberate downgrade from a fancier library that hung trying to download a model on first use. Instant, zero network dependency, plenty accurate for 4 short docs. |
| "The CRM and calendar are fake data, on purpose — the point of this hackathon is the agent, not a CRM integration." | Seeded Python dicts. Lead records are keyed by session id and updated in place via field-level upserts. |
| "Aria can remember things said much earlier in a long call." | mem0, backed by Anthropic (for fact extraction) and Voyage AI (for embeddings) instead of mem0's OpenAI default — we didn't want a second AI vendor account. Fully optional; the call works without it. |
| "When Aria hands off to a human, that's a real Slack message, not a log entry." | A real Incoming Webhook POST, with an LLM-written brief (issue/blocker/sentiment/recommended action), triggered either by the model's own judgment or by deterministic guardrails (frustration streak, repeated objection, low search confidence). |
| "The screen we're watching isn't what the customer sees — it's our own instrument panel." | Next.js/React, styled as a mixing console (session timeline = automation lane, escalation = a meter clipping red). The customer only ever hears Aria on the phone. |

---

## Anticipated questions

**"Why Apple products for the demo instead of your original SaaS pricing pitch?"**
Because it's instantly understandable to anyone watching — nobody needs the track brief explained to follow "a company buying 50 iPhones." The underlying architecture didn't change at all; we just swapped the knowledge base and system prompt. That itself is a feature: the brain is generic, the pitch is configurable.

**"Why not use Agora's `llm.mcp_servers` to route tool calls instead of building your own loop?"**
Because tool execution has to update our own session state (the CRM record, the escalation triggers, the live event panel) — if Agora routed tool calls to an external MCP server directly, that server would have no natural hook back into our session store without rebuilding the same plumbing anyway.

**"Why keyword search instead of embeddings for the knowledge base?"**
We tried a real embeddings library first — it hung 90+ seconds trying to download a model on first use, with no network progress. Not a risk worth taking on demo day for 4 short documents.

**"What's your actual turn-taking latency?"**
Being measured this session as we get real calls working — good candidate for the mentor's guidance once we have a number.

**"What happens if a tool call fails mid-conversation?"**
Each tool handler returns a structured error rather than raising, fed back to the model as a tool result so it can recover in the conversation. This same discipline is what caught the empty-transcript-turn bug (see below) — the fix was to filter, not to let a bad turn crash the call.

**"What's the most surprising thing you learned actually running this?"**
Three separate bugs that only a live call could ever surface: a CORS/error-handling bug that hid the real cause of every backend failure from the browser; a missing RTM auth token that broke the live event panel silently while the actual voice call kept working (found from a real Agora error code, `DYNAMIC_ENABLED_BUT_STATIC_KEY`); and a live-only crash where Agora sent a blank transcript slot that Anthropic's API flatly rejected. None of these show up in a scripted test suite — they only exist at the boundary with a real, messy, live system.

---

## Delivery notes

- **Lead with the live call.** It's the strongest thing in this whole session — a working demo beats a described one every time.
- **Don't oversell.** Say plainly that the full 4-beat script hasn't been rehearsed end-to-end yet, even though the pieces are proven.
- **Frame gaps as a plan, not an apology.** "Here's exactly what's left and when it happens" beats "we haven't gotten to X yet."
- **If a question goes past the simple explanation, that's fine — use the deep-dive column above.** You don't need to memorize it; it's written down.
