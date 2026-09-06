import { Text } from 'react-native';

import { useTheme } from '@/theme';
import { toolBusy } from '@/lib/vocab';
import { type } from '@/theme/type';

/**
 * One line of text under the rings, saying what is happening.
 *
 * This is the app's substitute for a spinner. The console refuses spinners
 * outright — "no spinner where the data can be shown instead" — so every wait
 * in this app is a sentence naming what is being waited on.
 *
 * The order below is the console's (frontend/app/page.tsx:420-439) and the
 * order is the design: an error outranks everything, a person on the call
 * outranks Aria, and a tool in flight outranks "thinking", because "checking
 * the calendar" is the more useful of the two true statements.
 */

export type CaptionInput = {
  error: string | null;
  phase: 'idle' | 'connecting' | 'active' | 'ending' | 'ended';
  muted: boolean;
  held: boolean;
  repOnCall: string | null;
  busyTool: string | null;
  ariaSpeaking: boolean;
  youSpeaking: boolean;
  endedFor: string | null;
};

function resolve(s: CaptionInput): { text: string; quiet: boolean } {
  if (s.error) return { text: s.error, quiet: false };
  if (s.phase === 'idle') return { text: 'Ready when you are', quiet: false };
  if (s.phase === 'connecting') return { text: 'Connecting…', quiet: true };
  if (s.phase === 'ending') return { text: 'Wrapping up…', quiet: true };
  if (s.phase === 'ended') {
    return { text: s.endedFor ? `Call ended · ${s.endedFor}` : 'Call ended', quiet: false };
  }
  if (s.held) return { text: 'On hold', quiet: true };
  if (s.repOnCall) return { text: `${s.repOnCall} has the call`, quiet: false };
  if (s.busyTool) return { text: `${toolBusy(s.busyTool)}…`, quiet: false };
  if (s.ariaSpeaking) return { text: 'Aria is speaking', quiet: false };
  if (s.muted) return { text: 'Muted', quiet: true };
  if (s.youSpeaking) return { text: 'Listening', quiet: false };
  return { text: 'Listening', quiet: false };
}

export function Caption({ state, large = false }: { state: CaptionInput; large?: boolean }) {
  const { t } = useTheme();
  const { text, quiet } = resolve(state);
  const isError = Boolean(state.error);

  return (
    <Text
      accessibilityLiveRegion="polite"
      style={[
        large ? type.captionLarge : type.caption,
        {
          color: isError ? t.bad : quiet ? t.ink3 : t.ink2,
          fontStyle: quiet ? 'italic' : 'normal',
          textAlign: 'center',
          paddingHorizontal: 32,
        },
      ]}>
      {text}
    </Text>
  );
}
