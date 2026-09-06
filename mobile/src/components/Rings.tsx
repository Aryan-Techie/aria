import { useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, View } from 'react-native';
import Animated, {
  Easing,
  interpolate,
  interpolateColor,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

import { DURATION, EASE, RING_PALETTE, type RingState } from '@/theme';

/**
 * The voice visualiser: three concentric rings around a soft core.
 *
 * The console draws a canvas orb — three blurred gradient blobs and a 72-bar
 * halo (frontend/components/Orb.tsx). There is no canvas in React Native and a
 * faithful port needs Skia, so this keeps the semantics and drops the
 * geometry. What carries over, because it is what the thing actually
 * communicates:
 *
 *   - Colour is who is speaking. Aria owns the cool half of the wheel, the
 *     customer the warm half, so it reads without a label.
 *   - Colours cross-fade, never switch. The console smooths at dt*3; here the
 *     same feel comes from a timed mix between the outgoing and incoming
 *     colour.
 *   - Amplitude is real RTC volume, and there is a synthetic breath underneath
 *     it so the rings are never dead still while a call is live.
 */

const EASING = Easing.bezier(...EASE);

/** Ring radii as a fraction of the box, innermost first. */
const RINGS = [0.42, 0.62, 0.84];
/** How much each ring reacts to the voice. Outer rings move most. */
const REACT = [0.06, 0.11, 0.17];

export function Rings({
  state,
  level,
  size = 240,
}: {
  state: RingState;
  /** 0..1, the loudest live level. */
  level: number;
  size?: number;
}) {
  const colour = RING_PALETTE[state];

  // Cross-fade: hold the outgoing colour and mix towards the incoming one,
  // rather than interpolating across the whole palette and passing through
  // colours that were never on screen.
  const [pair, setPair] = useState({ from: colour, to: colour });
  const mix = useSharedValue(1);
  const previous = useRef(colour);

  useEffect(() => {
    if (previous.current === colour) return;
    setPair({ from: previous.current, to: colour });
    previous.current = colour;
    mix.value = 0;
    mix.value = withTiming(1, { duration: DURATION.colour, easing: EASING });
  }, [colour, mix]);

  // Amplitude arrives about five times a second from Agora's volume
  // indication, which reads as a stutter unless it is smoothed between
  // reports.
  const amp = useSharedValue(0);
  useEffect(() => {
    amp.value = withTiming(Math.min(1, Math.max(0, level)), {
      duration: 180,
      easing: EASING,
    });
  }, [level, amp]);

  // The breath. Without it a silent call looks like a frozen screen.
  const breath = useSharedValue(0);
  const [reduceMotion, setReduceMotion] = useState(false);
  useEffect(() => {
    let alive = true;
    AccessibilityInfo.isReduceMotionEnabled().then((on) => {
      if (!alive) return;
      setReduceMotion(on);
      if (!on) {
        breath.value = withRepeat(
          withTiming(1, { duration: 2600, easing: Easing.inOut(Easing.sin) }),
          -1,
          true
        );
      }
    });
    const sub = AccessibilityInfo.addEventListener('reduceMotionChanged', setReduceMotion);
    return () => {
      alive = false;
      sub.remove();
    };
  }, [breath]);

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      {RINGS.map((fraction, i) => (
        <Ring
          key={fraction}
          size={size * fraction}
          // Absolutely positioned children ignore the parent's centring, so
          // the offset is computed here where the box size is known.
          offset={(size - size * fraction) / 2}
          react={REACT[i]}
          baseOpacity={0.55 - i * 0.15}
          border={i > 0}
          amp={amp}
          breath={breath}
          mix={mix}
          pair={pair}
          reduceMotion={reduceMotion}
        />
      ))}
    </View>
  );
}

function Ring({
  size,
  offset,
  react,
  baseOpacity,
  border,
  amp,
  breath,
  mix,
  pair,
  reduceMotion,
}: {
  size: number;
  offset: number;
  react: number;
  baseOpacity: number;
  border: boolean;
  amp: SharedValue<number>;
  breath: SharedValue<number>;
  mix: SharedValue<number>;
  pair: { from: string; to: string };
  reduceMotion: boolean;
}) {
  const style = useAnimatedStyle(() => {
    const colour = interpolateColor(mix.value, [0, 1], [pair.from, pair.to]);
    // A small idle sway plus the voice on top, matching the console's
    // "0.07 + 0.05*sin(t)" resting amplitude.
    const sway = reduceMotion ? 0 : interpolate(breath.value, [0, 1], [-0.012, 0.012]);
    const scale = 1 + sway + amp.value * react;
    const opacity = baseOpacity * (0.72 + amp.value * 0.28);
    return border
      ? { transform: [{ scale }], opacity, borderColor: colour }
      : { transform: [{ scale }], opacity, backgroundColor: colour };
  });

  return (
    <Animated.View
      style={[
        {
          position: 'absolute',
          top: offset,
          left: offset,
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: border ? 1.5 : 0,
        },
        style,
      ]}
    />
  );
}
