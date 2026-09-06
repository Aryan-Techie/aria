# Aria — live demo briefing (read this before the mentor call)

## 1. One-line pitch

Aria is a real-time voice sales agent for Apple Business. She talks to a customer on a live call, learns about the deal as it happens, brings in specialists when needed, and hands the call to a real human — with a written brief — the moment she should.

## 2. The stack, with full forms

| Piece | Full form / what it is | What we use it for |
|---|---|---|
| **Agora Conversational AI Engine** | Agora = real-time audio/video cloud. "Conversational AI Engine" is their service that runs an AI agent inside a voice call. | The whole phone-call layer: it captures the customer's audio, runs speech-to-text, detects interruptions (barge-in), calls our brain, and speaks the reply. |
| **RTC** | Real-Time Communication | Agora's audio channel. The customer's browser, Aria, and later Shipra all join the same RTC channel. |
| **RTM** | Real-Time Messaging | Agora's data channel. We publish events on it, but our console actually reads events over plain HTTP polling from our backend because that was more reliable. |
| **ASR** | Automatic Speech Recognition (speech-to-text) | **Deepgram Nova-3**, in "multi" language mode so it handles Hindi and English mixed in one sentence (Hinglish). |
| **TTS** | Text-to-Speech | **MiniMax speech-2.8-turbo**. Three voices: Aria (female), deal desk (second female), solutions engineer (male). |
| **Managed credentials** | Agora bills Deepgram and MiniMax through our Agora account. | We have no Deepgram or MiniMax keys. One vendor, one bill. |
| **LLM** | Large Language Model — the brain | **Google Gemini 3.5 Flash-Lite** as the primary model for every turn (chosen by measuring latency). Anthropic Claude Sonnet and Groq Qwen are configured as alternatives. |
| **FastAPI backend** | Python web framework | Our server. Agora calls it once per customer turn. All the logic lives here. |
| **Next.js console** | React framework | The operator dashboard you'll be showing: transcript, lead card, signals, deal, handoff. |
| **EspoCRM** | Open-source CRM (Customer Relationship Management) running in Docker | The real CRM. Aria creates and updates leads in it live. |
| **mem0 + Voyage AI** | mem0 = memory library. Voyage = embeddings provider (turns sentences into searchable vectors). | Long-term memory across turns so Aria can recall something said early in a long call. |
| **RAG** | Retrieval-Augmented Generation | Aria searches four product documents (pricing, features, PC comparison, FAQ) before answering product questions, instead of inventing numbers. |
| **cloudflared** | Cloudflare Tunnel | Gives our laptop a public HTTPS address so Agora's cloud can reach our backend. Free, no account. |
| **SMTP** | Simple Mail Transfer Protocol | Gmail with an App Password. Sends Shipra the join link on escalation, and sends meeting confirmations. |

## 3. How one turn works (the flow)

1. Customer speaks in the browser. Audio goes to Agora over RTC.
2. Agora runs Deepgram ASR and gets text.
3. Agora sends that text to our backend at `/agent/{session}/v1/chat/completions` — the same request shape as OpenAI's chat API, so Agora can talk to us like any LLM.
4. Our backend builds the prompt: Aria's persona, the current lead state, memory recalled from mem0, and the list of tools.
5. Gemini decides: answer directly, or call a tool first. Tools include: search products, update lead, log objection, update sentiment, negotiate deal, ask solutions engineer, check calendar, book meeting, escalate to human.
6. We run the tool, feed the result back, and Gemini writes the reply.
7. We stream the reply back to Agora token by token. Agora starts MiniMax TTS on the first chunk, so the customer hears the opening words while later words are still generating.
8. Every tool call and every transcript turn is written to the session's event log. The console polls that log every second and updates.

Target: under one second from the customer stopping talking to Aria starting.

## 4. Left brain / right brain memory

We split what Aria knows about the customer into two records, updated every turn.

**Left brain — facts. CRM-shaped.**
Company, device count, budget, timeline, pain points, decision stage. Written by the `crm_upsert_lead` tool straight into EspoCRM. A correction ("actually 50, not 10") is one field overwritten on the same lead, not a restart.

**Right brain — signals. The soft stuff.**
Sentiment right now, sentiment history (a list, one entry per turn), objections raised and whether they were resolved and how many attempts, competitor mentions. Written by `update_sentiment` and `log_objection`.

Why split: the left brain is what a salesperson types into a CRM. The right brain is what a salesperson feels about the call. The escalation guardrails read only the right brain. The CRM reads only the left brain.

On the console: Lead card = left brain. Signals card and Handoff card = right brain.

## 5. Three layers of who is talking

**Layer 1 — Aria.** The only one who talks to the customer. Warm, generalist, holds the conversation.

**Layer 2 — two specialists.** Neither talks to the customer directly. Aria asks them and relays the answer. Each gets its own voice so the customer hears a different person.

- **Deal desk** (`negotiate_deal` tool). Handles price. Aria alone may give at most 3% off. The desk may go to 10%. Beyond that a human must sign. The desk proposes, a policy engine clamps the number, and the customer hears a preformatted sentence — Aria never does the arithmetic herself. Each time the customer pushes again, the desk gives a smaller step, so the floor is felt coming.
- **Solutions engineer** (`ask_solutions_engineer` tool, male voice). Handles technical questions: compatibility, migration, MDM (Mobile Device Management, e.g. Intune or Jamf), security, rollout. Reads everything the retriever finds and is required to say exactly what it does not know instead of rounding a gap to reassurance. Can recommend escalation if the material has no answer.

