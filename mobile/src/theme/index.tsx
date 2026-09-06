import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { useColorScheme } from 'react-native';

import { getThemeMode, setThemeMode, type ThemeMode } from '@/lib/storage';
import { themes, type Theme } from './tokens';

export * from './tokens';

type ThemeContextValue = {
  t: Theme;
  /** Resolved appearance, after the system preference and the override. */
  scheme: 'light' | 'dark';
  /** What the user picked. `system` follows the OS, like the console does. */
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>('system');

  useEffect(() => {
    getThemeMode().then(setModeState);
  }, []);

  const value = useMemo<ThemeContextValue>(() => {
    const scheme = mode === 'system' ? (system === 'dark' ? 'dark' : 'light') : mode;
    return {
      t: themes[scheme],
      scheme,
      mode,
      setMode: (next: ThemeMode) => {
        setModeState(next);
        void setThemeMode(next);
      },
    };
  }, [mode, system]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside ThemeProvider');
  return ctx;
}
