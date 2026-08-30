# Aria — Real-Time Voice AI Sales Agent

A voice agent that runs a complete B2B sales qualification call: it answers pricing questions from a knowledge base, handles objections, negotiates, tracks what the customer said, updates a CRM as details change, books a meeting, and escalates to a human with full context when it genuinely needs to.

Built on **Agora Conversational AI Engine** (RTC + RTM) with a custom LLM webhook.

## How it works

```
browser (Next.js)  ──RTC audio──►  Agora Conversational AI Engine
                                     │  ASR (Deepgram) → LLM → TTS (MiniMax)
                                     ▼
                          POST {PUBLIC_BASE_URL}/agent/{session}/v1/chat/completions
                                     │
                                     ▼
                          FastAPI orchestrator (this repo)
                            ├─ Groq / Anthropic tool-calling loop
                            ├─ TF-IDF RAG over product & pricing docs
                            ├─ CRM · calendar · escalation inbox
                            └─ SSE stream back to Agora
```

Agora handles transport, turn detection and barge-in. This backend owns the conversation: the persona, the tool loop, qualification state and the call outcome.

## Capabilities

| | How |
|---|---|
| Natural turn-taking & interruption | Agora VAD; each request replays full history, so a barge-in truncates cleanly |
| Qualification through conversation | `crm_upsert_lead`, `crm_qualify_lead` — updated mid-call as details change |
| Memory of earlier details | Structured call state re-injected into the prompt every turn |
| Objection handling | `log_objection` + negotiation playbook in the system prompt |
| Product / pricing retrieval | `search_pricing_rag` — zero-dependency TF-IDF, no vector DB |
| CRM / calendar integration | In-memory stores with JSON persistence, exposed over REST |
| Human escalation with context | `escalate_to_human` + an LLM-written handoff brief |
| Clear outcome | Meeting booked, lead qualified, or follow-up created |

### The eight tools

`search_pricing_rag` · `crm_upsert_lead` · `crm_qualify_lead` · `calendar_check_availability` · `calendar_book_meeting` · `escalate_to_human` · `log_objection` · `update_sentiment`

## Design notes

**Memory without a memory service.** Tools write qualification state (company, device count, budget, timeline, objections, sentiment) to a structured record every turn. That record is rendered back into the system prompt on each hop, so the agent holds onto a detail from twenty turns ago and notices when the customer *changes* one — at zero network cost.

**Latency.** Groq serves a tool-calling hop in ~0.7–1.7s versus ~4–6s for a frontier model. Replies stream as SSE so Agora starts speaking on the first chunk instead of waiting for the whole tool loop. RTM event publishing and memory write-back are fire-and-forget, off the response path. If Groq is rate-limited it fails fast (no retries, short timeout) and Anthropic serves the turn.

**Live UI over HTTP.** The backend publishes call events to Agora RTM *and* records them on the session; the browser polls `/api/session/{id}/events`. RTM publishes returned 200 while never reaching the page, and the panels are cosmetic — so they use a transport that can actually be debugged.

## Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example ../.env          # fill in real values
python -m pytest                 # 76 tests, no credentials needed
uvicorn app.main:app --port 8000
```

`.env` is read from the repo root (falling back to `backend/.env`), so it works from either directory.

For a real call, `PUBLIC_BASE_URL` must be a publicly reachable HTTPS URL — Agora calls back into `{PUBLIC_BASE_URL}/agent/{session_id}/v1/chat/completions`:

```bash
cloudflared tunnel --url http://localhost:8000
```

Quick-tunnel URLs change on every restart; update `PUBLIC_BASE_URL` and restart the backend when it does.

**Set `LLM_SHARED_SECRET`.** The webhook is exposed to the public internet through that tunnel, and the secret is the only thing between a stranger and your LLM bill. Requests without it get a 401.

## Frontend setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_BACKEND_URL at the backend
npm run dev
```

Open <http://localhost:3000> — not the tunnel URL, which serves the backend only.

## Demo & debug endpoints

- `GET /healthz` — liveness
- `GET /api/leads` — CRM records created by calls
- `GET /api/calendar/slots` — remaining open meeting slots
- `GET /api/inbox` — escalations with LLM-generated handoff briefs
- `GET /api/session/{id}/events` — live call events driving the UI panels

## Configuration

Everything is environment-driven — see `backend/.env.example`. Notable:

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `groq` (default) or `anthropic` |
| `GROQ_API_KEY` | Leave blank to run entirely on Anthropic |
| `LLM_SHARED_SECRET` | Required for a publicly exposed webhook |
| `STATE_DIR` | JSON snapshots for CRM/calendar/inbox; blank = in-memory |
| `ASR_VENDOR` / `TTS_VENDOR` | Deepgram / MiniMax, both under Agora managed credentials |

## Tests

```bash
cd backend && python -m pytest
```

76 tests, ~5s, zero network calls. `conftest.py` blanks the env file so the suite never reads real credentials or touches the filesystem.
