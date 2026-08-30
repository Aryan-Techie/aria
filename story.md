# Aria — the story so far

**Team AR Voice** · Shipra Porwal, Ishtiyaque Alam, Aryan Jangra
**Track:** Adaptive AI Sales and Negotiation Agent
**Stage:** Round 3, Online Mentorship & Development Sprint

---

## 1. The problem we're actually solving

Scripted voice bots work right up until a real customer does something a script didn't anticipate — interrupts mid-sentence, asks an out-of-order question, or changes a number they already gave. At that point most voice bots either restart the flow or hand off blind. A real salesperson doesn't do that: they listen, adapt, and keep the thread. That's the gap the track brief asks us to close, and it's the gap Aria is built for.

## 2. Aria, in one paragraph

Aria is a real-time voice sales agent built on **Agora's Conversational AI Engine**. Instead of a decision tree, Aria's "brain" is an LLM-driven tool-calling loop that decides — turn by turn, live — whether to search a product knowledge base, update a lead's qualification record, check calendar availability, log an objection, or escalate to a human. Agora handles the hard real-time-audio problem (speech-to-text, barge-in, text-to-speech); we own the reasoning and the outcome.

**For this mentor demo, Aria plays an Apple Business sales specialist** — she sells real Apple products (Mac, iPhone, iPad fleets) to companies, using real pricing and real comparison material. We picked this because it's instantly understandable to anyone watching, and because Apple's actual enterprise sales motion (a business buying N devices, on a budget, on a timeline) maps naturally onto the qualification data Aria already tracks — no shortcuts taken to make the demo relatable.

## 3. What makes it different — and what's actually built to back each claim

- **Grounded, not scripted.** Every pricing/spec/comparison answer comes from a live knowledge-base search — Aria is instructed to say "I'm not sure" rather than invent a number.
- **A requirement change is a field update, not a restart.** Qualification state (company, device count, budget, timeline, pain points) lives in a deterministic record a tool writes to directly. When a customer corrects "10 devices" to "50 devices" mid-call, it's the same lead record with one field overwritten — not a re-derived guess. Verified in an automated test that scripts exactly this correction.
- **Escalation is a safety net, not just an LLM's opinion.** Deterministic guardrails watch every turn — two consecutive frustrated turns, the same unresolved objection raised three times, or a low-confidence knowledge-base search — and force a handoff even if the model doesn't ask for one. The handoff is a real Slack post with an AI-written brief, not a database row nobody reads.
- **Barge-in for free.** Agora detects when the customer talks over Aria and stops the agent's audio natively — we didn't build any of that ourselves.

## 4. How it's built — the tech, in plain terms

Everything below is a real decision we made and can go deeper on if asked — this is the short version.

| Piece | What it actually is | Why we picked it |
|---|---|---|
| **Agora Conversational AI Engine** | The service that runs the actual phone-call plumbing: it listens to the customer, turns speech into text, detects when they're speaking (including interrupting), and turns Aria's reply back into speech. | It's the track's required foundation, and it means we never had to build real-time audio, interruption-detection, or voice synthesis ourselves — genuinely hard problems we got for free. |
| **Deepgram (speech-to-text) & MiniMax (text-to-speech)** | The actual ASR/TTS engines Agora calls behind the scenes. | Agora supports several vendors; these two work under Agora's own "managed" billing, meaning **we don't need separate accounts or API keys with either company** — it's bundled into what we already pay Agora. We only found the right combination by testing directly against Agora's live API — the general docs weren't precise enough on their own. |
| **Anthropic** | The actual reasoning model — the "brain" that decides what to say and when to use a tool. | Agora's engine doesn't do the thinking itself; it calls out to whatever LLM we point it at, once per turn. We chose Anthropic for its tool-calling quality. |
| **A Python backend we wrote (FastAPI)** | Our own server that Agora calls into on every customer turn. It holds Aria's personality/instructions, decides which tools to call (search products, update the lead, book a meeting, escalate), and sends back what Aria should say. | This is the actual "adaptive" part of the product — everything that makes Aria different from a script lives here, not inside Agora. |
| **A small knowledge base (our own text search)** | Four short documents (device pricing, features, PC-fleet comparison, FAQ) that Aria searches before answering a product question. | We first tried a fancier "AI search" library, but it tried to download a large model on first use and hung for 90+ seconds — a real risk on demo day. Plain keyword search is instant and never needs the internet, and it's plenty accurate for four short documents. |
| **A mock CRM and calendar** | Fake-but-realistic lead records and open meeting slots, seeded ahead of time, that Aria's tools read and write during a call. | The brief allows dummy data here — building a real CRM integration wasn't the point of this hackathon; showing the *agent* correctly qualifying and booking is. |
| **mem0 + Voyage AI (session memory)** | A memory system that lets Aria recall things a customer said much earlier in a long call, beyond what fits in the normal conversation window. | mem0 is a known memory library; Voyage AI supplies the "embeddings" (a way of turning sentences into searchable numbers) it needs. We use Voyage instead of mem0's default (OpenAI) because we didn't want a second AI vendor account just for this — Voyage is free-tier and pairs cleanly with Anthropic. It's optional: the call works fine without it, it just won't recall very old details as precisely. |
| **A live Slack notification (Escalation)** | When Aria hands a call off to a human, it posts a real message to Slack with an AI-written summary of the issue. | This is the one part of the demo that's a genuinely real external integration rather than fake data — it proves the handoff isn't just a log entry nobody reads. |
| **Next.js / React (the operator console)** | The on-screen dashboard we watch during a call — live transcript, what Aria has learned about the lead, and an alarm-style meter that lights up on escalation. | This isn't what the customer sees (they only hear Aria on the phone) — it's our own instrument panel for demoing and debugging, styled deliberately like a recording-studio mixing desk rather than a generic dashboard, because that's genuinely how the data behaves: every action Aria takes prints onto a live timeline like a track being recorded. |
| **pytest (automated tests)** | 70 small, fast checks that run the entire "brain" — tool calls, memory, escalation rules — using fake stand-ins instead of real phone calls, in about 1.5 seconds. | Lets us change code confidently without needing a live Agora call every time, and catches logic bugs before they ever reach a real customer conversation. |
| **cloudflared (a tunnel)** | A temporary public web address that forwards to our laptop, since Agora's servers need to reach our backend over the real internet, not just `localhost`. | Free, already installed, works instantly for testing — a real deployment would use a permanent hosted server instead. |