**Layer 3 — a human.** Shipra. Reached by escalation.

## 6. How escalation works ("the frustration channel")

Two paths, both end in the same place.

**Path A — Aria's judgment.** The model calls `escalate_to_human` when the customer asks for a person or when she genuinely cannot resolve something.

**Path B — deterministic guardrails.** Code, not the model. Checked after every turn against the right brain:

| Guardrail | Rule |
|---|---|
| Frustration streak | Two consecutive turns where sentiment is skeptical or frustrated |
| Objection retry | The same objection raised three times without being resolved |
| Low confidence | The product search returned a weak match, so the answer would be a guess |

If any trips, escalation is forced even if the model did not ask for it. The Handoff card shows each guardrail's progress live (dots filling up), so the judge can see it approaching.

**What escalation does, in order:**
1. Writes an escalation record with an LLM-written brief: issue, blocker, sentiment, recommended action.
2. Puts it in the inbox (`GET /api/inbox`), posts to Slack, and now emails Shipra a join link.
3. Marks the session escalated in the CRM.
4. Aria tells the customer she is looping in a specialist. The call does not end.
5. The console shows "Copy join link for Shipra".

## 7. The human handoff (new)

1. Shipra opens the link on her phone. The page is served by our backend through the tunnel — no login, no app.
2. She sees the brief, the lead facts, the last twelve turns, and one button: Join call.
3. Join mints an Agora RTC token for her and puts her mic into the same channel the customer is in.
4. Her browser tells our backend she is in. The backend has Aria say "Shipra from our team is on the line now and has the full context, I'll hand you over", waits five seconds, and removes Aria from the channel.
5. Console shows "Shipra has the call · Aria has left". The customer never hung up; the voice changed.

This is a warm transfer: the human arrives already knowing the context, and the customer does not repeat themselves.

## 8. The console, card by card

- **Orb + caption**: who is speaking, driven by real audio levels.
- **Transcript** (right column): customer and Aria turns, streamed live from the backend as words are generated.
- **Tool calls** (left column): every tool with its latency in milliseconds.
- **Lead**: left brain, plus the stage tracker.
- **Signals**: current sentiment.
- **Deal**: the three limits (3% Aria, 10% desk, 18% floor) and each round offered.
- **Handoff**: the three guardrails with live progress, then the join link.
- **Activity**: tool history.
- **Brief** (after the call ends): the wrap-up summary written for the rep.

## 9. Likely mentor questions, with answers

**"Is this scripted?"** No. There is no decision tree. Each turn, the model decides which tool to call from the conversation. The demo script only tells the human what to say.

**"Why Gemini and not Claude?"** We measured. Flash-Lite gave the lowest turn latency on our calls, and the tool-calling quality was sufficient. Claude and Groq are one env line away.

**"Where does the pricing come from?"** From a pricing document searched by RAG, then clamped by a policy engine. The model never invents a number.

**"What happens when the model wants to give too big a discount?"** The engine clamps it. Above 10% a human must approve in the inbox; the call continues while they do, and Aria offers the approved figure on her next turn.

**"Why two specialist agents instead of one bigger prompt?"** Different objectives. The deal desk is optimised to hold margin. The solutions engineer is optimised to say precisely what it does not know. A warm generalist prompt does neither well.

**"How do you know she is frustrated?"** The model records a sentiment shift with a tool each turn. The guardrail is a plain rule over that history: two in a row. It is auditable and testable without a model.

**"What if the model never calls escalate?"** The guardrails force it. There is a test for exactly that case.

**"Why is the console polling instead of using Agora's RTM?"** RTM publishes returned 200 but the browser never received events reliably. Polling our own backend every second is observable and debuggable, and these panels are cosmetic, not call-critical.

**"What is the tunnel for?"** Agora's cloud must reach our backend over public HTTPS. cloudflared gives the laptop a temporary public URL. In production this would be a hosted server.

**"How does the transcript reach the screen?"** Our backend sees the customer's text in the request and Aria's text in the response. It publishes both to the event log; the console upserts them by turn id so Aria's reply grows in place while she speaks.

**"Is the CRM real?"** Yes, EspoCRM in Docker. Leads are created on the first tool call and updated field by field. Custom fields hold device count, budget, timeline, pain points, outcome, session id.

**"How does she handle Hindi and English mixed?"** Deepgram in multi-language mode for recognition. The prompt tells her to reply in the customer's language, Devanagari for Hindi. Product names and pre-formatted prices stay in English.

**"How do you test this?"** 242 automated tests, no network, about ten seconds. They run the whole tool loop with fake models and fake stores: corrections, escalation rules, deal clamping, voice selection, the LLM endpoint.

**"What breaks?"** Tunnel URL changes on every restart, so we never restart mid-demo. Voice switches are background REST calls, so a switch can land one sentence late. Email has a few seconds of lag, so the copy-link button is the primary path on stage.

**"What would you do next?"** Hosted backend instead of a tunnel. Real telephony (PSTN) instead of browser audio. Rep can rejoin Aria after the human leaves. Multiple reps and routing.

## 10. Numbers to have ready

| Item | Value |
|---|---|
| Discount limits | Aria 3%, desk 10%, human floor 18% |
| Frustration streak | 2 consecutive turns |
| Objection retry | 3 unresolved attempts |
| Tests | 242, ~10 s, zero network |
| Turn target | under 1 s to first spoken word |
| Console poll | every 1 s |
| Handoff line | 5 s, then Aria leaves |
