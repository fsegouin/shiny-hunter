/**
 * Pokemon Red/Blue bitmap font renderer for the browser.
 *
 * Loads three 1bpp tile sheets shipped under /public/gbfont/:
 *   - pokered_font.png       — tiles 0x80-0xFF (A-Z, a-z, digits, punctuation)
 *   - pokered_font_extra.png — tiles 0x60-0x7F (border tiles, space, bold)
 *   - shiny_icon.png         — Crystal's shiny sparkle, mapped to tile 0x3F
 *
 * Mirrors `src/shiny_hunter/gbfont.py` so the web monitor textbox looks
 * identical to the Python one.
 */

const TILE_SIZE = 8;
const FONT_COLS = 16;
export const GB_SCREEN_TILES_W = 20;

export const SHINY_CHAR = '⁂'; // ⁂

const CHARMAP: Record<string, number> = {
  A: 0x80, B: 0x81, C: 0x82, D: 0x83, E: 0x84,
  F: 0x85, G: 0x86, H: 0x87, I: 0x88, J: 0x89,
  K: 0x8a, L: 0x8b, M: 0x8c, N: 0x8d, O: 0x8e,
  P: 0x8f, Q: 0x90, R: 0x91, S: 0x92, T: 0x93,
  U: 0x94, V: 0x95, W: 0x96, X: 0x97, Y: 0x98,
  Z: 0x99,
  '(': 0x9a, ')': 0x9b, ':': 0x9c, ';': 0x9d, '[': 0x9e, ']': 0x9f,
  a: 0xa0, b: 0xa1, c: 0xa2, d: 0xa3, e: 0xa4,
  f: 0xa5, g: 0xa6, h: 0xa7, i: 0xa8, j: 0xa9,
  k: 0xaa, l: 0xab, m: 0xac, n: 0xad, o: 0xae,
  p: 0xaf, q: 0xb0, r: 0xb1, s: 0xb2, t: 0xb3,
  u: 0xb4, v: 0xb5, w: 0xb6, x: 0xb7, y: 0xb8,
  z: 0xb9,
  "'": 0xe0,
  '-': 0xe3,
  '?': 0xe6, '!': 0xe7, '.': 0xe8,
  '/': 0xf3, ',': 0xf4,
  '0': 0xf6, '1': 0xf7, '2': 0xf8, '3': 0xf9, '4': 0xfa,
  '5': 0xfb, '6': 0xfc, '7': 0xfd, '8': 0xfe, '9': 0xff,
  ' ': 0x7f,
  '=': 0xe3,
  [SHINY_CHAR]: 0x3f,
};

const BORDER_TL = 0x79;
const BORDER_H = 0x7a;
const BORDER_TR = 0x7b;
const BORDER_V = 0x7c;
const BORDER_BL = 0x7d;
const BORDER_BR = 0x7e;

interface Tile {
  /** Length 64; each entry is the grayscale byte (0-255). */
  pixels: Uint8ClampedArray;
}

let tilesPromise: Promise<Map<number, Tile>> | null = null;

async function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = (e) => reject(e);
    img.src = src;
  });
}

function imageToTiles(
  img: HTMLImageElement,
  startTileIdx: number,
  out: Map<number, Tile>,
): void {
  const cols = Math.floor(img.width / TILE_SIZE);
  const rows = Math.floor(img.height / TILE_SIZE);
  const canvas = document.createElement('canvas');
  canvas.width = img.width;
  canvas.height = img.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2d context unavailable');
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, img.width, img.height).data;

  for (let i = 0; i < cols * rows; i++) {
    const tx = (i % FONT_COLS) * TILE_SIZE;
    const ty = Math.floor(i / FONT_COLS) * TILE_SIZE;
    const pixels = new Uint8ClampedArray(TILE_SIZE * TILE_SIZE);
    for (let y = 0; y < TILE_SIZE; y++) {
      for (let x = 0; x < TILE_SIZE; x++) {
        const srcIdx = ((ty + y) * img.width + (tx + x)) * 4;
        // Read luminance from the red channel (image is grayscale).
        pixels[y * TILE_SIZE + x] = data[srcIdx];
      }
    }
    out.set(startTileIdx + i, { pixels });
  }
}

