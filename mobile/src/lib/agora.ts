import {
  AudioRoute,
  AudioScenarioType,
  ChannelProfileType,
  ClientRoleType,
  createAgoraRtcEngine,
  type IRtcEngine,
} from 'react-native-agora';
import { PermissionsAndroid, Platform } from 'react-native';

/**
 * Audio-only RTC, wrapped so the screens never touch the engine directly.
 *
 * Deliberately no RTM. The console pairs RTC with agora-rtm-sdk and
 * agora-agent-client-toolkit to receive transcripts, but that toolkit is
 * web-only, and frontend/lib/api.ts:107-115 already records that the RTM
 * envelopes were not arriving reliably anyway — the console reads its panels
 * from HTTP polling. So this app carries voice on RTC and everything else on
 * the session poll, which is one fewer moving part rather than a compromise.
 *
 * Mute and hold follow the console's semantics exactly
 * (frontend/lib/agoraClient.ts): mute silences the mic only; hold is a purely
 * local state that both mutes the mic and stops the far side playing, with no
 * backend primitive behind it.
 */

export type Levels = {
  /** 0..1, this device's microphone. */
  local: number;
  /** 0..1, loudest remote speaker — Aria, or the rep once she has joined. */
  remote: number;
};

export type JoinParams = {
  appId: string;
  channel: string;
  token: string;
  uid: number;
};

export type CallHandlers = {
  onJoined?: () => void;
  onRemoteJoined?: (uid: number) => void;
  onRemoteLeft?: (uid: number) => void;
  onError?: (message: string) => void;
};

/** Agora reports volume 0-255; the rings want 0-1. */
const NORM = 255;

/**
 * Agora's published audio tuning for a conversational-AI client
 * (docs.agora.io/en/ai/best-practices/audio-setup). On native this is what the
 * ConvoAI toolkit's `loadAudioSettings()` applies for you; there is no such
 * toolkit for React Native, so it is applied by hand.
 *
 * This is not optional polish. Without it the agent's own voice comes back in
 * through the microphone, the server's turn detection hears it as the customer
 * starting to talk, and it interrupts her mid-sentence — which sounds exactly
 * like her speech skipping and jumping.
 *
 * `nlpAlgRoute` is the one value that depends on where the audio is coming
 * out, so this has to be re-applied whenever the route changes, not only once
 * before joining.
 */
function aiAudioParams(route: AudioRoute): string[] {
  const nearField =
    route === AudioRoute.RouteHeadset ||
    route === AudioRoute.RouteEarpiece ||
    route === AudioRoute.RouteHeadsetnomic ||
    route === AudioRoute.RouteBluetoothDeviceHfp;

  return [
    '{"che.audio.aec.split_srate_for_48k":16000}',
    '{"che.audio.sf.enabled":true}',
    '{"che.audio.sf.stftType":6}',
    '{"che.audio.sf.ainlpLowLatencyFlag":1}',
    '{"che.audio.sf.ainsLowLatencyFlag":1}',
    '{"che.audio.sf.procChainMode":1}',
    '{"che.audio.sf.nlpDynamicMode":1}',
    `{"che.audio.sf.nlpAlgRoute":${nearField ? 0 : 1}}`,
    '{"che.audio.sf.ainlpModelPref":10}',
    '{"che.audio.sf.nsngAlgRoute":12}',
    '{"che.audio.sf.ainsModelPref":10}',
    '{"che.audio.sf.nsngPredefAgg":11}',
    // Automatic gain control fights the agent's own level control and makes
    // room noise loud enough to read as speech.
    '{"che.audio.agc.enable":false}',
  ];
}

export class AgoraCall {
  private engine: IRtcEngine | null = null;
  private levels: Levels = { local: 0, remote: 0 };
  private muted = false;
  private held = false;
  private joined = false;

  getLevels(): Levels {
    return this.levels;
  }

  isMuted(): boolean {
    return this.muted;
  }

  isHeld(): boolean {
    return this.held;
  }

