import { Platform, TextStyle } from 'react-native';

/**
 * The console's type scale, trimmed to what a phone actually uses.
 *
 * Two rules carried over from frontend/DESIGN.md and worth not losing:
 * headings tighten as they grow (-0.02em at 22px, -0.03em at 26px), and
 * anything that can change under the reader gets tabular numerals.
 *
 * Web tracking is in em; RN letterSpacing is in points, so each value here is
 * the em figure multiplied by its own font size.
 */

/**
 * System font first, matching the console's `-apple-system, ... "Inter"` stack.
 * On iOS that is SF Pro, which is what the design was drawn against. Android
 * has no SF, so Inter is loaded and named explicitly there.
 */
const sans = Platform.select({ ios: undefined, default: 'Inter_400Regular' });
const sansMedium = Platform.select({ ios: undefined, default: 'Inter_500Medium' });
const sansSemi = Platform.select({ ios: undefined, default: 'Inter_600SemiBold' });

/** Numbers that mutate under the reader: the timer, durations, percentages. */
export const tabular: TextStyle = { fontVariant: ['tabular-nums'] };

export const type = {
  /** The one serif in the whole app: the end-of-call headline. Nowhere else. */
  headline: {
    fontFamily: 'InstrumentSerif_400Regular',
    fontSize: 32,
    lineHeight: 36,
    letterSpacing: -0.48,
  } as TextStyle,

  /** Idle caption — "Ready when you are". */
  captionLarge: {
    fontFamily: sansMedium,
    fontSize: 22,
    fontWeight: '500',
    letterSpacing: -0.33,
  } as TextStyle,

  /** Company name on an escalation row. */
  title: {
    fontFamily: sansSemi,
    fontSize: 22,
    fontWeight: '600',
    letterSpacing: -0.55,
    lineHeight: 25,
  } as TextStyle,

  /** Transcript turn text. The console's most-read size. */
  body: {
    fontFamily: sans,
    fontSize: 17,
    fontWeight: '400',
    letterSpacing: -0.2,
    lineHeight: 25,
  } as TextStyle,

  /** Live caption under the rings. */
  caption: {
    fontFamily: sansMedium,
    fontSize: 15,
    fontWeight: '500',
    letterSpacing: -0.075,
  } as TextStyle,

  /** Primary button label. */
  button: {
    fontFamily: sansSemi,
    fontSize: 15,
    fontWeight: '600',
    letterSpacing: -0.15,
  } as TextStyle,

  /** Status chip, list rows, settings values. */
  small: {
    fontFamily: sansMedium,
    fontSize: 13,
    fontWeight: '500',
    letterSpacing: -0.065,
  } as TextStyle,

  /** Section labels. Uppercase, the one place tracking goes positive. */
  label: {
    fontFamily: sansSemi,
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.72,
    textTransform: 'uppercase',
  } as TextStyle,

  /** Transcript role marker — "You" / "Aria". */
  role: {
    fontFamily: sansSemi,
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.24,
  } as TextStyle,

  /** Hints, timestamps, the quiet row at the bottom of Settings. */
  tiny: {
    fontFamily: sansMedium,
    fontSize: 11.5,
    fontWeight: '500',
  } as TextStyle,
} as const;

/**
 * Loaded at startup by the root layout. iOS renders body text in SF and only
 * genuinely needs the serif, but loading all four on both platforms keeps the
 * font map identical everywhere and costs one small asset.
 */
export { Inter_400Regular, Inter_500Medium, Inter_600SemiBold } from '@expo-google-fonts/inter';
export { InstrumentSerif_400Regular } from '@expo-google-fonts/instrument-serif';
