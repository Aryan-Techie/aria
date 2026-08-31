# Aria — Real-Time Voice AI Sales Agent

Aria runs a complete B2B sales qualification call, out loud, in real time. She answers pricing
questions from a knowledge base, handles objections, negotiates, remembers what you told her
twenty turns ago, **writes to a real CRM while you are still talking**, books a meeting, and
escalates to a human with a written handoff brief when she genuinely needs to.

Built on **Agora Conversational AI Engine** (RTC + RTM) with a custom LLM webhook, a FastAPI
orchestrator, and **EspoCRM** running in Docker as the system of record.

> Open the console and an EspoCRM Lead page side by side. Say *"actually, make that fifty
> devices"* — the Lead updates itself, with no refresh, while she is still speaking.

---

## Quick start

**Windows — one command:**

```bat
run.bat
```

That checks your prerequisites, starts EspoCRM in Docker, provisions it, launches the backend,
opens a public tunnel, writes the tunnel URL into `.env`, restarts the backend so it picks the
URL up, starts the frontend, and opens both tabs. `run.bat stop` shuts it all down.

**Before the first run you need:**

| | Why | Get it |
|---|---|---|
| **Docker Desktop** | Runs EspoCRM + MariaDB | <https://docs.docker.com/desktop/install/windows-install/> |
| **Python 3.11+** | The backend | <https://www.python.org/downloads/> |
| **Node.js 18+** | The frontend | <https://nodejs.org/> |
| **cloudflared** | Public HTTPS URL so Agora can reach your machine | `winget install --id Cloudflare.cloudflared` |
| **A `.env`** | Credentials — see below | `copy backend\.env.example .env` |

`run.bat` verifies all five and tells you exactly what is missing before it changes anything.

**Minimum `.env` to make a call** (at the repo root, not `backend/`):

```ini
AGORA_APP_ID=...
AGORA_APP_CERTIFICATE=...
AGORA_CUSTOMER_KEY=...
AGORA_CUSTOMER_SECRET=...
ANTHROPIC_API_KEY=...
GROQ_API_KEY=...              # optional, but ~4x faster per hop
LLM_SHARED_SECRET=...         # any long random string — see Security
```

Then open **<http://localhost:3000>** and click Start. (Not the tunnel URL — that serves the
backend only, and its root returning `{"detail":"Not Found"}` is normal.)

<details>
<summary>Manual startup, or on macOS/Linux</summary>

```bash
# 1. CRM — first run pulls images and installs its own database (~2 min)
docker compose -f crm/docker-compose.yml up -d
python scripts/provision_crm.py          # role, API key, custom fields, layout
# paste the printed ESPOCRM_* lines into .env

# 2. backend
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# 3. tunnel — then put the https URL into PUBLIC_BASE_URL and RESTART the backend
cloudflared tunnel --url http://localhost:8000

# 4. frontend
cd frontend && npm install && npm run dev
```

Settings are cached with `lru_cache`, so editing `.env` while the backend runs does nothing —
it must be restarted. Quick-tunnel hostnames change on **every** cloudflared start; forgetting
to update `PUBLIC_BASE_URL` is the most common cause of "it worked yesterday".

</details>

---

## Architecture

```
browser (Next.js :3000) ──RTC audio──► Agora Conversational AI Engine
                                         ASR Deepgram → LLM → TTS MiniMax
                                                │
                       POST {PUBLIC_BASE_URL}/agent/{session}/v1/chat/completions
                                                │
                                    FastAPI (:8000) ── this repo
                                      ├─ Groq primary / Anthropic fallback
                                      ├─ tool loop (8 tools, max 6 hops)
                                      ├─ bridge line spoken when a lookup fires
                                      ├─ TF-IDF RAG over the product docs
                                      ├─ CRM + calendar ──► EspoCRM (:8080, Docker)
                                      ├─ confirmation email + .ics invite ──► SMTP
                                      ├─ escalation inbox
                                      └─ SSE stream back to Agora
```

### What Agora owns, and what this repo owns

Agora is the **phone system**. This backend is the **person**.

**Agora:** WebRTC transport · the Deepgram and MiniMax connections (under
`credential_mode: managed` it holds those sockets and injects its *own* vendor keys, which is
why neither key is in `.env`) · VAD, turn-taking and barge-in · calling this backend as if it
were OpenAI (`style: "openai"`) and streaming the SSE response into TTS chunk by chunk.

**This repo:** the persona, the tool loop, RAG, CRM and calendar, qualification state,
escalation, and every word she actually says. Agora never sees any of it.

### The eight tools

`search_pricing_rag` · `crm_upsert_lead` · `crm_qualify_lead` · `calendar_check_availability`
· `calendar_book_meeting` · `escalate_to_human` · `log_objection` · `update_sentiment`

---

## The CRM is real

