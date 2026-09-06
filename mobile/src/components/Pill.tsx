import { useEffect } from 'react';
import { Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';

import { useTheme } from '@/theme';
import { tabular, type } from '@/theme/type';

export type Tone = 'good' | 'warn' | 'bad' | 'info' | 'neutral';

/**
 * A tinted badge. Semantic colour appears as a soft ground and coloured text,
 * never as a saturated fill — the console's rule, and the reason the whole
 * thing stays quiet with six states on screen.
 */
export function Pill({ tone = 'neutral', children }: { tone?: Tone; children: string }) {
  const { t } = useTheme();
  const palette: Record<Tone, { bg: string; fg: string }> = {
    good: { bg: t.goodSoft, fg: t.goodInk },
    warn: { bg: t.youSoft, fg: t.warnInk },
    bad: { bg: t.badSoft, fg: t.bad },
    info: { bg: t.ariaSoft, fg: t.aria },
    neutral: { bg: t.surface2, fg: t.ink2 },
  };
  const { bg, fg } = palette[tone];
  return (
    <View
      style={{
        backgroundColor: bg,
        paddingVertical: 5,
        paddingHorizontal: 11,
        borderRadius: 999,
        alignSelf: 'flex-start',
      }}>
      <Text style={[type.small, { color: fg }]}>{children}</Text>
    </View>
  );
}

export type CallPhase = 'idle' | 'connecting' | 'live' | 'ended';

/**
 * The status chip: a dot, a word, and the clock.
 *
 * Live is red and pulses; connecting is amber and deliberately does not, so a
 * call that is still dialling never reads as one that has connected. Ended is
 * green. That is the console's mapping (globals.css:182-190) and it is worth
 * not "fixing" — red here means on air, not broken.
 */
export function StatusChip({ phase, elapsed }: { phase: CallPhase; elapsed: string | null }) {
  const { t } = useTheme();
  const pulse = useSharedValue(0);

  useEffect(() => {
    if (phase !== 'live') {
      pulse.value = 0;
      return;
    }
    pulse.value = withRepeat(
      withTiming(1, { duration: 1800, easing: Easing.out(Easing.ease) }),
      -1,
      false
    );
  }, [phase, pulse]);

  const halo = useAnimatedStyle(() => ({
    opacity: 0.45 * (1 - pulse.value),
    transform: [{ scale: 1 + pulse.value * 2.4 }],
  }));

  const dot = { idle: t.ink3, connecting: t.warn, live: t.bad, ended: t.good }[phase];
  const label = { idle: 'Standby', connecting: 'Connecting', live: 'Live', ended: 'Ended' }[phase];

  return (
    <View
      style={[
        {
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          backgroundColor: t.surface,
          borderWidth: 1,
          borderColor: t.line,
          borderRadius: 999,
          paddingVertical: 6,
          paddingLeft: 10,
          paddingRight: 12,
          alignSelf: 'center',
        },
        t.shadow,
      ]}>
      <View style={{ width: 8, height: 8, alignItems: 'center', justifyContent: 'center' }}>
        {phase === 'live' && (
          <Animated.View
            style={[
              { position: 'absolute', width: 8, height: 8, borderRadius: 4, backgroundColor: t.bad },
              halo,
            ]}
          />
        )}
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: dot }} />
      </View>
      <Text style={[type.small, { color: t.ink }]}>{label}</Text>
      {elapsed && <Text style={[type.small, tabular, { color: t.ink2 }]}>{elapsed}</Text>}
    </View>
  );
}
