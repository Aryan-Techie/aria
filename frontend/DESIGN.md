# Design system — Aria Console

## World

A voice, not a dashboard. One orb moves with whoever is speaking; the conversation runs
beneath it; a sheet on the right holds everything Aria knows about the call so far; and
when the call ends the transcript gives way to the brief the rep is sent. Light by
default, dark on request (system preference, then the toggle, remembered in
`localStorage`). Built to be read across a room during a screen-shared demo, and up
close by the operator who has to approve a discount mid-call.

The standalone mock this was ported from lives at `../mock/aria-console.html` and runs a
scripted demo call with no backend.

## Color

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#f5f5f7` | `#000` | page ground |
| `--surface` / `--surface-2` | `#fff` / `#f2f2f4` | `#151517` / `#1f1f22` | cards, chips, tracks |
| `--ink` / `--ink-2` / `--ink-3` | `#1d1d1f` / `#6e6e73` / `#aeaeb2` | `#f5f5f7` / `#98989d` / `#5c5c61` | primary / secondary / tertiary text |
| `--aria` | `#5e5ce6` | `#7d7aff` | Aria's colour: her orb, her turn marker, the deal track |
| `--you` | `#ff9f0a` | `#ffb340` | the customer's colour: their orb, their turn marker |
| `--good` / `--warn` / `--bad` | Apple system green / orange / red | brighter dark variants | outcome, guardrail and sentiment states |

Aria is the cool half of the wheel and the customer the warm half, so who is speaking
reads from the orb alone. Semantic colours never appear as large fills; they tint pills,
dots and borders.

## Type

- System font first (`-apple-system`, SF Pro), **Inter** shipped as the fallback for
  Windows. Body tracking `0`; small caps labels `+0.06em`; headings tighten as they grow
  (`-0.02em` at 22px, `-0.03em` at 26px).
- **Instrument Serif** for exactly one thing: the brief's headline, the one line written
  for a person rather than read off a record. Keep it there and nowhere else.
- Tabular numerals wherever a number can change under the reader (timer, devices,
  percentages, milliseconds).

## Components

- **Orb** (`components/Orb.tsx`) — canvas: three drifting gradient blobs plus a 72-bar
  halo. Amplitude is the real RTC volume of whichever side is speaking
  (`AgoraCallClient.getLevels`), with a small synthetic breath so it is never dead still.
  Palettes cross-fade between idle / Aria / you / thinking / hold / ended.
- **Transcript** — no bubbles. A tiny role label and 17px text. Tool calls print inline
  as pills with their round trip; system moments (approval asked, meeting booked, handoff)
  print as tinted notes in the flow.
- **Sheet cards** — Lead (devices count tweens), Signals (sentiment history bars,
  competitors, objections with attempts), Deal (track with the 3 / 10 / 18 stops from
  `app/deal/policy.py`, round list, approve control), Handoff (the three guardrails from
  `app/escalation/triggers.py` shown with their progress, turns red when one trips),
  Activity (every tool with ms, slow ones amber, running rep-minutes).
- **Brief** — the shape of `CallSummary`. Facts assemble client-side immediately from the
  same records; the serif headline waits for the backend's wrap-up and breathes until it
  lands.
- **Controls** — Start / Mute / Hold / End. Hold has no backend primitive: it mutes the
  mic and stops Aria's audio locally (`setHold`). Feedback is on the press (`:active`
  scale), never only on release.

## Motion

Cross-fades and short rises with `cubic-bezier(.2,.8,.2,1)`; nothing snaps. Layout
transitions (`grid-template-columns`, orb height) run 600ms. `prefers-reduced-motion`
collapses every transition and animation to a cut; `prefers-reduced-transparency`
solidifies the top bar; `prefers-contrast: more` strengthens hairlines and tertiary text.

## Refused

No chat bubbles, no card-per-stat dashboards, no colour used as decoration, no second
serif, no fixed letter-spacing across sizes, no spinner where the data can be shown
instead.
