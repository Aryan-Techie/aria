# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Internal operators only — the AR Voice hackathon team (and, by extension, mentors/judges watching over their shoulder). The actual customer/prospect on a call never sees this screen; they only ever hear Aria's voice over the phone. The operator's job here: start a call, watch it unfold live, and see how it resolved.

## Product Purpose

Aria is a real-time voice AI sales agent — an LLM-driven tool-calling loop running on Agora's Conversational AI Engine — that qualifies leads, handles objections, and books meetings over a live call instead of following a fixed script. This surface (`frontend/`) is the operator console for that agent: start/end a call, and watch its live transcript, qualification record, and escalation state as they happen.

## Positioning

Unlike a scripted voice bot, Aria's brain visibly does things mid-call — it searches a knowledge base, updates a structured lead record, logs an objection, checks a calendar, or escalates via deterministic guardrails (not just the model's own judgment). The console's job is to make that process legible in real time — tool calls firing, state changing, an escalation triggering — not to hide it behind a generic "on a call" spinner.

## Operating Context

A live voice call runs between Aria and a customer over Agora RTC. The operator starts the call from this console, which then receives real-time transcript and agent-state events via Agora's RTC/RTM SDKs and the `agora-agent-client-toolkit`, plus our own custom JSON events over the same RTM channel (`qualification_updated`, `tool_call_started`/`finished`, `escalation_triggered`, `call_outcome_set`, `objection_logged`). Ending the call surfaces a resolved outcome: meeting booked, escalated, qualified/disqualified, or follow-up.

Frequently used screen-shared or projected during mentor/judge demos — needs to read clearly at a glance and at a distance, not just up close.

## Capabilities and Constraints

- Backend: FastAPI at `NEXT_PUBLIC_BACKEND_URL` (`.env.local`), exposing `POST /api/call/start`, `POST /api/call/{id}/end`, and read-only admin endpoints (`/api/leads`, `/api/calendar/slots`, `/api/inbox`) with real seeded demo data.
- Agora's RTC/RTM/toolkit SDKs touch `window` at import time and must stay dynamically imported client-side only — statically importing them broke Next.js server prerendering (found and fixed this session).
- No real Agora/Anthropic/Voyage/Slack credentials are configured yet, so a live call cannot currently complete end-to-end. Failure states must be visible and specific, never a silent hang — a CORS bug already caused exactly that once and is now fixed.
- Seeded CRM/calendar data is reachable via the admin endpoints even without a live call, so the console can look populated and real during a demo regardless of credential status.

## Evidence on Hand

- `docs/demo_script.md` — the exact 4-beat scenario (pricing question → competitor interruption → requirement change → booking) this console needs to make trackable turn by turn.
- Backend admin endpoints return real seeded leads/calendar slots — not placeholder/lorem data.
- A separate architecture Artifact already exists for mentor-pitch materials (dark-ink/teal/IBM-Plex system) — explicitly **not** a binding constraint here; this surface's visual world is being decided fresh.

## Product Principles

1. Make the agent's reasoning visible — tool calls, state changes, and escalation triggers are the point of this screen, not chrome around a video-call widget.
2. Operator tool, not a pitch page — scannability and live-state clarity outrank persuasive polish.
3. Never fail silently — every failure state is specific and visible on screen; this has already bitten the team once.
4. Demo-resilient — reads as intentional and informative even before a live call ever connects.
