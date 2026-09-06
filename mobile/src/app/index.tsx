import { Ionicons } from '@expo/vector-icons';
import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import Animated, { FadeIn, FadeInDown } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Caption } from '@/components/Caption';
import { Logo } from '@/components/Logo';
import { Pill, StatusChip, type CallPhase } from '@/components/Pill';
import { PrimaryButton } from '@/components/PrimaryButton';
import { Rings } from '@/components/Rings';
import { RoundButton } from '@/components/RoundButton';
import { TranscriptSheet } from '@/components/TranscriptSheet';
import { AgoraCall } from '@/lib/agora';
import { endCall, fetchSummary, getApiBase, startCall, type CallSummary } from '@/lib/api';
import { getRepUnlocked } from '@/lib/storage';
import { useInboxPoll } from '@/lib/useInboxPoll';
import { useSessionPoll } from '@/lib/useSessionPoll';
import { formatElapsed, outcomeLabel, outcomeTone } from '@/lib/vocab';
import { useTheme, type RingState } from '@/theme';
import { tabular, type } from '@/theme/type';

type Status = 'idle' | 'connecting' | 'active' | 'ending' | 'ended';

/** Below this, a level is room noise rather than someone talking. */
const SPEAKING = 0.06;

export default function CallScreen() {
  const { t } = useTheme();
  const call = useRef(new AgoraCall()).current;

  const [status, setStatus] = useState<Status>('idle');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [levels, setLevels] = useState({ local: 0, remote: 0 });
  const [muted, setMuted] = useState(false);
  const [held, setHeld] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [summary, setSummary] = useState<CallSummary | null>(null);
  const [endedOutcome, setEndedOutcome] = useState<string | null>(null);
  const [repUnlocked, setRepUnlocked] = useState(false);
  const startedAt = useRef<number | null>(null);
  const lastSpeaker = useRef<RingState>('idle');

  const session = useSessionPoll(sessionId, status === 'active');
  const { handoffs, fresh, clearFresh } = useInboxPoll(repUnlocked);

  // The hidden screen can be switched on while this one is mounted, so the
  // flag is re-read every time the call screen comes back into focus.
  useFocusEffect(
    useCallback(() => {
      void getRepUnlocked().then(setRepUnlocked);
    }, [])
  );

  /* --------------------------------------------------------------- levels */
  useEffect(() => {
    if (status !== 'active' && status !== 'connecting') return;
    const timer = setInterval(() => setLevels(call.getLevels()), 120);
    return () => clearInterval(timer);
  }, [status, call]);

  /* ---------------------------------------------------------------- clock */
  useEffect(() => {
    if (status !== 'active') return;
    const timer = setInterval(() => {
      if (startedAt.current) setElapsed(Date.now() - startedAt.current);
    }, 500);
    return () => clearInterval(timer);
  }, [status]);

  /* -------------------------------------------------------------- wrap-up */
  useEffect(() => {
    if (status !== 'ended' || !sessionId || summary) return;
    let cancelled = false;
    let tries = 0;
    // The wrap-up costs a model call and is written after /end returns, so it
    // 404s for a few seconds. Twenty tries at 1.5s matches the console.
    const timer = setInterval(async () => {
      if (cancelled || tries >= 20) return clearInterval(timer);
      tries += 1;
      try {
        const found = await fetchSummary(sessionId);
        if (found && !cancelled) {
          setSummary(found);
          clearInterval(timer);
        }
      } catch {
        // Keep trying; a missing headline is not worth an error state.
      }
    }, 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [status, sessionId, summary]);

  /* ------------------------------------------------------------ the call */
  const onStart = async () => {
    if (!getApiBase()) {
      setError('No server address set. Open Settings and paste the backend URL.');
      return;
    }
    setError(null);
    setSummary(null);
    setEndedOutcome(null);
    setElapsed(0);
    setMuted(false);
    setHeld(false);
    lastSpeaker.current = 'idle';
    setStatus('connecting');

    try {
      // Any previous engine must be gone before a new one is created, or the
      // second call joins with a stale connection still holding the mic.
      call.leave();
      const started = await startCall();
      setSessionId(started.session_id);
      startedAt.current = Date.now();
      await call.join(
        {
          appId: started.app_id,
          channel: started.channel_name,
          token: started.rtc_token,
          uid: started.uid,
        },
        {
          onJoined: () => setStatus('active'),
          onError: (message) => setError(message),
        }
      );
    } catch (err) {
      call.leave();
      setStatus('idle');
      setError(err instanceof Error ? err.message : 'Could not start the call.');
    }
  };

  const onEnd = async () => {
    setStatus('ending');
    call.leave();
    try {
      const ended = sessionId ? await endCall(sessionId) : null;
      setEndedOutcome(ended?.outcome ?? session.outcome);
    } catch {
      setEndedOutcome(session.outcome);
    }
    setStatus('ended');
  };

  /* ----------------------------------------------------------- what shows */
  const phase: CallPhase =
    status === 'idle' ? 'idle' : status === 'connecting' ? 'connecting' : status === 'ended' ? 'ended' : 'live';

  const ariaSpeaking = levels.remote > SPEAKING;
  const youSpeaking = levels.local > SPEAKING;
  if (ariaSpeaking) lastSpeaker.current = 'aria';
  else if (youSpeaking) lastSpeaker.current = 'you';

  const ringState: RingState =
    status === 'idle' || status === 'connecting'
      ? 'idle'
      : status === 'ended'
        ? 'ended'
        : held
          ? 'hold'
          : session.busyTool
            ? 'think'
            : lastSpeaker.current;

  const live = status === 'active' || status === 'connecting' || status === 'ending';

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      {/* Top bar: only the chip, and the way out to Settings when idle. */}
      <View
        style={{
          height: 52,
          paddingHorizontal: 20,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
        <View style={{ position: 'absolute', left: 20 }}>
          <Logo width={30} />
        </View>
        <StatusChip phase={phase} elapsed={live || status === 'ended' ? formatElapsed(elapsed) : null} />
        {/* Reachable whenever there is no call to interrupt — which includes
            after one has ended, or Settings is unreachable without a restart. */}
        {(status === 'idle' || status === 'ended') && (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Settings"
            onPress={() => router.push('/settings')}
            hitSlop={12}
            style={{ position: 'absolute', right: 20 }}>
            <Ionicons name="ellipsis-horizontal" size={22} color={t.ink3} />
          </Pressable>
        )}
      </View>

      {repUnlocked && handoffs.length > 0 && (
        <HandoffBanner
          count={handoffs.length}
          hasFresh={fresh.size > 0}
          onPress={() => {
            clearFresh();
            router.push('/escalations');
          }}
        />
      )}

      {/* The call itself. Nothing else competes with it. */}
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 40 }}>
        <Rings state={ringState} level={Math.max(levels.local, levels.remote)} size={status === 'idle' ? 300 : 230} />

        {status === 'ended' ? (
          <EndCard outcome={endedOutcome ?? session.outcome} summary={summary} elapsed={elapsed} />
        ) : (
          <Caption
            large={status === 'idle'}
            state={{
              error,
              phase: status,
              muted,
              held,
              repOnCall: session.repOnCall,
              busyTool: session.busyTool,
              ariaSpeaking,
              youSpeaking,
              endedFor: null,
            }}
          />
        )}
      </View>

      {/* Controls sit above the sheet's resting height while a call is live. */}
      <View
        style={{
          alignItems: 'center',
          paddingBottom: live ? 120 : 48,
          paddingTop: 8,
        }}>
        {status === 'idle' || status === 'ended' ? (
          <PrimaryButton label={status === 'ended' ? 'New call' : 'Start call'} onPress={onStart} />
        ) : (
          <View style={{ flexDirection: 'row', gap: 18 }}>
            <RoundButton
              icon={muted ? 'mic-off' : 'mic'}
              label={muted ? 'Unmute' : 'Mute'}
              active={muted}
              disabled={status !== 'active' || held}
              onPress={() => {
                const next = !muted;
                setMuted(next);
                call.setMuted(next);
              }}
            />
            <RoundButton
              icon={held ? 'play' : 'pause'}
              label={held ? 'Resume' : 'Hold'}
              active={held}
              disabled={status !== 'active'}
              onPress={() => {
                const next = !held;
                setHeld(next);
                call.setHold(next);
                setMuted(next);
              }}
            />
            <RoundButton
              icon="call"
              label="End call"
              destructive
              disabled={status === 'ending'}
              onPress={onEnd}
            />
          </View>
        )}
      </View>

      {live && <TranscriptSheet turns={session.turns} notes={session.notes} />}
    </SafeAreaView>
  );
}

/**
 * The end of the call, as one card. The outcome and the duration are known
 * immediately; the headline is the one line written for a person rather than
 * read off a record, so it arrives a beat later and is the only serif in the
 * app.
 */
function EndCard({
  outcome,
  summary,
  elapsed,
}: {
  outcome: string | null;
  summary: CallSummary | null;
  elapsed: number;
}) {
  const { t } = useTheme();
  return (
    <Animated.View
      entering={FadeIn.duration(500)}
      style={{ alignItems: 'center', gap: 16, paddingHorizontal: 32 }}>
      <Pill tone={outcomeTone(outcome)}>{outcomeLabel(outcome)}</Pill>
      <Text style={[type.small, tabular, { color: t.ink3 }]}>{formatElapsed(elapsed)}</Text>
      {summary ? (
        <Animated.Text
          entering={FadeInDown.duration(500)}
          style={[type.headline, { color: t.ink, textAlign: 'center' }]}>
          {summary.headline}
        </Animated.Text>
      ) : (
        <Text style={[type.body, { color: t.ink3, fontStyle: 'italic', textAlign: 'center' }]}>
          Writing the wrap-up…
        </Text>
      )}
    </Animated.View>
  );
}

/** Quiet until it matters, then it is the only coloured thing on the screen. */
function HandoffBanner({
  count,
  hasFresh,
  onPress,
}: {
  count: number;
  hasFresh: boolean;
  onPress: () => void;
}) {
  const { t } = useTheme();
  return (
    <Animated.View entering={FadeInDown.duration(350)} style={{ paddingHorizontal: 20 }}>
      <Pressable
        accessibilityRole="button"
        onPress={onPress}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 10,
          backgroundColor: hasFresh ? t.badSoft : t.surface,
          borderWidth: 1,
          borderColor: hasFresh ? 'rgba(255,59,48,0.4)' : t.line,
          borderRadius: 14,
          paddingVertical: 11,
          paddingHorizontal: 14,
        }}>
        <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: t.bad }} />
        <Text style={[type.small, { color: t.ink, flex: 1 }]}>
          {count === 1 ? 'A customer is waiting' : `${count} customers are waiting`}
        </Text>
        <Ionicons name="chevron-forward" size={16} color={t.ink3} />
      </Pressable>
    </Animated.View>
  );
}
