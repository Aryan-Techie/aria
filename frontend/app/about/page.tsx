import type { Metadata } from "next";
import { Logo } from "@/components/Logo";
import { StoryOrb } from "@/components/StoryOrb";
import {
  GeminiMark,
  DeepgramMark,
  MiniMaxMark,
  NextJsMark,
  FastApiMark,
  DockerMark,
  OracleMark,
  CaddyMark,
  ExpoMark,
} from "@/components/BrandMarks";

export const metadata: Metadata = {
  title: "Aria — a voice AI that sells like a person",
  description:
    "A real-time voice sales agent built on Agora's Conversational AI Engine — she negotiates, updates a real CRM mid-call, and knows when to bring in a human.",
};

const AGORA_LOGO = "/agora-logo.png";
const ESPOCRM_LOGO = "/espocrm-logo.svg";

export default function AboutPage() {
  return (
    <div className="app story-page">
      <header className="top">
        <div className="brand">
          <Logo size={24} />
          <span>Aria</span>
          <span className="sub">Story</span>
        </div>
        <div className="actions">
          <a href="/" className="ghost">
            Open console
          </a>
        </div>
      </header>

      <main>
        {/* ---------- hero ---------- */}
        <section className="story-hero">
          <div className="story-orb-wrap">
            <StoryOrb />
          </div>
          <div className="story-badge">
            <span>Powered by</span>
            <img src={AGORA_LOGO} alt="Agora" />
          </div>
          <h1 className="headline">She doesn&apos;t wait for you to finish.</h1>
          <p className="story-sub">
            A real-time voice sales agent, built on Agora&apos;s Conversational AI Engine. Interrupt
            her mid-sentence and she stops instantly — that&apos;s Agora&apos;s own barge-in detection,
            native to the call, not something scripted after the fact.
          </p>
          <div className="story-cta-row">
            <a href="/" className="primary">
              Talk to Aria
            </a>
            <a href="#brain" className="ghost">
              See how she thinks
            </a>
          </div>
        </section>

        {/* ---------- the problem ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">The problem</p>
            <h2>Scripts break the moment a real customer shows up.</h2>
            <p>
              A scripted voice bot holds together right up until someone interrupts mid-sentence,
              changes a number they already gave, or asks something out of order — then it restarts
              the flow, or hands off blind. A real salesperson doesn&apos;t do that. They listen, adapt,
              and keep the thread. That&apos;s the gap Aria is built for.
            </p>
          </div>
        </section>

        {/* ---------- powered by agora ---------- */}
        <section className="story-section" id="agora">
          <div className="story-agora-lockup">
            <p className="story-eyebrow" style={{ margin: 0 }}>
              Powered by
            </p>
            <img src={AGORA_LOGO} alt="Agora" />
            <h2 style={{ margin: 0, fontSize: 27, fontWeight: 600, letterSpacing: "-0.02em" }}>
              Agora is the phone system. This backend is the person.
            </h2>
            <p>
              Every hard problem in real-time voice — hearing the customer, catching the exact
              instant they start talking over Aria, turning her reply into speech that sounds
              spoken rather than read — is Agora&apos;s Conversational AI Engine, not code this team
              wrote. Under <code>credential_mode: managed</code>, Agora holds the real Deepgram and
              MiniMax connections and injects its own vendor keys server-side, so this team never
              opened a separate speech-to-text or text-to-speech account at all — it&apos;s bundled
              straight into what they already pay Agora.
            </p>
          </div>
          <div className="story-pill-row" style={{ marginTop: 28 }}>
            <span className="pill info">Streaming ASR — Deepgram</span>
            <span className="pill info">Streaming TTS — MiniMax</span>
            <span className="pill info">Native barge-in</span>
            <span className="pill info">Turn-taking &amp; VAD</span>
            <span className="pill info">Managed vendor credentials</span>
            <span className="pill info">Runtime voice switching</span>
          </div>
          <p className="story-callout">
            And Agora calls <strong>us</strong> — not the other way around. Once
            per turn, at a URL minted per session, shaped exactly like an OpenAI chat completion.
            Agora never sees the sales conversation happening inside it; it just carries the call.
          </p>
        </section>

        {/* ---------- built with ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Built with</p>
            <h2>Real vendors, wired in — not simulated.</h2>
            <p>Everything below is actually running, not a slide of logos.</p>
          </div>
          <div className="story-pill-row" style={{ maxWidth: 700 }}>
            <span className="pill info">
              <GeminiMark size={14} /> Gemini
            </span>
            <span className="pill info">
              <DeepgramMark size={14} /> Deepgram
            </span>
            <span className="pill info">
              <MiniMaxMark size={14} /> MiniMax
            </span>
            <span className="pill info">
              <img src={ESPOCRM_LOGO} alt="" height={13} />
              EspoCRM
            </span>
            <span className="pill info">
              <NextJsMark size={14} /> Next.js
            </span>
            <span className="pill info">
              <FastApiMark size={14} /> FastAPI
            </span>
            <span className="pill info">
              <DockerMark size={14} /> Docker
            </span>
            <span className="pill info">
              <OracleMark size={14} /> Oracle Cloud
            </span>
            <span className="pill info">
              <CaddyMark size={14} /> Caddy
            </span>
            <span className="pill info">
              <ExpoMark size={14} /> Expo
            </span>
          </div>
          <p className="story-note">
            Provider-agnostic where it counts: the reasoning loop runs on Gemini today, with Groq
            and Anthropic wired in as real, benchmarked, swappable alternates — see{" "}
            <a href="#brain" className="strong">
              the brain
            </a>
            .
          </p>
        </section>

        {/* ---------- the brain we built ---------- */}
        <section className="story-section" id="brain">
          <div className="story-section-head">
            <p className="story-eyebrow">The brain</p>
            <h2>Ten tools, one decision at a time.</h2>
            <p>
              What Agora hands us each turn is a transcript. What we do with it is the actual
              product.
            </p>
          </div>
          <div className="story-grid">
            <div className="card">
              <h3>Not a decision tree</h3>
              <p>
                Every turn, a tool-calling loop decides — live — whether to search the product
                knowledge base, update the lead, check the calendar, log an objection, or hand off
                to a human: <code>search_pricing_rag</code>, <code>crm_upsert_lead</code>,{" "}
                <code>calendar_book_meeting</code>, <code>negotiate_deal</code>,{" "}
                <code>escalate_to_human</code>, and five more.
              </p>
            </div>
            <div className="card">
              <h3>Three layers of negotiation</h3>
              <p>
                A discount request is the most ordinary thing on a sales call, and the most
                dangerous thing to hand an LLM outright. Aria can concede 3% herself, instantly. Past
                that, a separate deal-desk agent can go to 10% — only against a real commitment. Past
                that, a human is asked, without ending the call.
              </p>
            </div>
            <div className="card">
              <h3>The clamp is code, not a prompt</h3>
              <p>
                An 18% walk-away floor is enforced in <code>engine.authorise</code>, deterministically.
                Feed the desk a 40% recommendation and what comes back out is a capped offer, a
                <code>clamped</code> flag, and a reason — every round written to the CRM as an audit
                line.
              </p>
            </div>
            <div className="card">
              <h3>Grounded, not guessed</h3>
              <p>
                Every price, spec, and comparison Aria states comes from a live knowledge-base
                search — she says she&apos;s not sure rather than invent a number. A technical question
                goes to a second specialist agent that is required to state exactly what it{" "}
                <em>doesn&apos;t</em> know, not just what it does.
              </p>
            </div>
            <div className="card">
              <h3>Benchmarked, not vendor-locked</h3>
              <p>
                The model behind the tool-calling loop is provider-agnostic on purpose — Groq,
                Anthropic, and Gemini all plug into the same interface. Which one serves a turn is
                picked by running real candidates against the real system prompt and the real tool
                schemas, and checking whether a fast model still made the right tool call, not just
                how fast it replied.
              </p>
            </div>
          </div>
        </section>

        {/* ---------- how it's shaped ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Architecture</p>
            <h2>Three layers. Agora owns the first two.</h2>
            <p>
              Not a diagram of ambition — this is the actual request path a single turn takes,
              start to finish.
            </p>
          </div>

          <div className="story-flow">
            <p className="story-flow-label">1. Caller ↔ Agora</p>
            <div className="story-flow-row">
              <span className="story-flow-node">🎙️ Caller&apos;s mic &amp; speaker</span>
              <span className="story-flow-arrow">⇄</span>
              <span className="story-flow-node">
                <img src={AGORA_LOGO} alt="" /> RTC audio + RTM signaling
              </span>
            </div>

            <div className="story-flow-connector">↓</div>

            <p className="story-flow-label">2. Agora ↔ backend</p>
            <div className="story-flow-row">
              <span className="story-flow-node">
                <img src={AGORA_LOGO} alt="" /> Conversational AI Engine
              </span>
              <span className="story-flow-arrow">→</span>
              <span className="story-flow-node">
                <code>POST /api/llm/…</code> — one call per turn
              </span>
            </div>

            <div className="story-flow-connector">↓</div>

            <p className="story-flow-label">3. Backend fan-out</p>
            <div className="story-flow-row">
              <span className="story-flow-node">
                <FastApiMark size={13} /> Tool-calling loop
              </span>
              <span className="story-flow-arrow">⇉</span>
              <span className="story-flow-node">EspoCRM</span>
              <span className="story-flow-node">Calendar</span>
              <span className="story-flow-node">RAG catalog</span>
              <span className="story-flow-node">Deal desk</span>
              <span className="story-flow-node">Slack handoff</span>
              <span className="story-flow-node" style={{ opacity: 0.55 }}>
                mem0 (off)
              </span>
            </div>
          </div>

          <p className="story-callout">
            Every hard real-time problem — hearing the caller, catching barge-in, speaking back —
            stays inside rows 1 and 2, on Agora&apos;s infrastructure. Row 3 is the only part this
            team wrote: one tool-calling loop instead of a rigid flow chart, so a call can take any
            order a real conversation takes. Why that loop and not a script, and why the negotiation
            clamp underneath it is code rather than a prompt — see{" "}
            <a href="#brain" className="strong">
              the brain
            </a>
            .
          </p>
        </section>

        {/* ---------- she adapts to you ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Multilingual &amp; memory</p>
            <h2>One call, and she never stops noticing.</h2>
          </div>
          <div className="story-grid">
            <div className="card">
              <h3>Hindi, English, or both mid-sentence</h3>
              <p>
                One setting and Aria takes the call in Hinglish — Deepgram&apos;s <code>multi</code>{" "}
                ASR mode and MiniMax&apos;s <code>language_boost: auto</code> follow a buyer who
                switches languages mid-thought. Hindi renders in Devanagari, never romanised —
                &ldquo;ek second&rdquo; spelled in Latin letters gets read out as English words.
              </p>
            </div>
            <div className="card">
              <h3>A different voice, because a different agent answered</h3>
              <p>
                When the deal desk or the solutions engineer genuinely takes a question, the
                customer hears a different voice — because a different agent actually did answer.
                Both run on Agora&apos;s own runtime <code>update</code> endpoint, dispatched in the
                background so it never blocks a reply.
              </p>
            </div>
            <div className="card">
              <h3>Memory without a memory service</h3>
              <p>
                Change a number twenty turns into the call and she doesn&apos;t ask again — the
                qualification record a tool wrote earlier is re-rendered into her system prompt
                every turn, at zero network cost. That&apos;s what carries every call today. A
                longer-range layer, built on mem0 with Voyage AI embeddings, is coded and tested
                for recalling detail beyond that window — currently switched off pending a
                provider-SDK compatibility fix.
              </p>
            </div>
          </div>
        </section>

        {/* ---------- it's real ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Not a mock</p>
            <h2>The CRM updates while she&apos;s still talking.</h2>
          </div>
          <div className="list agreed" style={{ maxWidth: 680, margin: "0 auto" }}>
            <ul>
              <li>
                A customer corrects 25 devices to 50 mid-call, and it&apos;s the same Lead record with
                one field overwritten — not a second lead, not a restart.
              </li>
              <li>
                Booking a meeting writes a real Meeting in EspoCRM and sends a real{" "}
                <code>.ics</code> calendar invite over SMTP — accept it and it lands in the
                customer&apos;s actual calendar.
              </li>
              <li>
                A handoff posts a real Slack message with an AI-written brief — issue, blocker,
                sentiment, recommended action — not a row in a table nobody opens.
              </li>
              <li>
                <ExpoMark size={13} /> A rep can take an escalation on a real mobile app — a linked
                EAS project, not a placeholder — and join the live call from their phone.
              </li>
            </ul>
          </div>
        </section>

        {/* ---------- it scales ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Proven, not claimed</p>
            <h2>256 concurrent calls. Zero failed turns.</h2>
          </div>
          <div className="stats" style={{ maxWidth: 680, margin: "0 auto 18px" }}>
            <div className="stat">
              <div className="k">Concurrent calls</div>
              <div className="v">256</div>
            </div>
            <div className="stat">
              <div className="k">Turns handled</div>
              <div className="v">
                1,536 <small>in 1.91s</small>
              </div>
            </div>
            <div className="stat">
              <div className="k">p95 latency</div>
              <div className="v">0.30s</div>
            </div>
            <div className="stat">
              <div className="k">Failed turns</div>
              <div className="v">0</div>
            </div>
          </div>
          <p className="story-note" style={{ maxWidth: 680 }}>
            At 512 concurrent calls: <strong>3,072 turns in 6.34s</strong> (485/s), p95 1.04s, still 0
            failed. These numbers come from <code>scripts/capacity_test.py</code> running the real
            six-beat call script — CRM writes, deal-desk consult, RAG search, calendar lookup — through
            the real turn loop. Only the model itself is stubbed. It found a genuine concurrency bug
            on its first serious run, before that bug ever reached a live call.
          </p>
        </section>

        {/* ---------- what she does beyond the call ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Beyond the call</p>
            <h2>The work doesn&apos;t end when she hangs up.</h2>
            <p>
              A call is one turn loop. Everything below is what happens around it — before, during,
              and after — built this same sprint.
            </p>
          </div>
          <div className="story-grid">
            <div className="card">
              <h3>A dashboard for every call, not just this one</h3>
              <p>
                <code>/dashboard</code> lists every lead and session the backend has ever seen,
                live capacity stats, open escalations, and the product catalog — polling the same
                backend every five seconds. Open two tabs, start two calls, and both show up here
                together — proof concurrency is real, not a claim.
              </p>
            </div>
            <div className="card">
              <h3>Buys for one person or a fleet</h3>
              <p>
                Aria reads the phrasing — &ldquo;my team&rdquo; versus &ldquo;I need a new
                phone&rdquo; — and skips the company, role, and headcount questions entirely for a
                solo buyer. Financing, AppleCare+, and trade-in work exactly the same either way.
              </p>
            </div>
            <div className="card">
              <h3>A catalog a rep can extend live</h3>
              <p>
                <code>POST /api/products</code> writes new stock and appends it to the RAG corpus,
                then calls <code>retriever.reset_index()</code>. A product added mid-shift is
                answerable by Aria on the very next question asked — no restart, no redeploy.
              </p>
            </div>
            <div className="card">
              <h3>Reschedule and cancel, not just book</h3>
              <p>
                <code>calendar_reschedule_meeting</code> and <code>calendar_cancel_meeting</code>{" "}
                sit alongside booking. A reschedule is cancel-then-rebook in one step, so two
                callers can never collide on the same slot.
              </p>
            </div>
            <div className="card">
              <h3>When it isn&apos;t ready to be a meeting yet</h3>
              <p>
                <code>schedule_followup</code> writes a real Task into EspoCRM — not a line in a
                transcript — so a rep has something to work later, even when the call ends short of
                a booking.
              </p>
            </div>
            <div className="card">
              <h3>Type it in, she never asks again</h3>
              <p>
                The console&apos;s lead card can edit a field by hand through{" "}
                <code>PATCH /api/session/&#123;id&#125;/lead</code> — the same{" "}
                <code>crm_upsert_lead</code> path the voice tools use. A typed correction is
                indistinguishable from a spoken one.
              </p>
            </div>
            <div className="card">
              <h3>She does the currency math</h3>
              <p>
                ₹, rupees, lakh, crore — Aria recognises all of them, converts at an approximate
                stated rate, and keeps negotiating in USD, since the deal engine and the catalog
                only ever speak one currency.
              </p>
            </div>
            <div className="card">
              <h3>A face, not just a voice</h3>
              <p>
                An optional 3D avatar, built in plain Three.js rather than react-three-fiber — a
                deliberate call for React/Next version compatibility — lip-syncing off the live
                remote audio track via morph targets. Toggled per call; the 2D orb stays the proven
                default.
              </p>
            </div>
          </div>
        </section>

        {/* ---------- we found this by running it ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Engineering, not a demo script</p>
            <h2>Real bugs only a live call could find.</h2>
          </div>
          <div className="list risk" style={{ maxWidth: 680, margin: "0 auto" }}>
            <ul>
              <li>
                A CORS/error-handling bug that turned every backend failure into an opaque browser
                error — invisible until a real call actually hit it.
              </li>
              <li>
                A missing RTM auth token that broke the live event panel in total silence while the
                voice call itself kept working — caught from Agora&apos;s own error code, not a stack
                trace.
              </li>
              <li>
                Agora occasionally sends a turn with an empty transcript slot, which the model API
                flatly rejects — a shape no scripted test conversation would ever produce.
              </li>
            </ul>
          </div>
          <p className="story-note">
            <strong>292 automated tests</strong>, zero network calls, about five seconds — enough to
            change code with confidence between two live calls, not instead of them.
          </p>
        </section>

        {/* ---------- faq ---------- */}
        <section className="story-section">
          <div className="story-section-head">
            <p className="story-eyebrow">Questions</p>
            <h2>Answered straight, same as she would.</h2>
          </div>
          <div className="story-faq">
            <details>
              <summary>Is any of this actually live, or is it a demo build?</summary>
              <p>
                Live. The console, the dashboard, and this page all run against the same real
                backend on a real Oracle Cloud VPS — no mock mode, no scripted call. The&nbsp;
                &ldquo;we found this by running it&rdquo; section above is the honest evidence: bugs a
                scripted demo would never have surfaced.
              </p>
            </details>
            <details>
              <summary>What happens when Aria doesn&apos;t know something?</summary>
              <p>
                She says so. Every price or spec comes from a live knowledge-base search — no
                answer, no guess. Technical questions beyond that go to a specialist agent required
                to state what it doesn&apos;t know, and anything past pricing authority goes to a
                human without ending the call. See{" "}
                <a href="#brain" className="strong">
                  the brain
                </a>
                .
              </p>
            </details>
            <details>
              <summary>Can I use my existing IT/MDM tooling, or does this need new software?</summary>
              <p>
                No new tooling required. Apple Business Manager integrates with Jamf, Kandji, and
                Microsoft Intune, so IT keeps whatever device-management stack it already runs.
              </p>
            </details>
            <details>
              <summary>What if I&apos;m buying one device for myself, not a fleet?</summary>
              <p>
                Aria reads that from how you talk about it and skips the company/headcount
                questions entirely. Financing, AppleCare+, and trade-in credit all work the same
                for one device as for fifty.
              </p>
            </details>
            <details>
              <summary>Is there a security or compliance review before we&apos;d sign anything?</summary>
              <p>
                Yes — that&apos;s a human step by design. Aria can walk through the standard
                documentation on the call, but a formal security/compliance review is routed to a
                specialist rather than closed out by an AI.
              </p>
            </details>
            <details>
              <summary>How is a live call different from a chatbot with a voice bolted on?</summary>
              <p>
                No script tree. Every turn re-decides, live, whether to search pricing, update the
                lead, check the calendar, or negotiate — and Agora&apos;s own barge-in detection
                means interrupting her mid-sentence actually stops her, not queues you.
              </p>
            </details>
          </div>
        </section>

        {/* ---------- closing ---------- */}
        <section className="story-section" style={{ textAlign: "center" }}>
          <h2 style={{ fontSize: 27, fontWeight: 600, letterSpacing: "-0.02em", margin: "0 0 20px" }}>
            Start a call. See what she does with it.
          </h2>
          <div className="story-cta-row">
            <a href="/" className="primary">
              Try the live console
            </a>
          </div>
          <p className="story-fineprint" style={{ marginTop: 18 }}>
            Live on a real Oracle Cloud VPS behind Caddy and real Let&apos;s Encrypt TLS — not a
            laptop and a tunnel.
          </p>
        </section>
      </main>

      <footer className="story-footer">
        <div className="story-footer-links">
          <a href="/">Talk to Aria</a>
          <a href="/dashboard">Dashboard</a>
          <a href="#brain">The brain</a>
          <a href="#agora">Powered by Agora</a>
          <a href="https://github.com/Aryan-Techie/aria" target="_blank" rel="noreferrer">
            GitHub
          </a>
        </div>
        <div className="story-credit">
          <span>Built on</span>
          <img src={AGORA_LOGO} alt="Agora" />
        </div>
        <p className="story-fineprint">Aria — for Agora&apos;s Adaptive AI Sales and Negotiation Agent track.</p>
      </footer>
    </div>
  );
}