Not a mock. EspoCRM in Docker, reachable at **<http://localhost:8080>** (`admin` /
`aria-demo-admin`), backing the `crm_*` and `calendar_*` tools.

- **Leads** — created and updated mid-call. Say 25 devices then change to 50, and one row
  changes; you do not get two leads for one call.
- **Meetings** — `calendar_book_meeting` writes a real Meeting, assigned to a rep, linked to
  the Lead, visible on the CRM calendar.
- **Stream** — EspoCRM writes its own timestamped audit trail: *"aria-agent updated this
  lead — In Process"*. Nothing in this repo produces that; the CRM is genuinely recording an
  agent working a lead.
- **Live push** — the `espocrm-websocket` container pushes changes to an open Lead page, so
  the record visibly fills in while she talks.

`provision_crm.py` sets it up headlessly — role, API key, rep user, seven custom fields and
the "Aria Qualification" panel — so it is reproducible on a fresh machine rather than being
twenty minutes of clicking.

**Falls back safely.** `CRM_BACKEND=memory` reverts to the in-process store, and that is also
the *automatic* fallback when the key is missing or EspoCRM is unreachable. A backend that
refuses to boot ten minutes before a demo is worse than one running on fixtures. Every CRM
failure is logged and swallowed: these calls sit on the turn path, and a lost row is
recoverable where a broken call is not.

---

## The customer gets the invite

Booking a meeting sends the customer a confirmation email with a real calendar
invite attached — accept it and the meeting lands in their Google or Outlook calendar.
`.ics` built in-process (`app/notify/ics.py`), delivered over plain SMTP, so it needs one
free Gmail App Password and no OAuth, no Calendar API, and no vendor SDK.

Off unless `EMAIL_ENABLED=true`, and a no-op — never an error — when it is off, when the
lead has no email address, or when the mail server refuses.

**Two hooks, one email.** It fires from `calendar_book_meeting`, backgrounded so an SMTP
handshake never spends the customer's patience mid-call, and again from `end_call`, which
adds the recap of what was actually captured. The second is a backstop, not a duplicate:
the "sent" flag is set only after a send that really succeeded, so a mail server that was
down at booking time gets another attempt at call end, and a send that worked is not
repeated. Booking-time alone would miss the retry; call-end alone would miss every call
where nobody presses the End Call button.

**Which means she has to ask for the address.** No email on the lead, no confirmation — so
the prompt makes her ask for it once a time is picked and read it back before booking. ASR
mangles email addresses more than anything else on a call.

---

## Design notes

**Memory without a memory service.** Tools write qualification state — company, device count,
budget, timeline, objections, sentiment — to a structured record every turn, and that record
is rendered back into the system prompt on each hop. She holds a detail from twenty turns ago
and notices when you *change* one, at zero network cost and with nothing to fail.

**Bridge lines fire on tools, not on timers.** Agora can speak a stall phrase itself, but it
triggers purely on how long the webhook has been quiet. Measured here: turns calling **no**
tool take 0.92s–2.55s to first byte, because the pipeline buffers whole hops; tool hops take
~1.4s. The ranges overlap, so no threshold separates them — set low enough to catch tool
calls, it fires on *every* turn. So the bridge line is emitted by our own pipeline at the
moment a lookup dispatches, chosen by *which* tool fired, at most one per turn, and never for
silent bookkeeping like writing a sentiment score. Agora knows *timing*; only this backend
knows *why* the pause exists.

**Speech that sounds spoken.** MiniMax `speech-2.8` renders `<#0.3#>` as a real pause and
`(breath)` / `(sighs)` / `(laughs)` as real audio, so the prompt uses them — but only after
`supports_speech_markup()` confirms the configured voice can, because any older model would
read them aloud as text. The frontend strips the markup from the transcript for display.

**Dates are not left to the model.** It called a Monday "Sunday the seventh" and 1 September
"the second". `calendar_check_availability` now returns a preformatted label per slot
("Tuesday 1 September at 10:00 AM") and the prompt says to read it verbatim. Removing the
arithmetic beats asking the model to be careful with it.

**Latency.** Groq serves a tool hop in ~0.7–1.7s against ~4–6s for a frontier model. Replies
stream as SSE so Agora starts speaking on the first chunk rather than waiting for the whole
tool loop. RTM publishing and memory write-back are fire-and-forget, off the response path.
A rate-limited Groq fails fast — no retries, short timeout — and Anthropic serves the turn.

**Live UI over HTTP, not RTM.** The backend publishes call events to Agora RTM *and* records
them on the session; the browser polls `/api/session/{id}/events`. RTM publishes returned 200
while never reaching the page, and these panels are cosmetic — so they run on a transport that
can actually be debugged.

---

## Configuration

Everything is environment-driven — see `backend/.env.example` for the annotated list.

