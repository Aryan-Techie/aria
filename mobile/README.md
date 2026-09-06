# Aria Mobile

One Android app, two people.

**The customer** opens it, presses one button, and talks to Aria. **Shipra** — the single
human rep, `handoff_rep_name` in `backend/app/config.py:99` — reaches the same app through
a code at the bottom of Settings, and when Aria escalates she joins the live call by voice.

The backend is unchanged. Every endpoint this app uses already existed for the web console
or for `routes/rep.py`'s own join page.

---

## Running it

You need a device or emulator, and the backend up (`run.bat` at the repo root).

```bash
cd mobile
npm install
npx expo run:android      # builds the dev client and installs it
```

`react-native-agora` is a native module, so **Expo Go will not run this**. The first build
takes a few minutes; after that `npx expo start --dev-client` is enough.

Then, in the app: **Settings → Server**, paste `PUBLIC_BASE_URL` from the repo-root `.env`,
and press *Save and test*. It should say *Backend reachable*.

That address is not baked in on purpose — the cloudflared quick tunnel mints a new hostname
every time `run.bat` runs, and the backend binds `127.0.0.1`, so the phone cannot reach it
any other way. `EXPO_PUBLIC_API_BASE` in `.env` seeds the field if you want a default.

### The APK

```bash
eas build -p android --profile preview
```

`preview` is configured for `buildType: apk` so the result installs directly, no Play
Store, no bundle.

---

## The two paths

**Customer.** Launch → rings, one caption, one button. Press Start and the rings go live:
warm when you speak, cool when Aria does, cyan while a tool is running, grey on hold. The
transcript is not on screen — it peeks from the bottom and you drag it up if you want it.
End the call and the outcome lands immediately, with the written headline a beat later.

**Rep.** Settings → the quiet version line at the very bottom → the code (`4821` unless
`EXPO_PUBLIC_REP_CODE` says otherwise) → *Escalations* appears, and stays until switched
off. While the app is open it polls `/api/inbox` every five seconds; a new handoff buzzes
the phone and puts a banner on the call screen. Tap through, tap Join, and you are on the
call — Aria says her handoff line and leaves about five seconds later.

There is no review step and no approve control. Discounts are settled by Aria's own ceiling
and the deal desk; a person is only ever wanted on the call itself.

---

## How it is put together

```
src/
  app/                   screens (expo-router)
    index.tsx            the call
    settings.tsx         server, appearance, and the way in
    escalations/         the rep's list, and the rep's call
  components/            Rings, Caption, buttons, the transcript sheet
  lib/
    api.ts               typed client — port of frontend/lib/api.ts
    agora.ts             RTC: join, mute, hold, leave, levels
    useSessionPoll.ts    the live call, assembled from the event poll
    useInboxPoll.ts      waiting handoffs
    vocab.ts             the console's words for backend snake_case
  theme/
    tokens.ts            verbatim port of frontend/app/globals.css:16-68
    type.ts              the type scale
```

Three decisions worth knowing before changing anything:

**No RTM.** The console pairs RTC with `agora-rtm-sdk` and the ConvoAI toolkit to receive
transcripts. That toolkit is web-only, and `frontend/lib/api.ts:107-115` already records
that the RTM envelopes were not arriving reliably — the console reads its panels from HTTP
polling. So this app carries voice on RTC and everything else on `useSessionPoll`. The
`rtm_token` from `/api/call/start` is deliberately unused.

**The rings are not the orb.** The console's orb is a canvas render loop — three blurred
gradient blobs and a 72-bar halo — and canvas does not exist in React Native. The rings
keep what the orb communicates (colour is who is speaking, colours cross-fade, amplitude is
real RTC volume with a breath under it) and drop the geometry. Amplitude and speaker
detection both come from Agora's `onAudioVolumeIndication`, which reports local and remote
in one callback.

**The access code is not security.** Every backend endpoint is unauthenticated — knowing an
escalation id is the whole access model, on the web page too. The code keeps the rep screen
out of a customer's way. It does not keep anyone out of the API.

---

## Design

Colours, type scale, radius and easing are ported from the console rather than reinvented,
so the phone and the laptop look like one product on a shared screen. `frontend/DESIGN.md`
is the source of truth; the rules that carry over are: semantic colour only as pill tints,
dots and hairlines, never a large fill; no chat bubbles; tabular numerals on anything that
changes under the reader; feedback on the press, not the release; and no spinner where the
state can be named instead — which is why every wait in this app is a sentence.

Live is red and does not pulse until it is actually live. Amber means connecting. That is
the console's mapping and it is worth not "fixing".
