import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { Pressable } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';

import { DURATION, EASE, useTheme } from '@/theme';

/**
 * The 44px circular call control: mute, hold, end.
 *
 * Three states, matching the console's `.round` variants — resting (surface
 * with a hairline), `on` (inverted ink, for an active mute or hold), and
 * `end` (solid red, the one place a semantic colour is allowed to be a fill).
 */

const EASING = Easing.bezier(...EASE);

export function RoundButton({
  icon,
  onPress,
  active = false,
  destructive = false,
  disabled = false,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  active?: boolean;
  destructive?: boolean;
  disabled?: boolean;
  label: string;
}) {
  const { t, scheme } = useTheme();
  const scale = useSharedValue(1);
  const animated = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));

  const background = destructive ? t.bad : active ? t.ink : t.surface;
  const tint = destructive ? '#fff' : active ? (scheme === 'dark' ? '#000' : t.bg) : t.ink;

  return (
    <Animated.View style={animated}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        accessibilityState={{ selected: active, disabled }}
        disabled={disabled}
        onPressIn={() => {
          scale.value = withTiming(0.94, { duration: DURATION.press, easing: EASING });
        }}
        onPressOut={() => {
          scale.value = withTiming(1, { duration: DURATION.press, easing: EASING });
        }}
        onPress={() => {
          void Haptics.impactAsync(
            destructive ? Haptics.ImpactFeedbackStyle.Medium : Haptics.ImpactFeedbackStyle.Light
          );
          onPress();
        }}
        style={[
          {
            width: 56,
            height: 56,
            borderRadius: 28,
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: background,
            borderWidth: destructive || active ? 0 : 1,
            borderColor: t.line,
            opacity: disabled ? 0.45 : 1,
          },
          t.shadow,
        ]}>
        <Ionicons name={icon} size={22} color={tint} />
      </Pressable>
    </Animated.View>
  );
}
