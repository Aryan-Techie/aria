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
                                      ├─ tool loop (10 tools, max 6 hops)
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

### The ten tools

`search_pricing_rag` · `ask_solutions_engineer` · `crm_upsert_lead` · `crm_qualify_lead` ·
`calendar_check_availability` · `calendar_book_meeting` · `negotiate_deal` ·
`escalate_to_human` · `log_objection` · `update_sentiment`

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

## She bargains, and she is not allowed to give the deal away

A buyer asking for a discount is the most ordinary thing on a sales call, and it is also
where an LLM is at its most dangerous: it will happily agree to forty percent because
agreeing is what makes the sentence flow. So the negotiation runs on three layers, and the
model is not the last thing standing between a customer and the margin.

**Layer 1 - Aria.** She can say yes to 3% on her own, instantly. Anything past that she does
not decide. Ask for a discount, name a target price, or wave a competitor's quote and she
calls `negotiate_deal` rather than answering.

**Layer 2 - two specialists, not one helper.** Each is a genuinely separate agent: its own
system prompt, its own model call, its own view of the call, and no ability to speak to the
customer at all.

*The deal desk* (`app/deal/desk.py`) reasons about margin, which is a different job from
holding a conversation - asking one prompt to do both is how you get an agent that is either a
pushover on price or a robot to talk to. It can sign up to 10%, and only ever against a
commitment.

*The solutions engineer* (`app/specialists/solutions.py`) takes the technical questions - 
compatibility, migration, MDM, rollout - that four sales documents cannot settle. Before it
existed those left two honest options, guess or fetch a person, and fetching a person ends the
call. It answers only from what the retriever can find and is required to state precisely what
it does **not** know, as a specific open question rather than a vague caveat. "That should be
fine" about software compatibility is a promise found out months later during a deployment.
When a weak search comes back, the tool result itself points the model here rather than at a
human - and when the engineer says the material genuinely does not cover it, the resulting
handoff is a better one, because the person arrives knowing exactly which question is open.

**Layer 3 - a human.** Past the desk's ceiling, a person is asked - *without ending the call*.
A question about margin is not a handoff, so the customer stays with Aria while a manager
answers one question. `POST /api/inbox/{id}/approve` writes their figure onto the live
session, the next system prompt renders it, and she can lead her next sentence with a number
a human signed seconds earlier.

**The desk proposes; code decides.** `engine.authorise` is the clamp, and it is where the
guarantees actually live rather than in prompt text:

| Rule | Why |
|---|---|
| Nothing past the 18% walk-away floor, ever | Deterministic. The desk is not consulted, because this is the one number a generation must not talk the business past |
| Above 10% holds the offer at 10% and asks a human | She offers what she *is* authorised for immediately and says the rest is with her manager - never that it is agreed |
| Discounts above 3% need a commitment attached | A concession given for nothing teaches the buyer that waiting is free |
| Each round moves less than the last (5%, +3%, +1.8%...) | A negotiator who moves five, then five, then five has taught them to keep pushing |
| A discount is never clawed back | Someone who heard 8% never hears 7% later, whatever the desk proposes next |

A desk that recommends 40% is a generation away, not a hypothesis, so that is exactly what the
tests feed in - and what comes out is a capped offer, a `clamped` flag and a reason. Every
round is written to the CRM as an audit line: what was asked, what was granted, which layer
authorised it, and what was demanded in return.