| Variable | Purpose |
|---|---|
| `PUBLIC_BASE_URL` | Public HTTPS URL Agora calls back into. Changes every tunnel restart |
| `LLM_SHARED_SECRET` | Required — see Security |
| `LLM_PROVIDER` | `groq` (default) or `anthropic` |
| `GROQ_API_KEY` | Leave blank to run entirely on Anthropic |
| `CRM_BACKEND` | `espocrm` or `memory` |
| `ESPOCRM_API_KEY` | From `scripts/provision_crm.py` |
| `ESPOCRM_ASSIGNED_USER_ID` | Meetings need a real assignee; an api-type user cannot be one |
| `EMAIL_ENABLED` | Confirmation email + `.ics` invite on booking. Off by default |
| `SMTP_HOST` / `SMTP_PORT` | 587 STARTTLS or 465 implicit TLS; any provider |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Gmail needs an App Password, not the account password |
| `EMAIL_FROM` | Blank falls back to `SMTP_USERNAME` - most providers reject anything else |
| `EMAIL_BCC` | Optional silent copy to the rep on the meeting |
| `MINIMAX_EMOTION` | `fluent` reads conversational; `happy` sounds like a chirpy IVR |
| `FILLER_WORDS_ENABLED` | Agora's own stall phrases. Off — see Design notes |
| `STATE_DIR` | JSON snapshots for the in-memory stores; blank = pure memory |

### Debug endpoints

`GET /healthz` · `GET /api/leads` · `GET /api/calendar/slots` · `GET /api/inbox` ·
`GET /api/session/{id}/events`

---

## Security

**Set `LLM_SHARED_SECRET`.** The webhook is exposed to the public internet through your
tunnel, and that secret is the only thing between a stranger and your LLM bill. Agora echoes
it back as `Authorization: Bearer`; requests without it get a 401.

`.env` is gitignored and holds live credentials — keep it that way. The EspoCRM passwords in
`crm/docker-compose.yml` are deliberately hardcoded demo values for a container bound to
localhost; they are not secrets and are not reused anywhere.

---

## Tests

```bash
cd backend && python -m pytest
```

121 tests, ~8s, zero network calls. `conftest.py` blanks the env file so the suite never reads
real credentials or touches disk, and the EspoCRM adapter is tested against
`httpx.MockTransport` — it never needs Docker running.

---

## Project layout

| Path | What |
|---|---|
| `backend/app/orchestrator/pipeline.py` | The turn loop; `run_turn_stream` is the production path |
| `backend/app/orchestrator/bridge_lines.py` | "Let me pull that up", chosen by which tool fired |
| `backend/app/tools/prompts.py` | Persona and speech markup — behaviour lives here, not in code |
| `backend/app/tools/definitions.py` | The eight tool schemas |
| `backend/app/agora/join_payload.py` | ASR/TTS/LLM/VAD config sent to Agora on `/join` |
| `backend/app/crm/espo_client.py` | EspoCRM REST client — auth, filters, datetime formats |
| `backend/app/crm/espo_store.py` | Leads |
| `backend/app/calendar/espo_store.py` | Meetings, with availability derived from real bookings |
| `backend/app/notify/ics.py` | The `.ics` invite - folding, escaping, `METHOD:REQUEST` |
| `backend/app/notify/mailer.py` | SMTP delivery and the MIME shape mail clients need |
| `backend/app/notify/service.py` | Both send hooks, and the once-only guard across them |
| `crm/docker-compose.yml` | EspoCRM + MariaDB + websocket + daemon |
| `scripts/provision_crm.py` | Headless CRM setup |
| `frontend/lib/agoraClient.ts` | RTC + RTM join/teardown, transcript handling |

---

## Troubleshooting

**She says "let me get a specialist to help you" every turn.** That line is not the model — it
is `failure_message` in the Agora join payload, spoken when the webhook times out, errors, or
returns something invalid. Check the backend log; do not edit the prompt.

**Replies sound right but the local log shows no `/chat/completions`.** `PUBLIC_BASE_URL` is
pointing at someone else's tunnel, or a dead one. Compare `/api/leads` between the tunnel and
localhost.

**The CRM is not updating.** Confirm `CRM_BACKEND=espocrm` and that the backend was restarted
*after* `.env` changed. If the page only updates on refresh, the `espocrm-websocket` container
is down — a plain HTTP GET to `:8081` returning **426 Upgrade Required** means it is healthy.

**Docker: "LEGACY INSTALLATION METHOD DETECTED", then 500 "No database params in config".**
Something is mounting `/var/www/html` as a whole volume. Only `data`, `custom` and
`client/custom` may be mounted. Most compose snippets online still show the old way.

**A field holds no value even though the write returned 200.** EspoCRM prefixes custom fields
with `c` — a field created as `ariaUserCount` must be written as `cAriaUserCount`. The
unprefixed name is accepted and discarded.

**Nothing is heard at all.** Check the microphone: a virtual-audio-cable device can appear
under a name that looks like your real mic. Pick the actual hardware input.
