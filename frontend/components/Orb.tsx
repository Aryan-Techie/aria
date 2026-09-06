"use client";

import { useEffect, useRef } from "react";

export type Phase = "idle" | "live" | "ended";
/** Who the orb is showing. `think` is Aria between turns with a tool in
 * flight - the one state where the call is alive but nobody is speaking. */
export type Speaker = "none" | "aria" | "you" | "think";

const hex = (h: string): number[] => [
  parseInt(h.slice(1, 3), 16),
  parseInt(h.slice(3, 5), 16),
  parseInt(h.slice(5, 7), 16),
];

/** One palette per state. Aria is the cool half of the wheel, the customer
 * the warm half, so who is speaking reads from across a room. */
const PALETTE: Record<string, string[]> = {
  idle: ["#a5b4fc", "#bae6fd", "#e9d5ff"],
  aria: ["#5e5ce6", "#64d2ff", "#bf5af2"],
  you: ["#ff9f0a", "#ff375f", "#ffd60a"],
  think: ["#64d2ff", "#5e5ce6", "#a5b4fc"],
  ended: ["#34c759", "#64d2ff", "#a5b4fc"],
  hold: ["#c7c7cc", "#d1d1d6", "#e5e5ea"],
};

const BAR_COUNT = 72;

/**
 * The voice visualizer. A soft three-blob orb with a halo of bars, drawn on
 * a canvas every frame. Amplitude comes from `getLevel` - the real RTC
 * volume of whichever side is speaking - with a gentle synthetic breath
 * underneath so the orb is never dead still while the call is live.
 *
 * Everything moves continuously: colours cross-fade between states rather
 * than switching, and amplitude is smoothed so a level that arrives in
 * bursts (Agora reports it a few times a second) still reads as one voice.
 */
export function Orb({
  phase,
  speaker,
  hold,
  getLevel,
}: {
  phase: Phase;
  speaker: Speaker;
  hold: boolean;
  getLevel: () => number;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  // Props are read inside a long-lived rAF loop, so they live on a ref
  // rather than re-subscribing the loop on every change.
  const propsRef = useRef({ phase, speaker, hold, getLevel });
  propsRef.current = { phase, speaker, hold, getLevel };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let W = 0;
    let H = 0;
    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const d = window.devicePixelRatio || 1;
      canvas.width = r.width * d;
      canvas.height = r.height * d;
      W = r.width;
      H = r.height;
      ctx.setTransform(d, 0, 0, d, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cur = PALETTE.idle.map(hex);
    const bars = new Float32Array(BAR_COUNT);
    let amp = 0;
    let t = 0;
    let last = performance.now();
    let raf = 0;

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      t += reduceMotion ? dt * 0.3 : dt;
      const { phase, speaker, hold, getLevel } = propsRef.current;
      const talking = !hold && (speaker === "aria" || speaker === "you");

      let target: number;
      if (talking) {
        // Real level on top of a small synthetic syllable rhythm, so a
        // sparse level feed still breathes like speech between samples.
        const rhythm = Math.max(0, (Math.sin(t * 6.1) + Math.sin(t * 9.7) * 0.6 + 0.4) / 2) * 0.25;
        target = Math.min(1, 0.1 + getLevel() * 1.6 + rhythm);
      } else if (speaker === "think" && !hold) {
        target = 0.16 + 0.05 * Math.sin(t * 3);
      } else {
        target = 0.07 + 0.05 * Math.sin(t * 1.1);
      }
      amp += (target - amp) * Math.min(1, dt * 9);

      const key = hold ? "hold" : phase === "ended" ? "ended" : speaker === "none" ? "idle" : speaker;
      PALETTE[key].map(hex).forEach((c, i) =>
        c.forEach((v, j) => {
          cur[i][j] += (v - cur[i][j]) * Math.min(1, dt * 3);
        })
      );

      draw(talking);
      raf = requestAnimationFrame(frame);
    };

    const draw = (speaking: boolean) => {
      ctx.clearRect(0, 0, W, H);
      const dark = document.documentElement.dataset.theme === "dark";
      const { phase } = propsRef.current;
      const cx = W / 2;
      const cy = H / 2 - (phase === "idle" ? 30 : 8);
      const base = Math.min(W, H) * (phase === "idle" ? 0.27 : 0.23);
      const R = base * (1 + 0.2 * amp);
      const col = (i: number, a: number) => `rgba(${cur[i][0] | 0},${cur[i][1] | 0},${cur[i][2] | 0},${a})`;

      for (let i = 0; i < BAR_COUNT; i++) {
        const n = 0.5 + 0.5 * Math.sin(i * 0.9 + t * 7.3) * Math.sin(i * 2.3 - t * 4.1);
        const tg = speaking ? amp * (0.35 + 0.65 * n) : 0;
        bars[i] += (tg - bars[i]) * 0.22;
        if (bars[i] < 0.01) continue;
        const a = (i / BAR_COUNT) * Math.PI * 2;
        const r0 = R * 1.28;
        const len = 2 + bars[i] * base * 0.5;
        ctx.strokeStyle = col(i % 3, 0.22 + 0.5 * bars[i]);
        ctx.lineWidth = 2.4;
        ctx.lineCap = "round";
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * r0, cy + Math.sin(a) * r0);
        ctx.lineTo(cx + Math.cos(a) * (r0 + len), cy + Math.sin(a) * (r0 + len));
        ctx.stroke();
      }

      ctx.save();
      ctx.filter = `blur(${base * 0.09}px)`;
      ctx.globalCompositeOperation = dark ? "lighter" : "source-over";
      for (let k = 0; k < 3; k++) {
        const ang = t * (0.35 + k * 0.13) + k * 2.1;
        const off = R * 0.26 * (0.6 + amp * 0.9);
        const x = cx + Math.cos(ang) * off;
        const y = cy + Math.sin(ang) * off;
        const rr = R * (0.86 + 0.08 * Math.sin(t * 2 + k));
        const g = ctx.createRadialGradient(x, y, 0, x, y, rr);
        g.addColorStop(0, col(k, dark ? 0.85 : 0.95));
        g.addColorStop(1, col(k, 0));
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.arc(x, y, rr, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      const g2 = ctx.createRadialGradient(cx - R * 0.22, cy - R * 0.28, 0, cx, cy, R * 0.95);
      g2.addColorStop(0, `rgba(255,255,255,${dark ? 0.18 : 0.6})`);
      g2.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = g2;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 0.95, 0, Math.PI * 2);
      ctx.fill();
    };

    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className="orb" aria-hidden="true" />;
}
