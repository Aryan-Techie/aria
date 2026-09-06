import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Rings } from '@/components/Rings';
import { RoundButton } from '@/components/RoundButton';
import { AgoraCall } from '@/lib/agora';
import { fetchHandoff, HttpError, markRepJoined, type HandoffDetails } from '@/lib/api';
import { useSessionPoll } from '@/lib/useSessionPoll';
import { formatElapsed } from '@/lib/vocab';
import { RADIUS, useTheme, type RingState } from '@/theme';
import { tabular, type } from '@/theme/type';

type Stage = 'loading' | 'joining' | 'handing_over' | 'on_call' | 'gone' | 'error';

const SPEAKING = 0.06;

/**
 * The rep's side of a handoff.
 *
 * Opening this screen is the whole interaction: it fetches the join payload,
 * puts the mic on the channel, and only then tells the backend a person has
 * arrived — because that call is what makes Aria say her closing line and
 * leave (routes/rep.py:81-98), and doing it before the mic is live would hand
 * the customer to somebody they cannot hear.
 *
 * Leaving is client-side only. The backend has no endpoint for a rep hanging
 * up, and the console's own join page does the same thing, so nothing is
 * invented here to fill the gap.
 */
export default function RepCallScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { t } = useTheme();
  const call = useRef(new AgoraCall()).current;

  const [stage, setStage] = useState<Stage>('loading');
  const [details, setDetails] = useState<HandoffDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [levels, setLevels] = useState({ local: 0, remote: 0 });
  const [muted, setMuted] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [briefOpen, setBriefOpen] = useState(false);
  const startedAt = useRef<number | null>(null);
  const lastSpeaker = useRef<RingState>('idle');

  const session = useSessionPoll(details?.session_id ?? null, stage === 'handing_over' || stage === 'on_call');

  /* ------------------------------------------------- fetch, join, announce */
  useEffect(() => {
    if (!id) return;
    let cancelled = false;

    (async () => {
      try {
        const found = await fetchHandoff(id);
        if (cancelled) return;
        setDetails(found);
        setStage('joining');

        await call.join(
          {
            appId: found.rtc.app_id,
            channel: found.rtc.channel,
            token: found.rtc.token,
            uid: found.rtc.uid,
          },
          {
            onJoined: async () => {
              startedAt.current = Date.now();
              try {
                const result = await markRepJoined(id);
                if (cancelled) return;
                setStage(result.status === 'handing_over' ? 'handing_over' : 'on_call');
              } catch {
                // The mic is live either way; the customer can hear us. Show
                // the call rather than an error about the announcement.
                if (!cancelled) setStage('on_call');
              }
            },
            onError: (message) => !cancelled && setError(message),
          }
        );
      } catch (err) {
        if (cancelled) return;
        // 404 here is the ordinary end of a call, not a fault.
        if (err instanceof HttpError && err.status === 404) setStage('gone');
        else {
          setError(err instanceof Error ? err.message : 'Could not join the call.');
          setStage('error');
        }
      }
    })();

    return () => {
      cancelled = true;
      call.leave();
    };
  }, [id, call]);

  // Aria's departure is the moment the call is fully the rep's.
  useEffect(() => {
    if (session.ariaLeft && stage === 'handing_over') setStage('on_call');
  }, [session.ariaLeft, stage]);

  useEffect(() => {
    if (stage !== 'handing_over' && stage !== 'on_call') return;
    const levelTimer = setInterval(() => setLevels(call.getLevels()), 120);
    const clockTimer = setInterval(() => {
      if (startedAt.current) setElapsed(Date.now() - startedAt.current);
    }, 500);
    return () => {
      clearInterval(levelTimer);
      clearInterval(clockTimer);
    };
  }, [stage, call]);

  const hangUp = () => {
    call.leave();
    router.back();
  };

  /* ---------------------------------------------------------- empty states */
  if (stage === 'gone' || stage === 'error') {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
        <Header onBack={() => router.back()} title="" />
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 20, paddingHorizontal: 40 }}>
          <Text style={[type.body, { color: t.ink3, fontStyle: 'italic', textAlign: 'center' }]}>
            {stage === 'gone' ? 'That call has already ended.' : (error ?? 'Could not join the call.')}
          </Text>
          <Pressable onPress={() => router.back()} hitSlop={10}>
            <Text style={[type.small, { color: t.aria }]}>Back to escalations</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const remoteSpeaking = levels.remote > SPEAKING;
  const localSpeaking = levels.local > SPEAKING;
  if (remoteSpeaking) lastSpeaker.current = 'you';
  else if (localSpeaking) lastSpeaker.current = 'aria';

  const ringState: RingState = stage === 'loading' || stage === 'joining' ? 'idle' : lastSpeaker.current;

  const caption =
    stage === 'loading'
      ? 'Opening the call…'
      : stage === 'joining'
        ? 'Connecting…'
        : stage === 'handing_over'
          ? 'Aria is handing over…'
          : 'You have the call';

  const company = details?.lead?.company ?? 'A caller';

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <Header onBack={hangUp} title={company} elapsed={stage === 'on_call' || stage === 'handing_over' ? formatElapsed(elapsed) : null} />

      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 36 }}>
        <Rings state={ringState} level={Math.max(levels.local, levels.remote)} size={230} />
        <Text
          accessibilityLiveRegion="polite"
          style={[
            type.caption,
            {
              color: stage === 'on_call' ? t.ink2 : t.ink3,
              fontStyle: stage === 'on_call' ? 'normal' : 'italic',
              textAlign: 'center',
            },
          ]}>
          {caption}
        </Text>
      </View>

      {details && <Brief details={details} open={briefOpen} onToggle={() => setBriefOpen((v) => !v)} />}

      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 18, paddingBottom: 40, paddingTop: 12 }}>
        <RoundButton
          icon={muted ? 'mic-off' : 'mic'}
          label={muted ? 'Unmute' : 'Mute'}
          active={muted}
          disabled={stage === 'loading' || stage === 'joining'}
          onPress={() => {
            const next = !muted;
            setMuted(next);
            call.setMuted(next);
          }}
        />
        <RoundButton icon="call" label="Leave call" destructive onPress={hangUp} />
      </View>
    </SafeAreaView>
  );
}