async function loadTiles(): Promise<Map<number, Tile>> {
  if (tilesPromise) return tilesPromise;
  tilesPromise = (async () => {
    const tiles = new Map<number, Tile>();
    const [main, extra, shiny] = await Promise.all([
      loadImage('/gbfont/pokered_font.png'),
      loadImage('/gbfont/pokered_font_extra.png'),
      loadImage('/gbfont/shiny_icon.png'),
    ]);
    imageToTiles(main, 0x80, tiles);
    imageToTiles(extra, 0x60, tiles);
    imageToTiles(shiny, 0x3f, tiles);
    return tiles;
  })();
  return tilesPromise;
}

/** Pre-load the font assets. Resolves once tiles are decoded and cached. */
export function preloadFont(): Promise<void> {
  return loadTiles().then(() => undefined);
}

function getTile(tiles: Map<number, Tile>, idx: number): Tile {
  return tiles.get(idx) ?? tiles.get(0x7f)!;
}

/**
 * Render lines of text inside a Pokémon-style bordered text box.
 *
 * Returns an offscreen canvas at unscaled tile resolution: width is
 * `widthTiles * 8` pixels, height is `(lines.length + 2) * 8` pixels.
 * Pixels are RGB grayscale (0 = black, 255 = white). The caller can scale
 * with NEAREST sampling and composite over a screen.
 */
export async function renderTextbox(
  lines: string[],
  widthTiles?: number,
): Promise<HTMLCanvasElement> {
  const tiles = await loadTiles();
  const maxLen = lines.reduce((m, l) => Math.max(m, l.length), 0);
  const totalW = widthTiles ?? maxLen + 4;
  const totalH = lines.length + 2;

  const canvas = document.createElement('canvas');
  canvas.width = totalW * TILE_SIZE;
  canvas.height = totalH * TILE_SIZE;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2d context unavailable');

  const imageData = ctx.createImageData(canvas.width, canvas.height);
  const buf = imageData.data;
  // Fill white.
  for (let i = 0; i < buf.length; i += 4) {
    buf[i] = 255;
    buf[i + 1] = 255;
    buf[i + 2] = 255;
    buf[i + 3] = 255;
  }

  const paste = (tileIdx: number, tx: number, ty: number) => {
    const tile = getTile(tiles, tileIdx);
    const px = tx * TILE_SIZE;
    const py = ty * TILE_SIZE;
    for (let y = 0; y < TILE_SIZE; y++) {
      for (let x = 0; x < TILE_SIZE; x++) {
        const v = tile.pixels[y * TILE_SIZE + x];
        const di = ((py + y) * canvas.width + (px + x)) * 4;
        buf[di] = v;
        buf[di + 1] = v;
        buf[di + 2] = v;
        buf[di + 3] = 255;
      }
    }
  };

  // Top border.
  paste(BORDER_TL, 0, 0);
  for (let x = 1; x < totalW - 1; x++) paste(BORDER_H, x, 0);
  paste(BORDER_TR, totalW - 1, 0);

  // Body rows: vertical borders + space-filled interior + characters.
  for (let row = 0; row < lines.length; row++) {
    const y = row + 1;
    paste(BORDER_V, 0, y);
    for (let x = 1; x < totalW - 1; x++) paste(0x7f, x, y);
    const line = lines[row];
    for (let ci = 0; ci < line.length; ci++) {
      const idx = CHARMAP[line[ci]] ?? 0x7f;
      paste(idx, ci + 1, y);
    }
    paste(BORDER_V, totalW - 1, y);
  }

  // Bottom border.
  paste(BORDER_BL, 0, totalH - 1);
  for (let x = 1; x < totalW - 1; x++) paste(BORDER_H, x, totalH - 1);
  paste(BORDER_BR, totalW - 1, totalH - 1);

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}
