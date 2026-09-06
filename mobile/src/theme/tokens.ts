/**
 * Verbatim port of the console's token block — frontend/app/globals.css:16-68.
 *
 * Same values, same names, same two themes. The console is the source of
 * truth: if a colour changes there it changes here, and nowhere else in this
 * app should a hex literal appear.
 *
 * Semantic colour is never a large fill (DESIGN.md) — it tints pills, dots and
 * hairlines only. Aria owns the cool half of the wheel, the customer the warm
 * half, so who is speaking reads from the rings alone.
 */

export type Theme = {
  bg: string;
  surface: string;
  surface2: string;
  ink: string;
  ink2: string;
  ink3: string;
  line: string;
  line2: string;
  aria: string;
  ariaSoft: string;
  you: string;
  youSoft: string;
  good: string;
  goodInk: string;
  goodSoft: string;
  warn: string;
  warnInk: string;
  bad: string;
  badSoft: string;
  info: string;
  glass: string;
  /** Elevation. RN has no multi-shadow, so this is the nearest single one. */
  shadow: {
    shadowColor: string;
    shadowOffset: { width: number; height: number };
    shadowOpacity: number;
    shadowRadius: number;
    elevation: number;
  };
};

const light: Theme = {
  bg: '#f5f5f7',
  surface: '#ffffff',
  surface2: '#f2f2f4',
  ink: '#1d1d1f',
  ink2: '#6e6e73',
  ink3: '#aeaeb2',
  line: 'rgba(0, 0, 0, 0.07)',
  line2: 'rgba(0, 0, 0, 0.12)',
  aria: '#5e5ce6',
  ariaSoft: 'rgba(94, 92, 230, 0.12)',
  you: '#ff9f0a',
  youSoft: 'rgba(255, 159, 10, 0.14)',
  good: '#34c759',
  goodInk: '#1f8f3c',
  goodSoft: 'rgba(52, 199, 89, 0.14)',
  warn: '#ff9f0a',
  warnInk: '#b46a00',
  bad: '#ff3b30',
  badSoft: 'rgba(255, 59, 48, 0.12)',
  info: '#0a84ff',
  glass: 'rgba(245, 245, 247, 0.72)',
  shadow: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.1,
    shadowRadius: 24,
    elevation: 3,
  },
};

/**
 * Dark deliberately does NOT redefine --info, --good-soft, --bad-soft, the
 * radius, the fonts or the easing — those inherit from :root on the web, so
 * they are carried across unchanged here.
 */
const dark: Theme = {
  ...light,
  bg: '#000000',
  surface: '#151517',
  surface2: '#1f1f22',
  ink: '#f5f5f7',
  ink2: '#98989d',
  ink3: '#5c5c61',
  line: 'rgba(255, 255, 255, 0.08)',
  line2: 'rgba(255, 255, 255, 0.14)',
  aria: '#7d7aff',
  ariaSoft: 'rgba(125, 122, 255, 0.18)',
  you: '#ffb340',
  youSoft: 'rgba(255, 179, 64, 0.16)',
  good: '#30d158',
  goodInk: '#30d158',
  warn: '#ffd60a',
  warnInk: '#ffd60a',
  bad: '#ff453a',
  glass: 'rgba(0, 0, 0, 0.6)',
  shadow: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.6,
    shadowRadius: 32,
    elevation: 6,
  },
};

export const themes = { light, dark };

/** --r: 18px. Cards and panels only; pills are 999, circles are half. */
export const RADIUS = 18;

/**
 * The single easing token — cubic-bezier(.2,.8,.2,1). Everything uses it, so
 * nothing in this app snaps. Durations cluster where the console's do:
 * 100 press / 150-300 colour / 350-500 entrance / 600 layout.
 */
export const EASE = [0.2, 0.8, 0.2, 1] as const;

export const DURATION = {
  press: 100,
  colour: 250,
  enter: 350,
  layout: 600,
} as const;

/**
 * Ring palettes, one per state, from frontend/components/Orb.tsx:18-25.
 * Colours cross-fade between these rather than switching.
 */
export const RING_PALETTE = {
  idle: '#a5b4fc',
  aria: '#5e5ce6',
  you: '#ff9f0a',
  think: '#64d2ff',
  ended: '#34c759',
  hold: '#c7c7cc',
} as const;

export type RingState = keyof typeof RING_PALETTE;