**Arithmetic is not left to the model** - the same call as the calendar labels. `negotiate_deal`
returns a finished `price_summary` ("60 x MacBook Air (M3). List $59,940... that is $902 a
device, $54,145 for the fleet") and the prompt says to read it, not recompute it. A wrong price
said to a buyer is unrecoverable in a way a wrong weekday is not.

**The pause is honest.** The desk sits on the turn path, so the bridge line covering it is
"let me see what I can do on that" - which is what a rep says while checking with their
manager, because that is exactly what is happening.

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

## Every call ends with a human being told

Not only the escalations. A qualified lead nobody was told about is the same as no lead, so
`end_call` builds a wrap-up and delivers it - `app/handoff/`.

It is deliberately not the escalation brief. That one answers *why am I being pulled into a
live call*; this answers *what happened on a call I was not on, and what do I do about it*:
a headline, one recommended action with an urgency, then what they need, **what was already
agreed** (the discount that stands, the quote she read out, the commitments they were asked
for), what we owe them, and what to watch out for.

**The model writes two sentences and nothing else.** The headline and the next action are
generated; every fact under them is read off the records the tools wrote during the call. A
summariser handed a raw transcript will confidently produce a detail nobody said, and a rep
who opens a call with an invented detail is worse off than a rep with a thin summary. If the
model call fails, `heuristic_summary` writes both sentences off the call outcome and the
wrap-up still goes out.

**Three delivery routes, in decreasing order of setup.** The **CRM record** always, with no
configuration at all - it is where the rep already is, and a summary that needs a Slack
workspace to exist does not exist on a fresh machine. **Slack** when a webhook is set, because
that is the one that arrives while the lead is still worth calling back. **Email** to
`REP_SUMMARY_EMAIL` when SMTP is configured. Each is independent and best-effort: a Slack
outage does not cost the CRM note, and `deliver()` returns which routes actually took it, so
"the rep was told" is checkable rather than assumed.

Readable at `GET /api/summaries` and `GET /api/summaries/{session_id}`.

---

## How many conversations at once

The question a buyer actually asks is not "does it work" - it is "how many of these run at
the same time, and how many people do I still need". `scripts/capacity_test.py` answers it by
running the load rather than estimating it, and `GET /api/metrics/capacity` reports what
really happened.

```
python scripts/capacity_test.py --sessions 256 --turns 6
256 concurrent calls, 1536 turns in 1.91s (804/s), p95 0.30s, 0 failed

python scripts/capacity_test.py --sessions 512 --turns 6
512 concurrent calls, 3072 turns in 6.34s (485/s), p95 1.04s, 0 failed
```

Each simulated call runs the real six-beat script - price question, objection, requirement
change, two discount pushes, booking - through the real `run_turn_stream`, so the CRM writes,
the deal desk consult, the RAG search and the calendar lookup all genuinely execute. Only the
model is stubbed.

**Which is exactly what the number means, and nothing more.** `--mode pipeline` says our code
holds 512 conversations without dropping a turn. It does not say a Groq free tier will serve
512; a turn spends most of its life inside the provider, so end to end the ceiling is their
rate limit, not ours. `--mode live` measures that against a running backend. Quote both or
neither.

**It found a real bug on its first serious run.** At 256 concurrent calls a handful of turns
died with `dictionary changed size during iteration`: the in-memory stores walk their own dict
to build a persistence snapshot, and another live call's `save()` was inserting into it
mid-walk. Every call is its own thread - Agora calls the webhook once per turn per call - so
this was always reachable and simply needed enough calls at once to be hit. The stores are
lock-guarded now, and `tests/test_capacity.py` hammers each one from two threads as a
regression guard.

`/api/metrics/capacity` reports peak concurrency **computed** as the maximum overlap across
every session's start and end (not "calls today", which is how this number usually gets
inflated), containment - with an escalated call counting *against* the agent, since a call
that needed a person is not a call it handled - talk time and post-call admin kept apart
rather than summed into one flattering figure, and rep-days saved. Every assumption behind
the derived figures is returned in the same payload, because a number whose assumptions are
hidden is one a judge is right to distrust. See `app/metrics/savings.py` for the per-action
baselines; repeated data entry counts once, and an escalation counts zero.

---

## She can take the call in Hindi

`AGENT_LANGUAGE=hinglish` (or `hi`, or `en`). One setting, because language is
not one setting - it is five things that have to agree, and any one of them left on its
English default is enough to break the call on its own:

| | Why it cannot be left alone |
|---|---|
| Deepgram's language code | Hindi audio transcribed as English comes back as nonsense, and the model answers the nonsense |
| The MiniMax voice id | Voices are language-specific. `English_captivating_female1` reading Devanagari is not accented Hindi, it is unusable |
| MiniMax `language_boost` | Unset, a Hindi voice still mispronounces the English product names in the same sentence |
| The system prompt | She answers an English-transcribed question in English, because English is what the rest of her instructions are written in |
| The greeting, failure line and bridge lines | **We** write these, not the model, so they stay English until translated. A Hindi call that says "let me pull that up for you" mid-turn tells the caller the Hindi was a veneer |

So it is a profile, in `app/language/profiles.py`, and the five move together.

**`hinglish` is the one you probably want.** A buyer discussing a device fleet switches
between Hindi and English inside a single sentence, and a recogniser pinned to either one
mangles the other half. That profile uses Deepgram's `multi` mode (English, Hindi and eight
others) with MiniMax's `language_boost: auto`, and the prompt tells her to match whichever
language the caller just used - Hindi for the conversation, English for product names,
numbers and dates, which is how the call is actually held in an Indian office.

**Devanagari, never romanised.** MiniMax's Hindi voices are trained on the script; "ek
second" in Latin letters is read out as English words.

**Pre-formatted strings stay English on purpose.** Slot labels and price summaries are built
in code precisely so the model never does arithmetic on them, and the prompt says to speak
them exactly as handed over. Translating a date back into Devanagari would undo the fix that
stopped her calling a Monday "Sunday the seventh".

### The bug this uncovered