function Header({
  onBack,
  title,
  elapsed,
}: {
  onBack: () => void;
  title: string;
  elapsed?: string | null;
}) {
  const { t } = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, height: 52, gap: 6 }}>
      <Pressable accessibilityRole="button" accessibilityLabel="Leave" onPress={onBack} hitSlop={12}>
        <Ionicons name="chevron-back" size={26} color={t.ink2} />
      </Pressable>
      <Text style={[type.title, { flex: 1, color: t.ink }]} numberOfLines={1}>
        {title}
      </Text>
      {!!elapsed && <Text style={[type.small, tabular, { color: t.ink3 }]}>{elapsed}</Text>}
    </View>
  );
}

/**
 * One line by default — why you are here — with everything Aria knew folded
 * behind it. The full brief arrives in the same payload as the join token, so
 * showing it costs nothing; keeping it closed costs nothing either, and a
 * person who has just picked up a live call should not have to read first.
 */
function Brief({
  details,
  open,
  onToggle,
}: {
  details: HandoffDetails;
  open: boolean;
  onToggle: () => void;
}) {
  const { t } = useTheme();
  const rows: [string, string | null | undefined][] = [
    ['Blocker', details.brief?.blocker],
    ['Suggested', details.brief?.recommended_action],
    ['Devices', details.lead?.user_count ? String(details.lead.user_count) : null],
    ['Budget', details.lead?.budget_range],
    ['Timeline', details.lead?.timeline],
  ];
  const shown = rows.filter(([, value]) => !!value);

  return (
    <Animated.View entering={FadeIn.duration(350)} style={{ paddingHorizontal: 20 }}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={onToggle}
        style={{
          backgroundColor: t.surface,
          borderWidth: 1,
          borderColor: t.line,
          borderRadius: RADIUS,
          paddingVertical: 14,
          paddingHorizontal: 16,
          gap: 12,
        }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Text style={[type.small, { flex: 1, color: t.ink2 }]} numberOfLines={open ? undefined : 1}>
            {details.brief?.issue || details.reason}
          </Text>
          <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={t.ink3} />
        </View>

        {open && shown.length > 0 && (
          <Animated.View entering={FadeInDown.duration(250)} style={{ gap: 10 }}>
            <ScrollView style={{ maxHeight: 190 }} nestedScrollEnabled>
              <View style={{ gap: 10 }}>
                {shown.map(([label, value]) => (
                  <View key={label} style={{ gap: 3 }}>
                    <Text style={[type.label, { color: t.ink3 }]}>{label}</Text>
                    <Text style={[type.small, { color: t.ink }]}>{value}</Text>
                  </View>
                ))}
              </View>
            </ScrollView>
          </Animated.View>
        )}
      </Pressable>
    </Animated.View>
  );
}