## 5. The demo scenario

One continuous call, four beats, no restart between any of them:
1. **Pricing question** — "We're thinking about switching our team to Mac and iPhone — what would that cost?" → grounded answer from the real device-pricing knowledge base.
2. **Objection, mid-answer** — "wait, that's a lot more than our Windows laptops" → native barge-in, direct answer on total cost of ownership (support burden, device lifespan, resale value), grounded again, not a script restart.
3. **Requirement change** — "actually it's more like 50 people, not 10" → same lead record, device count corrected in place, volume pricing re-quoted if asked.
4. **Move to next step** → live calendar availability check → a real slot booked with an Apple Business specialist → the call ends in a concrete outcome, not a vague "we'll follow up."

Full script with exact lines: `docs/demo_script.md`.

## 6. Proof of engineering rigor — the part we're proudest of

- **70 automated tests, 13 test files, ~1.3 seconds, zero network calls.** The entire tool-calling brain is tested against fakes, so it's fast and doesn't depend on any external service being up.
- **Verified against Agora's real API, not assumed — repeatedly.** We didn't guess the request shape; we pulled it from the live docs mid-build and caught real mismatches (config fields nest differently than an earlier draft assumed; the "managed" ASR/TTS mode needed exact vendor endpoint URLs the general docs didn't spell out precisely — we found the working combination by testing directly against Agora's live validation errors).
- **It's genuinely live now — and we found real bugs by making real calls, not by reading code.** Three separate bugs only a live call could have surfaced, each found and fixed within minutes of it happening:
  1. A CORS/error-handling bug that turned every backend failure into an opaque, undebuggable browser error.
  2. A missing RTM authentication token — the voice call itself worked, but the live event channel (the one that drives our on-screen transcript/qualification panels) silently failed with `DYNAMIC_ENABLED_BUT_STATIC_KEY` until we noticed we'd built the token-generation code but never actually wired it into the call-start response.
  3. A live-call-only crash where Agora occasionally sends a turn with empty transcript content (an interim speech-recognition slot), which Anthropic's API flatly rejects — invisible to any test using scripted, well-formed conversation history.
- **Honest engineering calls, made with evidence.** We swapped away from a "smarter" search library after watching it hang on a model download; we rewired our memory library to a different AI provider than its own default because it didn't fit our stack; we chased down the exact working ASR/TTS configuration through live trial and error against Agora's own error messages rather than guessing.

## 7. Where things stand, plainly

**Confirmed working, live, this session:**
- Real Agora session start → real agent joins → real call connects → **a real customer turn was received and answered correctly** through the full pipeline (transcript in, tool-calling brain, reply out) — not a simulation.
- Zero external ASR/TTS accounts needed: Deepgram + MiniMax both run under Agora's own managed billing.
- CRM, calendar, RAG, escalation, memory, and the full tool-calling loop — all built and tested.
- The operator console (revamped this session into a mixing-console-styled live view) builds and runs cleanly.

**Still open:**
- A complete, uninterrupted run through all 4 demo beats in one call hasn't been rehearsed yet — individual pieces are proven, the full choreography isn't yet.
- Turn-taking latency hasn't been formally measured yet.

This is a materially stronger position than a few hours ago: this was a "should work" architecture; it's now a call that has actually happened, with real bugs found and fixed live, not theorized about.

## 8. The plan from here

1. **Now:** rehearse the full 4-beat script end to end on a real call; measure turn-taking latency.
2. **Round 4 submission (due 2026-09-06):** working prototype, GitHub repo, demo video of the full 4-beat script, architecture writeup, pitch deck.
3. **Round 5 finale prep (2026-09-12):** live demo rehearsal, judge Q&A prep.

## 9. What we want from this mentor session

- A second opinion on keeping the entire tool-calling loop inside our own backend rather than delegating to Agora's `llm.mcp_servers` routing.
- Any latency-tuning guidance now that we have a real number to work from, once we've measured one.
- Feedback on the demo console's design direction — is a live "session timeline" the right way to make the agent's reasoning visible to judges, or is there a clearer way to show it in the time we'll have?
