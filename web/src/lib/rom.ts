/**
 * Accept a user-supplied File and return the raw ROM bytes.
 *
 * Handles:
 *   - Plain Game Boy ROMs (.gb / .gbc): bytes returned as-is.
 *   - ZIP archives: detected by magic ("PK\x03\x04"), decompressed via
 *     fflate, and the first .gb / .gbc entry returned.
 *
 * No upload to a server: everything happens in-memory in the browser.
 */
import { unzipSync } from 'fflate';

export interface RomLoad {
  bytes: Uint8Array;
  /** The file name we ultimately treated as the ROM (post-extraction). */
  name: string;
  /** "raw" if the input was a plain ROM; "zip" if it came from an archive. */
  source: 'raw' | 'zip';
}

const ZIP_MAGIC = [0x50, 0x4b, 0x03, 0x04]; // "PK\x03\x04"
const GB_EXTENSIONS = ['.gb', '.gbc'];

function looksLikeZip(bytes: Uint8Array): boolean {
  if (bytes.length < ZIP_MAGIC.length) return false;
  return ZIP_MAGIC.every((b, i) => bytes[i] === b);
}

function pickRomEntry(entries: Record<string, Uint8Array>): { name: string; bytes: Uint8Array } {
  const candidates = Object.entries(entries).filter(([name, data]) =>
    data.byteLength > 0 && GB_EXTENSIONS.some((ext) => name.toLowerCase().endsWith(ext)),
  );
  if (candidates.length === 0) {
    throw new Error(
      `archive contains no .gb or .gbc file (saw: ${Object.keys(entries).join(', ') || '<empty>'})`,
    );
  }
  if (candidates.length > 1) {
    // Pick the largest; a small one is usually a save or readme. We could
    // surface a picker later if this heuristic ever bites.
    candidates.sort((a, b) => b[1].byteLength - a[1].byteLength);
  }
  const [name, bytes] = candidates[0];
  return { name, bytes };
}

export async function loadRomFromFile(file: File): Promise<RomLoad> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (!looksLikeZip(bytes)) {
    return { bytes, name: file.name, source: 'raw' };
  }
  let entries: Record<string, Uint8Array>;
  try {
    entries = unzipSync(bytes);
  } catch (err) {
    throw new Error(`failed to read ZIP: ${(err as Error).message}`);
  }
  const picked = pickRomEntry(entries);
  return { bytes: picked.bytes, name: picked.name, source: 'zip' };
}
