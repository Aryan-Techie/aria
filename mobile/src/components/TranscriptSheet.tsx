import BottomSheet, { BottomSheetFlatList, BottomSheetView } from '@gorhom/bottom-sheet';
import { useEffect, useMemo, useRef } from 'react';
import { Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '@/theme';
import { type } from '@/theme/type';
import type { CallNote, Turn } from '@/lib/useSessionPoll';
import { Pill, type Tone } from './Pill';

/**
 * The transcript, kept out of the way.
 *
 * This is the app's progressive disclosure in one component: during a call the
 * screen is the rings and three controls, and the conversation peeks from the
 * bottom as a handle you can drag up if you want it. Nothing is hidden, but
 * nothing competes with the call either.
 *
 * The rows follow the console's format rather than a messaging app's: a small
 * role marker and the text, no bubbles, no avatars, no alternating sides.
 * Aria's words sit in full-strength ink and the customer's in secondary,
 * because the thing being demonstrated is what Aria said.
 */

type Row =
  | { kind: 'turn'; key: string; turn: Turn }
  | { kind: 'note'; key: string; note: CallNote };

export function TranscriptSheet({ turns, notes }: { turns: Turn[]; notes: CallNote[] }) {
  const { t } = useTheme();
  const insets = useSafeAreaInsets();
  const ref = useRef<BottomSheet>(null);
  const listRef = useRef<React.ComponentRef<typeof BottomSheetFlatList<Row>>>(null);

  // The collapsed detent has to clear the gesture bar as well as show the
  // label and the first line, or the peek reads as a rendering fault rather
  // than an invitation to drag.
  const collapsed = 118 + insets.bottom;

  const rows = useMemo<Row[]>(() => {
    const asTurns: Row[] = turns.map((turn) => ({ kind: 'turn', key: turn.id, turn }));
    const asNotes: Row[] = notes.map((note) => ({ kind: 'note', key: note.id, note }));
    return [...asTurns, ...asNotes];
  }, [turns, notes]);

  // Follow the conversation. Unlike the console this does not try to detect an
  // upward scroll and hold position — on a sheet you are usually holding it
  // open precisely because you want the latest line.
  useEffect(() => {
    if (rows.length === 0) return;
    const timer = setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(timer);
  }, [rows.length]);

  return (
    <BottomSheet
      ref={ref}
      index={0}
      snapPoints={[collapsed, '52%', '92%']}
      enablePanDownToClose={false}
      backgroundStyle={{ backgroundColor: t.surface }}
      handleIndicatorStyle={{ backgroundColor: t.ink3 }}
      style={{
        shadowColor: '#000',
        shadowOffset: { width: 0, height: -8 },
        shadowOpacity: 0.08,
        shadowRadius: 24,
        elevation: 8,
      }}>
      <BottomSheetView style={{ paddingHorizontal: 20, paddingBottom: 6 }}>
        <Text style={[type.label, { color: t.ink3 }]}>Transcript</Text>
      </BottomSheetView>

      {rows.length === 0 ? (
        <BottomSheetView
          style={{ paddingHorizontal: 20, paddingTop: 10, paddingBottom: insets.bottom + 16 }}>
          <Text style={[type.body, { color: t.ink3, fontStyle: 'italic' }]}>
            What you both say will appear here.
          </Text>
        </BottomSheetView>
      ) : (
        <BottomSheetFlatList
          ref={listRef}
          data={rows}
          keyExtractor={(row) => row.key}
          contentContainerStyle={{
            paddingHorizontal: 20,
            paddingBottom: insets.bottom + 40,
            gap: 14,
          }}
          renderItem={({ item }) =>
            item.kind === 'turn' ? <TurnRow turn={item.turn} /> : <NoteRow note={item.note} />
          }
        />
      )}
    </BottomSheet>
  );
}

function TurnRow({ turn }: { turn: Turn }) {
  const { t } = useTheme();
  const isAria = turn.role === 'assistant';
  return (
    <Animated.View entering={FadeInDown.duration(350)} style={{ flexDirection: 'row', gap: 12 }}>
      <View style={{ width: 46, flexDirection: 'row', alignItems: 'center', gap: 5, paddingTop: 5 }}>
        <View
          style={{
            width: 6,
            height: 6,
            borderRadius: 3,
            backgroundColor: isAria ? t.aria : t.you,
          }}
        />
        <Text style={[type.role, { color: t.ink3 }]}>{isAria ? 'Aria' : 'You'}</Text>
      </View>
      <Text style={[type.body, { flex: 1, color: isAria ? t.ink : t.ink2 }]}>{turn.text}</Text>
    </Animated.View>
  );
}

/**
 * A moment rather than a sentence — a meeting booked, a person brought in.
 * Printed inline so the transcript reads as a record of the whole call and not
 * just the words.
 */
function NoteRow({ note }: { note: CallNote }) {
  return (
    <Animated.View entering={FadeInDown.duration(350)} style={{ paddingLeft: 58 }}>
      <Pill tone={note.tone as Tone}>{note.text}</Pill>
    </Animated.View>
  );
}
