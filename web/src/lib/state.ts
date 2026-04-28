/**
 * Compact binary serialization for WasmBoy save states.
 *
 * WasmBoy's `saveState()` returns an object containing four Uint8Array
 * sections plus a couple of scalars. We pack them into a single binary
 * blob with a small header so the user can download / re-upload across
 * sessions:
 *
 *   bytes 0..3   magic "WBST"
 *   bytes 4..5   format version (u16 LE; currently 1)
 *   bytes 6..7   reserved (u16 LE; 0)
 *   bytes 8..15  date (u64 LE; ms since epoch)
 *   bytes 16..19 internalState length (u32 LE)
 *   bytes 20..23 paletteMemory length (u32 LE)
 *   bytes 24..27 gameBoyMemory length (u32 LE)
 *   bytes 28..31 cartridgeRam length (u32 LE)
 *   then the four sections concatenated in the same order.
 *
 * NOTE: this is a WasmBoy-specific format. PyBoy `.state` files from
 * the Python CLI are NOT interchangeable with this — the two emulators
 * have different internal layouts.
 *
 * NOTE about WasmBoy's own shape: the outer container key is
 * `wasmboyMemory` (lowercase 'b'), even though the inner keys use
 * `wasmBoy*` (uppercase 'B'). Bizarre but verified against the 0.7.1
 * source (`getSaveState` in dist/wasmboy.wasm.cjs.js).
 */

/**
 * Deep-copy a save state. WasmBoy's `saveState()` returns Uint8Array
 * VIEWS into worker-owned memory; passing the same object to
 * `loadState()` twice fails with "the object can not be cloned" because
 * the underlying buffers get transferred/detached during the first
 * call. Always work with a copy.
 */
export function cloneState(state: WasmBoySaveState): WasmBoySaveState {
  if (!state || !state.wasmboyMemory) {
    throw new Error(
      'unexpected save-state shape (no .wasmboyMemory) — WasmBoy version mismatch?',
    );
  }
  const m = state.wasmboyMemory;
  return {
    wasmboyMemory: {
      wasmBoyInternalState: new Uint8Array(m.wasmBoyInternalState),
      wasmBoyPaletteMemory: new Uint8Array(m.wasmBoyPaletteMemory),
      gameBoyMemory: new Uint8Array(m.gameBoyMemory),
      cartridgeRam: new Uint8Array(m.cartridgeRam),
    },
    date: state.date,
    isAuto: state.isAuto,
  };
}

const MAGIC = new Uint8Array([0x57, 0x42, 0x53, 0x54]); // "WBST"
const VERSION = 1;
const HEADER_SIZE = 32;

export interface WasmBoySaveState {
  wasmboyMemory: {
    wasmBoyInternalState: Uint8Array;
    wasmBoyPaletteMemory: Uint8Array;
    gameBoyMemory: Uint8Array;
    cartridgeRam: Uint8Array;
  };
  date: number;
  isAuto: boolean;
}

export function serializeState(state: WasmBoySaveState): Uint8Array {
  const m = state.wasmboyMemory;
  const totalSize =
    HEADER_SIZE +
    m.wasmBoyInternalState.byteLength +
    m.wasmBoyPaletteMemory.byteLength +
    m.gameBoyMemory.byteLength +
    m.cartridgeRam.byteLength;
  const out = new Uint8Array(totalSize);
  const view = new DataView(out.buffer);
  out.set(MAGIC, 0);
  view.setUint16(4, VERSION, true);
  view.setUint16(6, 0, true); // reserved
  view.setBigUint64(8, BigInt(Math.floor(state.date)), true);
  view.setUint32(16, m.wasmBoyInternalState.byteLength, true);
  view.setUint32(20, m.wasmBoyPaletteMemory.byteLength, true);
  view.setUint32(24, m.gameBoyMemory.byteLength, true);
  view.setUint32(28, m.cartridgeRam.byteLength, true);
  let off = HEADER_SIZE;
  out.set(m.wasmBoyInternalState, off);  off += m.wasmBoyInternalState.byteLength;
  out.set(m.wasmBoyPaletteMemory, off);  off += m.wasmBoyPaletteMemory.byteLength;
  out.set(m.gameBoyMemory, off);         off += m.gameBoyMemory.byteLength;
  out.set(m.cartridgeRam, off);
  return out;
}

export function deserializeState(bytes: Uint8Array): WasmBoySaveState {
  if (bytes.byteLength < HEADER_SIZE) {
    throw new Error('state file too small to contain a header');
  }
  for (let i = 0; i < MAGIC.length; i++) {
    if (bytes[i] !== MAGIC[i]) {
      throw new Error('not a WasmBoy state file (magic mismatch)');
    }
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const version = view.getUint16(4, true);
  if (version !== VERSION) {
    throw new Error(`unsupported state file version ${version} (expected ${VERSION})`);
  }
  const date = Number(view.getBigUint64(8, true));
  const internalLen = view.getUint32(16, true);
  const paletteLen = view.getUint32(20, true);
  const gbMemLen = view.getUint32(24, true);
  const cartRamLen = view.getUint32(28, true);
  const expected = HEADER_SIZE + internalLen + paletteLen + gbMemLen + cartRamLen;
  if (bytes.byteLength < expected) {
    throw new Error(`state file truncated: expected ${expected} bytes, got ${bytes.byteLength}`);
  }
  let off = HEADER_SIZE;
  const slice = (n: number) => {
    const out = bytes.slice(off, off + n);
    off += n;
    return out;
  };
  return {
    wasmboyMemory: {
      wasmBoyInternalState: slice(internalLen),
      wasmBoyPaletteMemory: slice(paletteLen),
      gameBoyMemory: slice(gbMemLen),
      cartridgeRam: slice(cartRamLen),
    },
    date,
    isAuto: false,
  };
}