  /**
   * Android will not capture audio without a runtime grant, and the failure
   * mode is silence rather than an error, so this is checked before joining
   * rather than at first use.
   */
  static async ensureMicPermission(): Promise<boolean> {
    if (Platform.OS !== 'android') return true;
    const granted = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.RECORD_AUDIO
    );
    return granted === PermissionsAndroid.RESULTS.GRANTED;
  }

  async join(params: JoinParams, handlers: CallHandlers = {}): Promise<void> {
    if (!(await AgoraCall.ensureMicPermission())) {
      throw new Error('Microphone permission denied.');
    }

    const engine = createAgoraRtcEngine();
    this.engine = engine;

    // Live-broadcasting profile with the AI-client scenario is what Agora
    // specifies for talking to a Conversational AI agent. The communication
    // profile's tuning is built for two humans on a phone call and mangles a
    // synthesised voice.
    engine.initialize({
      appId: params.appId,
      channelProfile: ChannelProfileType.ChannelProfileLiveBroadcasting,
      audioScenario: AudioScenarioType.AudioScenarioAiClient,
    });

    engine.addListener('onJoinChannelSuccess', () => {
      this.joined = true;
      // Joining sets the audio route, so forcing the loudspeaker has to happen
      // after it lands — doing it synchronously after joinChannel() gets
      // overwritten and leaves the call on the earpiece.
      engine.setEnableSpeakerphone(true);
      this.applyAudioParams(AudioRoute.RouteSpeakerphone);
      handlers.onJoined?.();
    });
    engine.addListener('onUserJoined', (_c, remoteUid) => handlers.onRemoteJoined?.(remoteUid));
    engine.addListener('onUserOffline', (_c, remoteUid) => {
      // The far side is gone; stop the rings reacting to a stale level.
      this.levels = { ...this.levels, remote: 0 };
      handlers.onRemoteLeft?.(remoteUid);
    });
    engine.addListener('onError', (_err, msg) => handlers.onError?.(msg));

    // The tuning above is route-dependent, and the route can change under us —
    // headphones going in, Bluetooth connecting — so it is re-applied here as
    // well as before the join.
    engine.addListener('onAudioRoutingChanged', (routing: number) => {
      this.applyAudioParams(routing as AudioRoute);
    });

    // Fires roughly five times a second, carrying local and remote speakers in
    // the same shape. This is what drives both the ring amplitude and the
    // decision about who is speaking — the console needed a separate poll of
    // getVolumeLevel() for the same thing.
    engine.enableAudioVolumeIndication(200, 3, true);
    engine.addListener('onAudioVolumeIndication', (_connection, speakers) => {
      let local = this.levels.local;
      let remote = 0;
      let sawRemote = false;
      for (const s of speakers ?? []) {
        const level = Math.min(1, (s.volume ?? 0) / NORM);
        // Agora reports the local speaker as uid 0 in this callback.
        if (s.uid === 0) local = level;
        else {
          sawRemote = true;
          remote = Math.max(remote, level);
        }
      }
      this.levels = {
        local: this.muted || this.held ? 0 : local,
        remote: sawRemote ? remote : this.held ? 0 : this.levels.remote,
      };
    });

    engine.enableAudio();

    // Loudspeaker, not the earpiece. Held to the ear this is a phone call the
    // OS knows nothing about: no proximity blanking, so a cheek lands on the
    // End button. On speaker it behaves like what it is — an app you look at
    // while you talk to it.
    engine.setDefaultAudioRouteToSpeakerphone(true);
    this.applyAudioParams(AudioRoute.RouteSpeakerphone);

    engine.joinChannel(params.token, params.channel, params.uid, {
      clientRoleType: ClientRoleType.ClientRoleBroadcaster,
      publishMicrophoneTrack: true,
      autoSubscribeAudio: true,
    });
  }

  private applyAudioParams(route: AudioRoute): void {
    const engine = this.engine;
    if (!engine) return;
    for (const param of aiAudioParams(route)) {
      try {
        engine.setParameters(param);
      } catch {
        // A private parameter the installed SDK does not know is a no-op, not
        // a reason to fail the call.
      }
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
    this.engine?.muteLocalAudioStream(muted);
    if (muted) this.levels = { ...this.levels, local: 0 };
  }

  /**
   * Hold is entirely local — there is no backend primitive for it. Entering
   * hold forces mute and stops remote playback; leaving restores both, which
   * matches what the console does in page.tsx:398-412.
   */
  setHold(held: boolean): void {
    this.held = held;
    this.engine?.muteAllRemoteAudioStreams(held);
    this.setMuted(held);
    if (held) this.levels = { local: 0, remote: 0 };
  }

  /**
   * Each step is guarded on its own: one failure here must not strand the
   * engine half-joined, which is the bug the console's teardown comment warns
   * about (frontend/lib/agoraClient.ts:259-288).
   */
  leave(): void {
    const engine = this.engine;
    if (!engine) return;
    this.engine = null;
    this.joined = false;
    this.levels = { local: 0, remote: 0 };
    this.muted = false;
    this.held = false;
    try {
      engine.leaveChannel();
    } catch {
      // Already gone.
    }
    try {
      engine.removeAllListeners();
    } catch {
      // Nothing registered.
    }
    try {
      engine.release();
    } catch {
      // Already released.
    }
  }

  isJoined(): boolean {
    return this.joined;
  }
}
