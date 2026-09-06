import AsyncStorage from '@react-native-async-storage/async-storage';

/**
 * The three things this app remembers between launches.
 *
 * The base URL matters most: the backend binds 127.0.0.1 and the cloudflared
 * quick tunnel mints a new hostname on every `run.bat`, so a hardcoded URL is
 * wrong within a day. EXPO_PUBLIC_API_BASE seeds it; Settings overrides it.
 */

const KEYS = {
  baseUrl: 'aria.baseUrl',
  theme: 'aria.theme',
  repUnlocked: 'aria.repUnlocked',
} as const;

export type ThemeMode = 'system' | 'light' | 'dark';

export const DEFAULT_BASE_URL = process.env.EXPO_PUBLIC_API_BASE ?? '';

export async function getBaseUrl(): Promise<string> {
  const stored = await AsyncStorage.getItem(KEYS.baseUrl);
  return normaliseBaseUrl(stored ?? DEFAULT_BASE_URL);
}

export async function setBaseUrl(value: string): Promise<string> {
  const clean = normaliseBaseUrl(value);
  await AsyncStorage.setItem(KEYS.baseUrl, clean);
  return clean;
}

/**
 * Trailing slashes and a missing scheme are the two things people actually
 * paste, and both produce a fetch that fails in a way that looks like the
 * backend is down. Fix them here rather than debugging them later.
 */
export function normaliseBaseUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, '');
  if (!trimmed) return '';
  if (!/^https?:\/\//i.test(trimmed)) return `https://${trimmed}`;
  return trimmed;
}

export async function getThemeMode(): Promise<ThemeMode> {
  const stored = await AsyncStorage.getItem(KEYS.theme);
  return stored === 'light' || stored === 'dark' ? stored : 'system';
}

export async function setThemeMode(mode: ThemeMode): Promise<void> {
  await AsyncStorage.setItem(KEYS.theme, mode);
}

/**
 * Whether the rep screen is revealed. This is a UI affordance, not a security
 * boundary — every backend endpoint is unauthenticated, so anyone who knows an
 * escalation id can already reach it. It exists to keep the customer's app
 * looking like a customer's app.
 */
export async function getRepUnlocked(): Promise<boolean> {
  return (await AsyncStorage.getItem(KEYS.repUnlocked)) === '1';
}

export async function setRepUnlocked(on: boolean): Promise<void> {
  if (on) await AsyncStorage.setItem(KEYS.repUnlocked, '1');
  else await AsyncStorage.removeItem(KEYS.repUnlocked);
}

/** The code that reveals the rep screen. Overridable without a rebuild. */
export const REP_ACCESS_CODE = process.env.EXPO_PUBLIC_REP_CODE ?? '4821';
