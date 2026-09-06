# Demo script — three voices, one call, under 3 minutes

**Cast:** You (customer, "Rudra from Microsoft") · Aria (AI, no script) · Shipra (human rep, remote)

**Three levels, no restart:**
1. Aria + deal desk (female voice → second female voice)
2. Solutions engineer (male voice)
3. You get frustrated → Shipra joins from another city, Aria leaves

Timings are targets. Aria's replies are hers; keep yours short so she has room.

---

## Before you start (30s, off-camera)

- Shipra: on headphones, phone unlocked, WhatsApp open, ready for a link.
- You: console open, Espo dashboard in another tab (leads assigned to `aria`).
- Say your lines in Hinglish or English, either works. Keep each line one sentence.

---

## Level 1 — Aria + deal desk (0:00–1:00)

**YOU:** "Hi, I'm Rudra from Microsoft. We need fifty MacBook Airs, budget is around twenty lakh."
> Watch: Lead card fills — Microsoft, 50, 20 lakh. `Updated the lead` pill.

**YOU:** "That's over budget. What's your best price on fifty?"
> Watch: `negotiate_deal` → Deal card shows a round. **Voice changes** — deal desk (second female voice) speaks the offer.

**YOU:** "Okay. Hold that number."

---

## Level 2 — Solutions engineer (1:00–1:40)

**YOU:** "Before I commit — our whole fleet is on Intune. Can these Macs be enrolled in Intune on day one, or do we need Jamf?"
> Watch: `ask_solutions_engineer` pill. **Male voice** answers. HandoffCard still "Aria has it".

**YOU:** "And migrating fifty users' data from Windows — who does that, us or you?"
> Male voice again. Let him finish.

---

## Level 3 — Frustration → Shipra (1:40–2:50)

Two consecutive frustrated turns trip the guardrail. Sound annoyed, not angry. Interrupt her once — barge-in shows.

**YOU (turn 1, cut her off mid-sentence):** "No, stop — you keep giving me general answers. I asked who physically does the migration."
> Watch: Handoff card — Frustration streak 1 of 2.

**YOU (turn 2):** "This isn't working. I don't want another AI answer, I want an actual person who owns this account."
> Watch: Frustration streak 2 of 2 → card goes red, "Waiting for a person". Aria says she's looping in a specialist. **Copy join link for Shipra** button appears.

**YOU (to audience, while copying):** "That link goes to Shipra — she's in [city], on her phone."
> Paste link into WhatsApp. Shipra opens it, sees the brief, taps **Join call**.

> Aria: *"Shipra from our team is on the line now and has the full context. I'll hand you over."* — then leaves. Console: "Shipra has the call · Aria has left".

---

## Shipra's script (2:50 → end, ~40s)

Shipra reads the brief on the join page before tapping Join. Her opening should prove she has context — that's the whole point.

**SHIPRA:** "Hi Rudra, Shipra here from Apple Business. I've got everything — fifty MacBook Airs, twenty lakh budget, and your question is who runs the Windows migration. Right?"

**YOU:** "Yes. Exactly."

**SHIPRA:** "It's us. Our deployment team does the migration on-site, and Intune enrolment works out of the box — no Jamf needed. I'll send you a written plan today."

**YOU:** "And the price Aria's desk quoted?"

**SHIPRA:** "That number stands. I'll put it in the plan with the migration included."

**YOU:** "Good. Send it over."

**SHIPRA:** "Done. You'll have it in an hour. Thanks Rudra."

> End call on console. Show Espo: lead exists, assigned, status escalated, brief in inbox.

---

## If something goes sideways

| Problem | Do this |
|---|---|
| Guardrail doesn't trip after 2 turns | Say: "Get me a human. Now." — Aria calls `escalate_to_human` herself. |
| Deal desk voice doesn't switch | Keep going — the offer still lands; mention voices in wrap-up. |
| Shipra's Join fails | She refreshes the link once. If still failing, you say "Shipra's joining by phone" and continue on speaker. |
| Aria doesn't say the handoff line | She'll still leave after ~5s. Shipra just starts talking. |
| Link 404s "no longer live" | Backend restarted mid-demo. Don't restart during the demo. |

## Total

| Level | Time |
|---|---|
| Deal desk | 1:00 |
| Solutions engineer | 0:40 |
| Frustration + handoff | 1:10 |
| Shipra | 0:40 |
| **Total** | **~3:30 worst case, 2:45 if Aria's replies stay short** |

Cut "Hold that number" and the second solutions question if running long.
