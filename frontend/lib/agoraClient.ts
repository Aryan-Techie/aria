/**
 * Wraps Agora RTC (audio transport) + RTM (side-channel events) + the
 * Conversational AI client toolkit into one call session.
 *
 * The Agora SDKs touch `window` at module-load time, which breaks Next.js
 * server-side prerendering if imported statically at the top of a "use
 * client" file — Next still evaluates that module graph once during build.
 * All three are dynamically imported inside join(), so nothing resolves
 * until this runs in an actual browser tab.
 *
 * Unverified against a real Agora project in this build (no live credentials
 * available while writing this) — the RTM client construction and the raw
 * custom-event subscription in particular should be checked against current
 * SDK docs (or via Agora Skills / the Agora MCP doc server, per the plan)
 * during the first real test call, per the plan's Step 3 verification note.
 */
import type { IAgoraRTCClient, IMicrophoneAudioTrack } from "agora-rtc-sdk-ng";
import type { StartCallResponse } from "./api";

export interface TranscriptEvent {
  id: string;
  role: "user" | "assistant";
  text: string;
  final?: boolean;
}

/** The toolkit emits NO `role` field on a transcript item (confirmed against
 * `TranscriptHelperItem` in agora-agent-client-toolkit's own typings). Which
 * side spoke is carried two other ways instead:
 *
 *   1. `metadata.object` - the discriminator on the raw message union,
 *      "user.transcription" vs "assistant.transcription". Authoritative.
 *   2. `uid` - the speaker's RTC uid. Ours is the uid we joined with; the
 *      agent publishes under its own. Used when metadata is absent, which it
 *      is for interim chunks (metadata is typed `T | null`).
 *
 * Reading a non-existent `turn.role` is what made EVERY turn fall through to
 * "assistant", so the console labelled the customer's own speech "Aria". */
function normalizeRole(turn: RawTranscriptTurn, localUid: string | null): "user" | "assistant" {
  const object = String(turn.metadata?.object ?? "").toLowerCase();
  if (object.startsWith("user.")) return "user";
  if (object.startsWith("assistant.") || object.startsWith("agent.")) return "assistant";

  if (localUid !== null && turn.uid !== undefined && String(turn.uid) === localUid) return "user";

  // Last resort: some builds may still carry a role-ish string. Keep the
  // permissive alias scan rather than a strict equality check.
  const r = String(turn.role ?? "").toLowerCase();
  if (r.includes("user") || r.includes("customer") || r.includes("caller") || r.includes("human")) return "user";
  return "assistant";
}

/** Aria's spoken text carries MiniMax delivery markup - `<#0.3#>` pause
 * markers and `(breath)` / `(sighs)` / `(laughs)` interjection tags (see
 * SPEECH_STYLE_PROMPT in the backend). The voice engine turns those into
 * audio, but the transcript Agora echoes back still contains them verbatim,
 * so without this the timeline reads "(breath) Okay, let me check that."
 * Strip them for display only - the audio is unaffected. */
function stripSpeechMarkup(text: string): string {
  return text
    .replace(/<#\s*\d+(?:\.\d+)?\s*#>/g, " ")
    .replace(/\((?:breath|breathes|sighs|sigh|laughs|laugh|humming|applause)\)/gi, " ")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([,.!?])/g, "$1")
    .trim();
}

export interface RtmCustomEvent {
  type: string;
  session_id: string;
  ts: string;
  payload: Record<string, unknown>;
}

export interface CallCallbacks {
  /** Called with the FULL current transcript on every update — confirmed
   * live this is a "chat history updated" snapshot, not one new turn per
   * call (timestamps on naively-appended entries came back non-monotonic).
   * Each turn carries a stable `id` (its index) so the caller can upsert
   * in place rather than appending duplicate/fragmented entries. */
  onTranscriptSnapshot?: (turns: TranscriptEvent[]) => void;
  onAgentStateChanged?: (state: string) => void;
  onCustomEvent?: (event: RtmCustomEvent) => void;
  onError?: (error: unknown) => void;
}

/** Shape of one item in a TRANSCRIPT_UPDATED payload. Mirrors the toolkit's
 * `TranscriptHelperItem<Partial<UserTranscription | AgentTranscription>>`,
 * kept loose (all optional) because interim items arrive partially filled. */
interface RawTranscriptTurn {
  uid?: string | number;
  turn_id?: number;
  stream_id?: number;
  text?: string;
  status?: string;
  metadata?: { object?: string } | null;
  /** Not emitted by the current toolkit - retained only for the fallback. */
  role?: string;
  content?: string;
  isFinal?: boolean;
  final?: boolean;
}

export class AgoraCallClient {
  private rtcClient: IAgoraRTCClient | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private rtmClient: any = null;
  private micTrack: IMicrophoneAudioTrack | null = null;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  private api: any = null;
  /** The uid we joined RTC with, so transcript items published under it can
   * be attributed to the customer rather than to Aria. */
  private localUid: string | null = null;

