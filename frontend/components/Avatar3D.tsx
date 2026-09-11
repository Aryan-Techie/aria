"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { LipsyncAnalyser, type Viseme } from "@/lib/lipsync";
import type { Phase, Speaker } from "@/components/Orb";

const VISEMES: Viseme[] = [
  "viseme_PP",
  "viseme_FF",
  "viseme_TH",
  "viseme_DD",
  "viseme_kk",
  "viseme_CH",
  "viseme_SS",
  "viseme_aa",
  "viseme_E",
  "viseme_I",
  "viseme_O",
  "viseme_U",
];

// Ready Player Me exports the SAME 67-entry viseme/ARKit blend-shape
// dictionary onto EyeLeft, EyeRight, Wolf3D_Head AND Wolf3D_Teeth alike -
// confirmed by inspecting this exact avatar.glb's JSON chunk. Picking "the
// first SkinnedMesh with a morphTargetDictionary" during a traverse finds
// an eyeball mesh before it ever reaches the head, so every viseme update
// was silently animating invisible eyeball geometry - the mouth (Head and
// Teeth) never received a single morph target write. Name-matching the
// meshes that actually show on camera is the fix RPM's own docs use.
const MORPH_MESH_NAMES = ["Wolf3D_Head", "Wolf3D_Teeth"];

function findMorphMeshes(root: THREE.Object3D): THREE.SkinnedMesh[] {
  const found: THREE.SkinnedMesh[] = [];
  root.traverse((child) => {
    const mesh = child as THREE.SkinnedMesh;
    if (mesh.isSkinnedMesh && mesh.morphTargetDictionary && MORPH_MESH_NAMES.includes(mesh.name)) {
      found.push(mesh);
    }
  });
  return found;
}

/**
 * Standalone 3D face, lipsynced to Aria's real remote audio - plain Three.js
 * (no react-three-fiber): R3F v8's react-reconciler dependency reads a React
 * internals field Next's App Router build renames, and no version of either
 * lined up with this app's React/Next combination without pulling in
 * React-19-only react-dom APIs this app doesn't have. Vanilla three.js has
 * no React-internals coupling at all, so it sidesteps the whole problem -
 * same imperative canvas-ref + rAF-loop shape components/Orb.tsx already
 * uses for its own 2D canvas.
 *
 * Opt-in only (toggled in page.tsx); the 2D Orb stays the default. No body
 * animation, no multi-avatar switching - just the lipsync.
 */
export function Avatar3D({
  speaker,
  hold,
  getTrack,
}: {
  phase: Phase;
  speaker: Speaker;
  hold: boolean;
  getLevel: () => number;
  getTrack: () => MediaStreamTrack | null;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef({ speaker, hold, getTrack });
  propsRef.current = { speaker, hold, getTrack };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let disposed = false;
    let raf = 0;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(22, 1, 0.1, 10);
    camera.position.set(0, 0, 0.78);

    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));

    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const key = new THREE.DirectionalLight(0xffffff, 1.2);
    key.position.set(0.6, 1, 1.2);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xffffff, 0.3);
    rim.position.set(-0.8, 0.4, -0.6);
    scene.add(rim);

    let morphMeshes: THREE.SkinnedMesh[] = [];
    new GLTFLoader().load(
      "/models/avatar.glb",
      (gltf) => {
        if (disposed) return;
        gltf.scene.position.set(0, -1.6, 0);
        scene.add(gltf.scene);
        morphMeshes = findMorphMeshes(gltf.scene);
        if (morphMeshes.length === 0) {
          console.warn("Avatar3D: no Wolf3D_Head/Wolf3D_Teeth morph mesh found in avatar.glb");
        }
      },
      undefined,
      (err) => console.warn("Avatar3D: failed to load avatar.glb", err)
    );

    const resize = () => {
      const r = canvas.getBoundingClientRect();
      const d = window.devicePixelRatio || 1;
      renderer.setSize(r.width, r.height, false);
      camera.aspect = r.width / Math.max(1, r.height);
      camera.updateProjectionMatrix();
      void d;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const analyser = new LipsyncAnalyser();
    const blink = { timer: 2 + Math.random() * 3, active: false, elapsed: 0 };
    let last = performance.now();

    const lerpTo = (name: string, value: number, speed: number) => {
      for (const mesh of morphMeshes) {
        if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences) continue;
        const idx = mesh.morphTargetDictionary[name];
        if (idx === undefined) continue;
        const infl = mesh.morphTargetInfluences;
        infl[idx] = THREE.MathUtils.lerp(infl[idx], value, speed);
      }
    };

    const frame = (now: number) => {
      const delta = Math.min(0.05, (now - last) / 1000);
      last = now;
      const { hold: onHold, getTrack: track } = propsRef.current;

      if (morphMeshes.length > 0) {
        // Gate on the real track, not on Agora's agent-state label - that
        // state can flip back to "listening" before the TTS audio it
        // describes has actually arrived and started playing, which left
        // the mouth frozen for the exact window the voice was audible.
        // Actual signal presence (sampled below) is the only timing that
        // can't lag behind itself.
        const remoteTrack = !onHold ? track() : null;
        if (remoteTrack) analyser.connect(remoteTrack);
        else analyser.dispose();
        const { viseme, volume } = remoteTrack ? analyser.sample() : { viseme: "viseme_sil" as const, volume: 0 };

        for (const name of VISEMES) {
          lerpTo(name, name === viseme ? Math.min(volume * 3, 1) : 0, 0.4);
        }
        lerpTo("jawOpen", Math.min(volume * 2, 0.6), 0.4);

        if (!blink.active) {
          blink.timer -= delta;
          if (blink.timer <= 0) {
            blink.active = true;
            blink.elapsed = 0;
          }
        }
        if (blink.active) {
          blink.elapsed += delta;
          lerpTo("eyeBlinkLeft", 1, 0.9);
          lerpTo("eyeBlinkRight", 1, 0.9);
          if (blink.elapsed > 0.15) {
            blink.active = false;
            blink.timer = 2 + Math.random() * 3;
          }
        } else {
          lerpTo("eyeBlinkLeft", 0, 0.4);
          lerpTo("eyeBlinkRight", 0, 0.4);
        }
      }

      renderer.render(scene, camera);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      analyser.dispose();
      renderer.dispose();
      scene.traverse((child) => {
        const mesh = child as THREE.Mesh;
        if (mesh.isMesh) {
          mesh.geometry?.dispose();
          const mats = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
          mats.forEach((m) => m?.dispose());
        }
      });
    };
  }, []);

  return <canvas ref={canvasRef} className="orb" aria-hidden="true" />;
}
