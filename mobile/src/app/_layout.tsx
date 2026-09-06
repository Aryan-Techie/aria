import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { loadApiBase } from '@/lib/api';
import { ThemeProvider, useTheme } from '@/theme';
import {
  InstrumentSerif_400Regular,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
} from '@/theme/type';

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [fontsReady] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    InstrumentSerif_400Regular,
  });

  useEffect(() => {
    // The stored base URL has to be in place before any screen can fetch.
    loadApiBase().finally(() => {
      if (fontsReady) SplashScreen.hideAsync();
    });
  }, [fontsReady]);

  if (!fontsReady) return null;

  return (
    <ThemeProvider>
      <GestureHandlerRootView style={{ flex: 1 }}>
        <Chrome />
      </GestureHandlerRootView>
    </ThemeProvider>
  );
}

/**
 * Split out so it sits inside ThemeProvider and can colour the native stack.
 * Screens are pushed, not tabbed: the call is the app, and everything else is
 * somewhere you go and come back from.
 */
function Chrome() {
  const { t, scheme } = useTheme();
  return (
    <>
      <StatusBar style={scheme === 'dark' ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerShown: false,
          contentStyle: { backgroundColor: t.bg },
          animation: 'slide_from_right',
        }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="settings" options={{ presentation: 'modal' }} />
        <Stack.Screen name="escalations/index" />
        <Stack.Screen name="escalations/[id]" />
      </Stack>
    </>
  );
}
