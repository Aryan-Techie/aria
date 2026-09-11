/**
 * Real-time viseme detection from Aria's actual TTS audio - formant-band
 * energy ratios on a WebAudio FFT, no ML model, no phoneme API. Adapted
 * directly from Agora's own reference implementation
 * (github.com/AgoraIO-Community/RPM-agora-agent, src/hooks/useLipSync.jsx) -
 * that version taps a plain <audio> element; this one taps the raw
 * MediaStreamTrack off Agora's remote RTC audio instead (see
 * AgoraCallClient.getRemoteMediaStreamTrack), since this console has no
 * <audio> element of its own - Agora's SDK plays the remote track
 * internally.
 *
 * The viseme names below (viseme_PP, viseme_aa, ...) are Oculus/Meta OVR
 * visemes - on a Ready Player Me avatar exported with visemes enabled,
 * they ARE the morph target names on the head mesh directly, not a
 * separate mapping table.
 */

export type Viseme =
  | "viseme_sil"
  | "viseme_PP"
  | "viseme_FF"
  | "viseme_TH"
  | "viseme_DD"
  | "viseme_kk"
  | "viseme_CH"
  | "viseme_SS"
  | "viseme_aa"
  | "viseme_E"
  | "viseme_I"
  | "viseme_O"
  | "viseme_U";

export interface LipsyncFrame {
  viseme: Viseme;
  volume: number;
}

/**
 * Owns the AudioContext/AnalyserNode for one remote track. Call connect()
 * once a remote track exists, sample() once per animation frame, and
 * dispose() on teardown - mirrors AgoraCallClient's own lifecycle shape.
 */
export class LipsyncAnalyser {
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private data: Uint8Array | null = null;
  private connectedTrackId: string | null = null;

  connect(track: MediaStreamTrack): void {
    if (this.connectedTrackId === track.id && this.ctx) return;
    this.dispose();
    try {
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(new MediaStream([track]));
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      source.connect(analyser);
      // Deliberately not connected to ctx.destination - Agora's SDK is
      // already playing this track; connecting it again would double it.
      this.ctx = ctx;
      this.analyser = analyser;
      this.data = new Uint8Array(analyser.frequencyBinCount);
      this.connectedTrackId = track.id;
      // A context created outside the synchronous gesture stack (this one
      // is - it fires when the remote track first arrives, well after the
      // "start call" click) can come up "suspended" under autoplay policy,
      // which reads back as constant silence rather than an error.
      if (ctx.state === "suspended") void ctx.resume().catch(() => {});
    } catch {
      this.ctx = null;
      this.analyser = null;
    }
  }

  dispose(): void {
    this.ctx?.close().catch(() => {});
    this.ctx = null;
    this.analyser = null;
    this.data = null;
    this.connectedTrackId = null;
  }

  /** One frame of viseme + volume, or silence if not connected yet. */
  sample(): LipsyncFrame {
    if (!this.analyser || !this.data) return { viseme: "viseme_sil", volume: 0 };
    if (this.ctx?.state === "suspended") void this.ctx.resume().catch(() => {});
    this.analyser.getByteFrequencyData(this.data as Uint8Array<ArrayBuffer>);
    const d = this.data;

    const avg = (from: number, to: number) => {
      let sum = 0;
      for (let i = from; i < to; i++) sum += d[i];
      return sum / (to - from);
    };

    const volume = avg(0, d.length) / 255;
    if (volume <= 0.02) return { viseme: "viseme_sil", volume };

    // Formant-band energies - same bins as the reference (fftSize=256 ->
    // 128 bins covering 0-~22kHz on a typical 44.1kHz context).
    const f1 = avg(0, 8);
    const f2 = avg(8, 20);
    const f3 = avg(20, 40);
    const f4 = avg(40, 70);
    const highF = avg(70, 110);
    const total = f1 + f2 + f3 + f4 + highF;
    if (total <= 10) return { viseme: "viseme_sil", volume };

    const nf1 = f1 / total;
    const nf2 = f2 / total;
    const nf3 = f3 / total;
    const nhighF = highF / total;

    let viseme: Viseme;
    if (nf1 > 0.25 && nf2 < 0.2) viseme = "viseme_aa";
    else if (nf2 > 0.25 && nhighF > 0.2) viseme = "viseme_I";
    else if (nf1 > 0.2 && nf2 > 0.2) viseme = "viseme_E";
    else if (nf1 < 0.15 && nf2 < 0.2 && nhighF > 0.25) viseme = "viseme_U";
    else if (nf1 < 0.2 && nf2 > 0.2 && nf3 > 0.2) viseme = "viseme_O";
    else if (nhighF > 0.35) viseme = "viseme_SS";
    else if (nhighF > 0.25) viseme = "viseme_FF";
    else if (nf1 < 0.15 && nf2 < 0.2 && nhighF < 0.2) viseme = "viseme_PP";
    else if (nf2 < 0.2 && nf3 > 0.2) viseme = "viseme_kk";
    else viseme = "viseme_DD";

    return { viseme, volume };
  }
}
