import { ActivityIndicator, Pressable, Text, ViewStyle } from 'react-native';
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withTiming,
  Easing,
} from 'react-native-reanimated';

import { DURATION, EASE, useTheme } from '@/theme';
import { type } from '@/theme/type';

/**
 * The pill button: ink ground, page-coloured label, inverted in dark.
 *
 * Feedback is on the press, not the release — the console is explicit about
 * this (DESIGN.md, `.primary:active { scale(.97) }`) and it is most of what
 * makes a button feel attached to the finger.
 */

const EASING = Easing.bezier(...EASE);

export function PrimaryButton({
  label,
  onPress,
  busy = false,
  disabled = false,
  style,
}: {
  label: string;
  onPress: () => void;
  busy?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
}) {
  const { t, scheme } = useTheme();
  const scale = useSharedValue(1);
  const animated = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const off = disabled || busy;

  return (
    <Animated.View style={animated}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: off, busy }}
        disabled={off}
        onPressIn={() => {
          scale.value = withTiming(0.97, { duration: DURATION.press, easing: EASING });
        }}
        onPressOut={() => {
          scale.value = withTiming(1, { duration: DURATION.press, easing: EASING });
        }}
        onPress={onPress}
        style={[
          {
            backgroundColor: t.ink,
            paddingVertical: 14,
            paddingHorizontal: 30,
            borderRadius: 999,
            minWidth: 168,
            alignItems: 'center',
            justifyContent: 'center',
            opacity: off ? 0.45 : 1,
          },
          t.shadow,
          style,
        ]}>
        {busy ? (
          <ActivityIndicator color={t.bg} size="small" />
        ) : (
          <Text style={[type.button, { color: scheme === 'dark' ? '#000' : t.bg }]}>{label}</Text>
        )}
      </Pressable>
    </Animated.View>
  );
}
