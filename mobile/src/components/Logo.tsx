import { Image } from 'react-native';

import { useTheme } from '@/theme';

/**
 * The Aria mark.
 *
 * Two inks, one per ground: the dark mark on light, the light mark on dark.
 * The blue is common to both and never changes, so the logo keeps its identity
 * either way rather than becoming a silhouette.
 *
 * Rasterised from the brand SVGs by `npm run icons` — the app has no SVG
 * renderer, and adding one is a native dependency and a rebuild for a picture
 * that never animates.
 *
 * Both sources are resolved unconditionally into constants rather than inside
 * the JSX. `require` returns a Metro asset id, and picking one inside the
 * element let React Compiler treat the whole prop as constant, so the mark
 * kept whichever ink it was first mounted with and disappeared against the
 * other ground.
 */

const ON_LIGHT = require('../../assets/images/logo-on-light.png');
const ON_DARK = require('../../assets/images/logo-on-dark.png');

/** Source is 1313 × 1079. */
const ASPECT = 1313 / 1079;

export function Logo({ width = 34 }: { width?: number }) {
  const { scheme } = useTheme();
  return (
    <Image
      accessibilityRole="image"
      accessibilityLabel="Aria"
      source={scheme === 'dark' ? ON_DARK : ON_LIGHT}
      style={{ width, height: width / ASPECT }}
      resizeMode="contain"
    />
  );
}
