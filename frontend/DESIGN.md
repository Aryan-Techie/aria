# Design system — Aria Call Console

<!-- impeccable:design-schema 1 -->
<!-- Authored directly from the built result (not by the native impeccable-documenter
     subagent — unavailable in this mid-session skill install; disclosed per the
     skill's own substitution rule). -->

## World

A recording-studio mixing console. The call is a live session; every action Aria
takes prints onto a session timeline like an automation move on a DAW track.
Single-theme, dark-only, by deliberate choice — a mixing desk is a dim-room
instrument, and this console is used screen-shared during demos.

Direction: impeccable concept-seed, scope `direction`, mode `operate`, seed key
`57721061`, assigned index 3 of 7 grounded candidates. Raised by two declined
catalog challengers: depth/prominence as a state signal, and physical-feeling
digit readouts for numeric fields.

## Color

One commanded accent only — everything else is neutral or semantic.

| Token | Value | Use |
|---|---|---|
| `--chassis` | `#17130f` | page ground — warm near-black console body |
| `--chassis-raised` | `#211b15` | rail panel surfaces |
| `--chassis-inset` | `#100d0a` | recessed instrument wells (readouts, track, patch cells) |
| `--edge` | `#3a3128` | hairline separators |
| `--text` | `#f3ece1` | primary ivory (console backlighting) |
| `--text-dim` | `#a89a86` | secondary text |
| `--text-faint` | `#8f8067` | tertiary/placeholder text — tuned to 5:1+ against both chassis and inset surfaces |
| `--live` | `#ff3b2f` | the one accent — on-air/rec red. All live/primary-action meaning lives here. |
| `--meter-green` / `-dim` | `#5fd964` / `#4a8058` | VU-meter healthy zone (dim = resting/idle state, tuned to 4:1+, not decorative-invisible) |
| `--meter-amber` | `#f0a83c` | VU-meter caution zone |
| `--meter-red` | `#ff3b2f` | VU-meter clip zone — same value as `--live`, deliberately: live and clipping/alarm share one real-world red |

Never introduce a second saturated accent. New semantic states reuse the green/amber/red zone vocabulary already established by the alarm meter.

## Type

- **Archivo** — all UI text: labels, body, headings. A workhorse grotesque, not a trend face; chosen for its genuine condensed/expanded family (channel-strip lettering).
- **JetBrains Mono** — strictly digits, timestamps, and instrument readouts (elapsed timer, patch-bay values, event timestamps). Never used as a "technical" costume on prose.

Panel labels: 10px, weight 700, `letter-spacing: 0.1em–0.12em`, uppercase, `--text-faint`. Never floated above a heading as a kicker/eyebrow — that pattern is banned outright in this system, not just avoided.

## Components

- **`.lamp` / `.lamp-housing`** — the LIVE indicator. Off-state is `--live-dim`, not gray — a red lamp is red glass whether lit or not. `on` adds glow + a slow pulse (disabled under `prefers-reduced-motion`).
- **`.readout`** — an inset instrument well with a large mono value + a small caps label below. Used for elapsed time and the resolved outcome.
- **`.switch`** — transport buttons. Hardware-styled (inset/outset shadow on press), never a flat SaaS button. `.switch.live` is the sole place a button carries the accent border.
- **`.track` / `.event`** — the session timeline. A vertically-scrolling instrument well with a repeating vertical-rule background (tape/reel texture). Each event prints in with a one-shot flash-to-transparent keyframe (`print-in`), never a slide/fade template repeated identically everywhere.
- **`.patch-cell`** — qualification fields as instrument tiles, 2-column grid. Explicitly not a card grid: no icon, no nested shadow-card look, flat inset wells only.
- **`.alarm`** — the escalation channel. A 12-segment meter bar (green → amber → red zones) that's visibly present at rest and clips fully red when `tripped`.

## Refused (do not reintroduce)

No cards-as-page-structure, no kicker/eyebrow above headings, no gradient text, no colored `border-left` accents, no emoji/unicode standing in for icons, no rounded-corner soft-shadow tiles. `border-radius` is capped at `3px` (`--radius`) everywhere — this is a hardware panel, not a consumer app.

## Verified

- `npx tsc --noEmit` clean; `next build` clean.
- Contrast checked by computation, not eye: `--text-faint` on both chassis surfaces ≥4.8:1, `--meter-green-dim` resting baseline ≥4:1 (an earlier pass at `#6b5f4f`/`#1c3020` measured 3.11:1 and 1.38:1 respectively — both fixed before shipping).
- `node scripts/detect.mjs` (impeccable's 59-rule anti-pattern scanner): zero findings.
- Desktop (1440×900) and mobile (390×844) screenshots inspected; mobile collapses the three-rail desk into a stacked column with the transport rail as a wrapping top bar.
- Real interaction tested: Start Call → connecting → clean error surfaced in the timeline (`Failed to start call: 500`, expected with no Agora credentials configured) → reverts to standby. No silent failure.

## Open / substituted

No native `impeccable-finish-reviewer` subjective critique pass ran — the subagent isn't registered in this session (the skill was installed mid-session, not at harness start). The mechanical detector, contrast computation, and manual desktop/mobile inspection above stand in for it.
