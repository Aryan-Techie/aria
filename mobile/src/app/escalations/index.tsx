import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { FlatList, Pressable, Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { type EscalationRecord } from '@/lib/api';
import { useInboxPoll } from '@/lib/useInboxPoll';
import { timeAgo } from '@/lib/vocab';
import { RADIUS, useTheme } from '@/theme';
import { type } from '@/theme/type';

/**
 * Everyone waiting for a person. Usually nobody.
 *
 * There is no review step here on purpose. A rep opening this screen is
 * opening it because Aria has already decided she cannot finish the call, and
 * the useful thing to do about that is be on the call — not read about it
 * first. So a row has exactly one action.
 */
export default function EscalationsScreen() {
  const { t } = useTheme();
  const { handoffs } = useInboxPoll(true);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: t.bg }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, height: 52, gap: 6 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={12}>
          <Ionicons name="chevron-back" size={26} color={t.ink2} />
        </Pressable>
        <Text style={[type.title, { color: t.ink }]}>Escalations</Text>
      </View>

      {handoffs.length === 0 ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 40 }}>
          <Text style={[type.body, { color: t.ink3, fontStyle: 'italic', textAlign: 'center' }]}>
            Nobody is waiting. Aria will bring you in when she needs you.
          </Text>
        </View>
      ) : (
        <FlatList
          data={handoffs}
          keyExtractor={(item) => item.id}
          contentContainerStyle={{ padding: 20, gap: 12 }}
          renderItem={({ item, index }) => <Row record={item} index={index} />}
        />
      )}
    </SafeAreaView>
  );
}

function Row({ record, index }: { record: EscalationRecord; index: number }) {
  const { t } = useTheme();
  const company = record.left_brain?.company ?? 'A caller';
  // The brief's one-line issue is more use than the raw trigger reason when
  // both are present — it is the sentence a person wrote for a person.
  const line = record.brief?.issue || record.reason;

  return (
    <Animated.View entering={FadeInDown.delay(index * 40).duration(350)}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Join the call with ${company}`}
        onPress={() => router.push(`/escalations/${record.id}`)}
        style={{
          backgroundColor: t.surface,
          borderWidth: 1,
          borderColor: t.line,
          borderRadius: RADIUS,
          padding: 18,
          gap: 12,
        }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: t.bad }} />
          <Text style={[type.title, { flex: 1, color: t.ink }]} numberOfLines={1}>
            {company}
          </Text>
          <Text style={[type.tiny, { color: t.ink3 }]}>{timeAgo(record.created_at)}</Text>
        </View>

        {!!line && (
          <Text style={[type.body, { color: t.ink2 }]} numberOfLines={2}>
            {line}
          </Text>
        )}

        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            backgroundColor: t.ink,
            borderRadius: 999,
            paddingVertical: 12,
          }}>
          <Ionicons name="call" size={16} color={t.bg} />
          <Text style={[type.button, { color: t.bg }]}>Join call</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}
