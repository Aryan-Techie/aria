/**
 * Renders every raster the app needs from the two brand SVGs at the repo root.
 *
 * The two source files are the same artwork in two inks: dark.svg is
 * #1A1B1F and belongs on a light ground, light.svg is #E5E4E0 and belongs on a
 * dark one. The blue (#469CFE) is shared and never changes.
 *
 * Run with `npm run icons` after either SVG changes. Everything it writes is
 * derived, so it is safe to delete and regenerate.
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, '..', '..');
const out = join(here, '..', 'assets', 'images');

const INK_DARK = '#1A1B1F';
const INK_LIGHT = '#E5E4E0';

/** The mark's own aspect ratio, from the source viewBox. */
const ASPECT = 1313 / 1079;

async function loadMark(file, recolour) {
  let svg = await readFile(join(repo, file), 'utf8');
  if (recolour) {
    svg = svg.replaceAll(`fill="${INK_DARK}"`, `fill="${recolour}"`);
    svg = svg.replaceAll(`fill="${INK_LIGHT}"`, `fill="${recolour}"`);
  }
  return Buffer.from(svg);
}

/** Renders the mark at a given width, preserving its aspect. */
function render(svg, width) {
  return sharp(svg, { density: 400 })
    .resize({ width: Math.round(width), height: Math.round(width / ASPECT), fit: 'contain' })
    .png()
    .toBuffer();
}

/** Centres a rendered mark on a square canvas, transparent or filled. */
async function square(mark, size, background) {
  return sharp({
    create: {
      width: size,
      height: size,
      channels: 4,
      background: background ?? { r: 0, g: 0, b: 0, alpha: 0 },
    },
  })
    .composite([{ input: mark, gravity: 'centre' }])
    .png()
    .toBuffer();
}

async function write(name, buffer) {
  await writeFile(join(out, name), buffer);
  console.log(`wrote ${name}`);
}

async function main() {
  await mkdir(out, { recursive: true });

  const onDark = await loadMark('light.svg'); // light ink, for dark grounds
  const onLight = await loadMark('dark.svg'); // dark ink, for light grounds
  const white = await loadMark('dark.svg', '#FFFFFF'); // silhouette for themed icons

  // Launcher icon: the light mark on the brand's near-black, so it reads the
  // same whichever wallpaper it lands on.
  await write('icon.png', await square(await render(onDark, 700), 1024, INK_DARK));

  // Adaptive icon. The foreground is masked to roughly the middle two thirds,
  // so the mark is drawn smaller than it is on the flat icon.
  await write('android-icon-foreground.png', await square(await render(onDark, 560), 1024));
  await write(
    'android-icon-background.png',
    await sharp({ create: { width: 1024, height: 1024, channels: 4, background: INK_DARK } })
      .png()
      .toBuffer()
  );
  await write('android-icon-monochrome.png', await square(await render(white, 560), 1024));

  // Splash. One per theme, because the splash ground follows the system and a
  // single ink would vanish on one of them.
  await write('splash-icon.png', await square(await render(onLight, 400), 512));
  await write('splash-icon-dark.png', await square(await render(onDark, 400), 512));

  // In-app wordmark, at 3x for the densest screens we care about.
  await write('logo-on-light.png', await render(onLight, 420));
  await write('logo-on-dark.png', await render(onDark, 420));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