`language` was being sent as a **sibling** of `asr.params`, not inside it. Agora silently
drops properties it does not recognise, so the setting never reached Deepgram and the
recogniser ran on its own English default whatever `ASR_LANGUAGE` said. That is where "sorry,
English only" came from - not a vendor limitation, and not something setting a language code
would have fixed. It is now in `asr.params.language`, with a regression test asserting it is
*not* a sibling.

### Before you switch

An existing `.env` from when this only spoke English pins `ASR_LANGUAGE=en` and
`MINIMAX_VOICE_ID=English_captivating_female1`, and those override the profile - so
`AGENT_LANGUAGE=hi` would switch the prompt and the greeting while the recogniser and the
voice stayed English. **Blank both lines.** They are legitimate overrides otherwise (pinning
`hi` over `multi`, or `hindi_male_1_v2` over the female voice), so they are kept - but the
backend logs a warning naming the exact line whenever a pin is fighting the profile, because
a call that half-switches is far worse to debug than one that does not switch at all.

### What is not translated

The confirmation email, the `.ics` invite and the end-of-call wrap-up are English. Business
email in India is usually English so this is a deliberate boundary rather than an oversight,
but it is a boundary: a fully Hindi call still produces an English invite.

### Not yet confirmed on a live call

Vendor support is documented, not measured. Deepgram lists Hindi and `multi` for nova-3;
MiniMax publishes three Hindi voices and the `language_boost` parameter; Agora states it
forwards parameters it does not validate straight to the vendor, which is what lets
`language_boost` through. But this account has already had one (vendor, model) combination
refused for its SKU under managed credentials, so a Hindi voice being available to *us*
is a reasonable expectation and not a fact. Place one call before demoing it.

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
| `REP_SUMMARY_EMAIL` | Where the end-of-call wrap-up is emailed. Blank still writes it to the CRM |
| `AGENT_LANGUAGE` | `en`, `hi`, or `hinglish`. Sets ASR, voice, boost, greeting and prompt together |
| `MINIMAX_EMOTION` | `fluent` reads conversational; `happy` sounds like a chirpy IVR |
| `FILLER_WORDS_ENABLED` | Agora's own stall phrases. Off — see Design notes |
| `STATE_DIR` | JSON snapshots for the in-memory stores; blank = pure memory |

### Debug endpoints

`GET /healthz` · `GET /api/leads` · `GET /api/calendar/slots` · `GET /api/inbox` ·
`GET /api/session/{id}/events` · `POST /api/inbox/{id}/approve` · `GET /api/summaries` · `GET /api/metrics/capacity`

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

211 tests, ~9s, zero network calls. `conftest.py` blanks the env file so the suite never reads
real credentials or touches disk, and the EspoCRM adapter is tested against
`httpx.MockTransport` — it never needs Docker running.

---

## Project layout

| Path | What |
|---|---|
| `backend/app/orchestrator/pipeline.py` | The turn loop; `run_turn_stream` is the production path |
| `backend/app/deal/policy.py` | The commercial envelope - tiers, authority caps, the walk-away floor |
| `backend/app/deal/engine.py` | Pricing, and `authorise` - the clamp the desk cannot argue with |
| `backend/app/deal/desk.py` | Layer 2: the deal desk agent, its own prompt and its own model call |
| `backend/app/specialists/solutions.py` | Layer 2: the solutions engineer, and what it refuses to claim |
| `backend/app/orchestrator/bridge_lines.py` | "Let me pull that up", chosen by which tool fired |
| `backend/app/tools/prompts.py` | Persona and speech markup — behaviour lives here, not in code |
| `backend/app/tools/definitions.py` | The eight tool schemas |
| `backend/app/agora/join_payload.py` | ASR/TTS/LLM/VAD config sent to Agora on `/join` |
| `backend/app/language/profiles.py` | English / Hindi / Hinglish, and the five settings that must agree |
| `backend/app/crm/espo_client.py` | EspoCRM REST client — auth, filters, datetime formats |
| `backend/app/crm/espo_store.py` | Leads |
| `backend/app/calendar/espo_store.py` | Meetings, with availability derived from real bookings |
| `backend/app/notify/ics.py` | The `.ics` invite - folding, escaping, `METHOD:REQUEST` |
| `backend/app/notify/mailer.py` | SMTP delivery and the MIME shape mail clients need |
| `backend/app/notify/service.py` | Both send hooks, and the once-only guard across them |
| `backend/app/handoff/builder.py` | The end-of-call wrap-up; facts off the record, two sentences from the model |
| `backend/app/handoff/delivery.py` | CRM note, Slack, email - independent and best-effort |
| `backend/app/metrics/savings.py` | How much human time a call actually took off someone's desk |
| `backend/app/metrics/capacity.py` | Concurrency, containment and the assumptions behind both |
| `scripts/capacity_test.py` | N concurrent calls through the real turn loop |
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
