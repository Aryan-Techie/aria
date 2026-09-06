import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  View,
} from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { PrimaryButton } from '@/components/PrimaryButton';
import { loadApiBase, ping, setApiBase } from '@/lib/api';
import {
  getBaseUrl,
  getRepUnlocked,
  normaliseBaseUrl,
  REP_ACCESS_CODE,
  setBaseUrl,
  setRepUnlocked,
  type ThemeMode,
} from '@/lib/storage';
import { RADIUS, useTheme } from '@/theme';
import { type } from '@/theme/type';

/**
 * Settings, in the order they are actually needed: the server first, because
 * nothing works without it, then appearance, then — at the very bottom, in the
 * quietest text on the screen — the way in for the one person who is not a
 * customer.
 */
export default function SettingsScreen() {
  const { t, mode, setMode } = useTheme();
  const [url, setUrl] = useState('');
  const [checking, setChecking] = useState(false);
  const [reachable, setReachable] = useState<boolean | null>(null);
  const [unlocked, setUnlocked] = useState(false);
  const [codeOpen, setCodeOpen] = useState(false);
  const [code, setCode] = useState('');
  const [codeWrong, setCodeWrong] = useState(false);

  useEffect(() => {
    void getBaseUrl().then(setUrl);
    void getRepUnlocked().then(setUnlocked);
  }, []);

  const save = async () => {
    setChecking(true);
    setReachable(null);
    const clean = await setBaseUrl(url);
    setUrl(clean);
    setApiBase(clean);
    await loadApiBase();
    // A saved address that cannot be reached is the single most common way
    // this app appears broken, so it is checked here rather than discovered
    // on the call screen.
    setReachable(clean ? await ping(clean) : false);
    setChecking(false);
  };

  const submitCode = async () => {
    if (code.trim() !== REP_ACCESS_CODE) {
      setCodeWrong(true);
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Error);
      return;
    }
    await setRepUnlocked(true);
    setUnlocked(true);
    setCodeOpen(false);
    setCode('');
    setCodeWrong(false);
    void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            paddingHorizontal: 20,
            height: 52,
          }}>
          <Text style={[type.title, { flex: 1, color: t.ink }]}>Settings</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={() => router.back()} hitSlop={12}>
            <Ionicons name="close" size={24} color={t.ink3} />
          </Pressable>
        </View>

        <ScrollView
          contentContainerStyle={{ paddingHorizontal: 20, paddingBottom: 48, gap: 28 }}
          keyboardShouldPersistTaps="handled">
          {/* ------------------------------------------------------ server */}
          <Section title="Server">
            <TextInput
              value={url}
              onChangeText={(next) => {
                setUrl(next);
                setReachable(null);
              }}
              placeholder="https://your-tunnel.trycloudflare.com"
              placeholderTextColor={t.ink3}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              style={[
                type.body,
                {
                  color: t.ink,
                  backgroundColor: t.surface,
                  borderWidth: 1,
                  borderColor: t.line,
                  borderRadius: 12,
                  paddingHorizontal: 14,
                  paddingVertical: 12,
                },
              ]}
            />
            <Text style={[type.tiny, { color: t.ink3 }]}>
              The cloudflared tunnel mints a new address every time the backend restarts. Paste
              PUBLIC_BASE_URL from .env here when it changes.
            </Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
              <PrimaryButton label="Save and test" onPress={save} busy={checking} style={{ minWidth: 0 }} />
              {reachable !== null && (
                <Animated.Text
                  entering={FadeIn.duration(250)}
                  style={[type.small, { color: reachable ? t.goodInk : t.bad, flex: 1 }]}>
                  {reachable ? 'Backend reachable' : 'No answer from that address'}
                </Animated.Text>
              )}
            </View>
          </Section>

          {/* -------------------------------------------------- appearance */}
          <Section title="Appearance">
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {(['system', 'light', 'dark'] as ThemeMode[]).map((option) => (
                <Pressable
                  key={option}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: mode === option }}
                  onPress={() => setMode(option)}
                  style={{
                    flex: 1,
                    alignItems: 'center',
                    paddingVertical: 11,
                    borderRadius: 10,
                    backgroundColor: mode === option ? t.ink : t.surface,
                    borderWidth: 1,
                    borderColor: mode === option ? t.ink : t.line,
                  }}>
                  <Text style={[type.small, { color: mode === option ? t.bg : t.ink2 }]}>
                    {option === 'system' ? 'System' : option === 'light' ? 'Light' : 'Dark'}
                  </Text>
                </Pressable>
              ))}
            </View>
          </Section>

          {/* ------------------------------------------------- the way in */}
          <View style={{ marginTop: 24, gap: 12 }}>
            {unlocked ? (
              <Animated.View entering={FadeIn.duration(250)} style={{ gap: 12 }}>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => router.push('/escalations')}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    gap: 10,
                    backgroundColor: t.surface,
                    borderWidth: 1,
                    borderColor: t.line,
                    borderRadius: RADIUS,
                    paddingVertical: 15,
                    paddingHorizontal: 16,
                  }}>
                  <Ionicons name="people-outline" size={19} color={t.ink2} />
                  <Text style={[type.small, { flex: 1, color: t.ink }]}>Escalations</Text>
                  <Ionicons name="chevron-forward" size={16} color={t.ink3} />
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  onPress={async () => {
                    await setRepUnlocked(false);
                    setUnlocked(false);
                  }}
                  style={{ alignSelf: 'center', paddingVertical: 8 }}>
                  <Text style={[type.tiny, { color: t.ink3 }]}>Turn off rep mode</Text>
                </Pressable>
              </Animated.View>
            ) : codeOpen ? (
              <Animated.View entering={FadeIn.duration(250)} style={{ gap: 10 }}>
                <TextInput
                  value={code}
                  onChangeText={(next) => {
                    setCode(next);
                    setCodeWrong(false);
                  }}
                  onSubmitEditing={submitCode}
                  placeholder="Access code"
                  placeholderTextColor={t.ink3}
                  autoFocus
                  secureTextEntry
                  keyboardType="number-pad"
                  returnKeyType="go"
                  style={[
                    type.body,
                    {
                      color: t.ink,
                      textAlign: 'center',
                      backgroundColor: t.surface,
                      borderWidth: 1,
                      borderColor: codeWrong ? t.bad : t.line,
                      borderRadius: 12,
                      paddingVertical: 12,
                    },
                  ]}
                />
                {codeWrong && (
                  <Text style={[type.tiny, { color: t.bad, textAlign: 'center' }]}>
                    That code does not match.
                  </Text>
                )}
              </Animated.View>
            ) : (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Staff access"
                onPress={() => setCodeOpen(true)}
                style={{ alignSelf: 'center', paddingVertical: 10 }}>
                <Text style={[type.tiny, { color: t.ink3 }]}>Aria · version 1.0.0</Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const { t } = useTheme();
  return (
    <View style={{ gap: 10 }}>
      <Text style={[type.label, { color: t.ink3 }]}>{title}</Text>
      {children}
    </View>
  );
}