  async join(session: StartCallResponse, callbacks: CallCallbacks): Promise<void> {
    const { app_id: appId, channel_name: channelName, uid, rtc_token: rtcToken, rtm_token: rtmToken } = session;

    const [{ default: AgoraRTC }, AgoraRTMModule, ToolkitModule] = await Promise.all([
      import("agora-rtc-sdk-ng"),
      import("agora-rtm-sdk"),
      import("agora-agent-client-toolkit"),
    ]);
    const { ConversationalAIAPI, EConversationalAIAPIEvents } = ToolkitModule;

    this.localUid = String(uid);

    this.rtcClient = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });

    await this.rtcClient.join(appId, channelName, rtcToken, uid);
    this.micTrack = await AgoraRTC.createMicrophoneAudioTrack();
    await this.rtcClient.publish([this.micTrack]);

    this.rtcClient.on("user-published", async (user, mediaType) => {
      await this.rtcClient!.subscribe(user, mediaType);
      if (mediaType === "audio") {
        user.audioTrack?.play();
      }
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const RTM = (AgoraRTMModule as any).RTM ?? (AgoraRTMModule as any).default;

    // Each `new RTM(...)` allocates another SDK instance ("Ins id is 2/3...")
    // and the SDK logs that at ERROR level, which Next.js surfaces as a red
    // overlay mid-demo. The warning is about two live clients kicking each
    // other off, so the fix is to guarantee the previous one is logged out
    // before allocating the next - see teardown() - and to keep the SDK's own
    // logging out of the overlay. Set NEXT_PUBLIC_RTM_LOG_LEVEL=debug when
    // actually debugging RTM; our own error paths (AGENT_ERROR, the try/catch
    // around login, onError) are unaffected either way.
    if (this.rtmClient) {
      await this.teardown();
    }

    const rtmLogLevel = (process.env.NEXT_PUBLIC_RTM_LOG_LEVEL ?? "none") as
      | "debug"
      | "info"
      | "warn"
      | "error"
      | "none";

    this.rtmClient = new RTM(appId, String(uid), { logLevel: rtmLogLevel });
    await this.rtmClient.login({ token: rtmToken });

    this.api = await ConversationalAIAPI.init({
      rtcEngine: this.rtcClient,
      rtmEngine: this.rtmClient,
      enableLog: true,
    });
    this.api.subscribeMessage(channelName);

    // The toolkit's actual call signature isn't fully documented (confirmed
    // live: a handler written as (agentUserId, event) received `undefined`
    // for `event` — the real call passes a single argument). Confirmed live,
    // separately: treating this as "append only new turns" produced garbled,
    // non-chronological fragments — the timestamps on naively-appended
    // entries came back non-monotonic, meaning this fires repeatedly with
    // interim/evolving snapshots, not one clean new turn per call. Treat the
    // payload as the CURRENT FULL transcript state every time and hand the
    // whole thing to the caller to reconcile (upsert by id), rather than
    // diffing here. Logged to console so the real shape is visible if this
    // still doesn't match.
    this.api.on(EConversationalAIAPIEvents.TRANSCRIPT_UPDATED, (...args: unknown[]) => {
      // eslint-disable-next-line no-console
      console.debug("[Aria] TRANSCRIPT_UPDATED raw args:", args);
      const payload = args[args.length - 1];
      const turns: RawTranscriptTurn[] = Array.isArray(payload)
        ? (payload as RawTranscriptTurn[])
        : payload
          ? [payload as RawTranscriptTurn]
          : [];

      // Key on the speaker + turn, not the array index: both sides carry the
      // same turn_id for one exchange, so uid+turn_id is the natural id and
      // survives the snapshot being reordered or re-emitted.
      const snapshot: TranscriptEvent[] = turns
        .map((turn, i) => ({
          id:
            turn.turn_id !== undefined && turn.uid !== undefined
              ? `${turn.uid}-${turn.turn_id}`
              : `idx-${i}`,
          role: normalizeRole(turn, this.localUid),
          text: stripSpeechMarkup(turn.text ?? turn.content ?? ""),
          final: turn.isFinal ?? turn.final,
        }))
        .filter((t) => t.text);

      callbacks.onTranscriptSnapshot?.(snapshot);
    });

    this.api.on(EConversationalAIAPIEvents.AGENT_STATE_CHANGED, (...args: unknown[]) => {
      // eslint-disable-next-line no-console
      console.debug("[Aria] AGENT_STATE_CHANGED raw args:", args);
      const event = args[args.length - 1] as { state?: string } | undefined;
      callbacks.onAgentStateChanged?.(event?.state ?? "unknown");
    });

    this.api.on(EConversationalAIAPIEvents.AGENT_ERROR, (...args: unknown[]) => {
      // eslint-disable-next-line no-console
      console.debug("[Aria] AGENT_ERROR raw args:", args);
      callbacks.onError?.(args[args.length - 1]);
    });

    // Our own app-level envelope events (qualification_updated, tool_call_started,
    // escalation_triggered, call_outcome_set — see backend app/rtm/publisher.py)
    // ride the same RTM channel as plain JSON messages.
    this.rtmClient.addEventListener?.("message", (event: { message?: string; payload?: string }) => {
      try {
        const raw = event?.message ?? event?.payload ?? "";
        const parsed = JSON.parse(raw) as RtmCustomEvent;
        if (parsed?.type) callbacks.onCustomEvent?.(parsed);
      } catch {
        // not one of our JSON envelopes — ignore
      }
    });
  }

  /**
   * Releases everything, in dependency order, with each step isolated.
   *
   * Previously a single `await` chain: if `rtcClient.leave()` rejected, the
   * RTM logout below it never ran, leaving a logged-in client behind. The
   * next call then created a second live client on the same app - the exact
   * "mutual kick" the SDK warns about. Every step is now independently
   * guarded and the references are always cleared, so a failure mid-teardown
   * still leaves this object safe to reuse.
   */
  private async teardown(): Promise<void> {
    // The toolkit holds references to both engines, so it goes first.
    try {
      await this.api?.destroy?.();
    } catch {
      // already gone
    }
    try {
      await this.rtmClient?.logout?.();
    } catch {
      // already logged out
    }
    try {
      this.micTrack?.stop();
      this.micTrack?.close();
    } catch {
      // track already released
    }
    try {
      await this.rtcClient?.leave();
    } catch {
      // already left
    }
    this.api = null;
    this.rtmClient = null;
    this.micTrack = null;
    this.rtcClient = null;
  }

  async leave(): Promise<void> {
    await this.teardown();
  }
}
