/**
 * Bare WASM core loader for WasmBoy's emulator binary.
 *
 * Designed to run inside a Web Worker with synchronous access to the
 * Game Boy emulator — no postMessage overhead, no WasmBoy JS library.
 * `instantiateCore` is the only async function (WASM instantiation is
 * inherently async); every other helper is synchronous.
 *
 * The module directly instantiates `wasmboy-core.wasm` (the same binary
 * WasmBoy's internal worker uses), resolves the memory layout constants
 * from the WASM globals, and exposes thin wrappers for frame stepping,
 * joypad input, save/load state, and raw memory access.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Resolved byte offsets into WASM linear memory. */
export interface MemoryLayout {
  readonly cartridgeRomLocation: number;
  readonly cartridgeRamLocation: number;
  readonly gameBoyInternalMemoryLocation: number;
  readonly gameBoyInternalMemorySize: number;
  readonly gbcPaletteLocation: number;
  readonly gbcPaletteSize: number;
  readonly wasmBoyStateLocation: number;
  readonly wasmBoyStateSize: number;
  readonly frameLocation: number;
  readonly frameSize: number;
}

/** The four memory sections that make up a WasmBoy save state. */
export interface StateSections {
  internalState: Uint8Array;
  paletteMemory: Uint8Array;
  gameBoyMemory: Uint8Array;
  cartridgeRam: Uint8Array;
}

/** Typed subset of what the WASM module exports. */
interface WasmExports {
  memory: WebAssembly.Memory;

  // Functions
  executeFrame(): number;
  executeMultipleFrames(numberOfFrames: number): number;
  saveState(): void;
  loadState(): void;
  config(
    bootRom: number,
    isGbc: number,
    audioBatch: number,
    graphicsBatch: number,
    timersBatch: number,
    disableScanline: number,
    accumulateSamples: number,
    tileRendering: number,
    tileCaching: number,
    enableAudioDebugging: number,
  ): void;
  setJoypadState(
    up: number,
    right: number,
    down: number,
    left: number,
    a: number,
    b: number,
    select: number,
    start: number,
  ): void;

  // Memory layout constants (WebAssembly.Global)
  CARTRIDGE_ROM_LOCATION: WebAssembly.Global;
  CARTRIDGE_RAM_LOCATION: WebAssembly.Global;
  GAMEBOY_INTERNAL_MEMORY_LOCATION: WebAssembly.Global;
  GAMEBOY_INTERNAL_MEMORY_SIZE: WebAssembly.Global;
  GBC_PALETTE_LOCATION: WebAssembly.Global;
  GBC_PALETTE_SIZE: WebAssembly.Global;
  WASMBOY_STATE_LOCATION: WebAssembly.Global;
  WASMBOY_STATE_SIZE: WebAssembly.Global;
  FRAME_LOCATION: WebAssembly.Global;
  FRAME_SIZE: WebAssembly.Global;
}

/** The instantiated core — WASM exports, a byte view of memory, and resolved layout. */
export interface WasmCore {
  exports: WasmExports;
  mem: Uint8Array;
  layout: MemoryLayout;
}

// If WASM memory was grown, the old ArrayBuffer is detached. Refresh the view.
function ensureMem(core: WasmCore): void {
  if (core.mem.byteLength === 0) {
    core.mem = new Uint8Array(core.exports.memory.buffer);
  }
}

// ---------------------------------------------------------------------------
// Instantiation
// ---------------------------------------------------------------------------

/**
 * Minimal import object that satisfies WasmBoy's WASM module.
 *
 * The binary expects `index.consoleLog`, `index.consoleLogTimeout`, and
 * `env.abort`. In our headless context these are no-ops (aside from
 * logging aborts).
 */
const wasmImports: WebAssembly.Imports = {
  index: {
    consoleLog: () => {},
    consoleLogTimeout: () => {},
  },
  env: {
    abort: () => {
      console.error('WASM abort');
    },
  },
};

/**
 * Patch a known bug in WasmBoy 0.7.1's compiled WASM binary.
 *
 * Channels 1-4 have a typo in `loadState()` where they use the channel's
 * `cycleCounter` value (a runtime counter) as the save-state slot index
 * instead of the constant `saveStateSlot`. After the first state load,
 * cycleCounter holds garbage, and a second loadState computes an offset
 * far past the end of WASM linear memory → "memory access out of bounds".
 *
 * The bug looks like (WAT):
 *   global.get $ChannelN.cycleCounter
 *   i32.const 50
 *   i32.mul
 *   i32.const 1024     ;; WASMBOY_STATE_LOCATION
 *   i32.add
 *   i32.load
 *   global.set $ChannelN.cycleCounter
 *
 * We replace the leading `global.get` (2 bytes: 0x23 idx) with
 * `i32.const SLOT` (2 bytes: 0x41 slot). The 4 channel slots are 7-10.
 * Both encodings are 2 bytes, so the patch is in-place and doesn't shift
 * any function offsets.
 */
function patchChannelLoadStateBug(bytes: Uint8Array): number {
  // Pattern that follows the buggy global.get:
  //   0x41 0x32       i32.const 50
  //   0x6C            i32.mul
  //   0x41 0x80 0x08  i32.const 1024 (LEB128)
  //   0x6A            i32.add
  const pattern = [0x41, 0x32, 0x6C, 0x41, 0x80, 0x08, 0x6A];
  const channelSlots = [7, 8, 9, 10];
  let patched = 0;

  for (let i = 3; i + pattern.length < bytes.length && patched < 4; i++) {
    let match = true;
    for (let j = 0; j < pattern.length; j++) {
      if (bytes[i + j] !== pattern[j]) { match = false; break; }
    }
    if (!match) continue;

    // Look back to find the `global.get` (0x23) — either 2-byte (single-byte
    // LEB128 index) or 3-byte (2-byte LEB128 index).
    let globalGetStart = -1;
    let getLen = 0;
    if (bytes[i - 2] === 0x23 && bytes[i - 1] < 0x80) {
      globalGetStart = i - 2;
      getLen = 2;
    } else if (
      bytes[i - 3] === 0x23 &&
      bytes[i - 2] >= 0x80 &&
      bytes[i - 1] < 0x80
    ) {
      globalGetStart = i - 3;
      getLen = 3;
    } else {
      continue;
    }

    // After i32.add (0x6A): i32.load (0x28 align offset), then global.set X.
    let p = i + pattern.length;
    if (bytes[p] !== 0x28) continue;
    p += 3; // skip 0x28 + 1-byte align + 1-byte offset

    // global.set must have matching length and index bytes.
    if (bytes[p] !== 0x24) continue;
    let setMatches = true;
    for (let k = 1; k < getLen; k++) {
      if (bytes[p + k] !== bytes[globalGetStart + k]) {
        setMatches = false;
        break;
      }
    }
    if (!setMatches) continue;

    // Patch in-place:
    //   2-byte:  0x23 X       → 0x41 SLOT
    //   3-byte:  0x23 X1 X2   → 0x01 0x41 SLOT (prepend nop)
    if (getLen === 2) {
      bytes[globalGetStart] = 0x41;
      bytes[globalGetStart + 1] = channelSlots[patched];
    } else {
      bytes[globalGetStart] = 0x01; // nop
      bytes[globalGetStart + 1] = 0x41;
      bytes[globalGetStart + 2] = channelSlots[patched];
    }
    patched++;
  }
  return patched;
}

/** Instantiate the WasmBoy WASM binary and resolve its memory layout. */
export async function instantiateCore(
  wasmBytes: ArrayBuffer,
): Promise<WasmCore> {
  const patchedBytes = new Uint8Array(wasmBytes.slice(0));
  const numPatched = patchChannelLoadStateBug(patchedBytes);
  console.log('[wasm-core] patched', numPatched, '/ 4 Channel.loadState bugs');
  const { instance } = await WebAssembly.instantiate(patchedBytes.buffer as ArrayBuffer, wasmImports);
  const exports = instance.exports as unknown as WasmExports;
  const mem = new Uint8Array(exports.memory.buffer);

  const layout: MemoryLayout = {
    cartridgeRomLocation: (exports.CARTRIDGE_ROM_LOCATION as unknown as { valueOf(): number }).valueOf(),
    cartridgeRamLocation: (exports.CARTRIDGE_RAM_LOCATION as unknown as { valueOf(): number }).valueOf(),
    gameBoyInternalMemoryLocation: (exports.GAMEBOY_INTERNAL_MEMORY_LOCATION as unknown as { valueOf(): number }).valueOf(),
    gameBoyInternalMemorySize: (exports.GAMEBOY_INTERNAL_MEMORY_SIZE as unknown as { valueOf(): number }).valueOf(),
    gbcPaletteLocation: (exports.GBC_PALETTE_LOCATION as unknown as { valueOf(): number }).valueOf(),
    gbcPaletteSize: (exports.GBC_PALETTE_SIZE as unknown as { valueOf(): number }).valueOf(),
    wasmBoyStateLocation: (exports.WASMBOY_STATE_LOCATION as unknown as { valueOf(): number }).valueOf(),
    wasmBoyStateSize: (exports.WASMBOY_STATE_SIZE as unknown as { valueOf(): number }).valueOf(),
    frameLocation: (exports.FRAME_LOCATION as unknown as { valueOf(): number }).valueOf(),
    frameSize: (exports.FRAME_SIZE as unknown as { valueOf(): number }).valueOf(),
  };

  return { exports, mem, layout };
}

// ---------------------------------------------------------------------------
// ROM loading
// ---------------------------------------------------------------------------

/** Write ROM bytes into the WASM memory at the cartridge ROM location. */
export function loadRom(core: WasmCore, romBytes: Uint8Array): void {
  core.mem.set(romBytes, core.layout.cartridgeRomLocation);
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

// Headless config: batch audio/graphics/timers + disable scanline rendering.
const HEADLESS_CONFIG: [number, number, number, number, number, number, number, number, number, number] =
  [0, 0, 1, 1, 1, 1, 0, 0, 0, 0];

export function configureCore(core: WasmCore): void {
  core.exports.config(...HEADLESS_CONFIG);
}

// ---------------------------------------------------------------------------
// State save / load
// ---------------------------------------------------------------------------

/**
 * Write four state sections into WASM memory and call `loadState()`.
 *
 * Mirrors WasmBoy's SET_MEMORY handler: write cartridge RAM, Game Boy
 * memory, palette memory, and internal state into the correct offsets,
 * then invoke the WASM `loadState` export so the CPU registers are
 * restored from the internal-state blob.
 */
export function writeState(core: WasmCore, state: StateSections): void {
  ensureMem(core);
  const { layout, exports } = core;
  core.mem.set(state.cartridgeRam, layout.cartridgeRamLocation);
  core.mem.set(state.gameBoyMemory, layout.gameBoyInternalMemoryLocation);
  core.mem.set(state.paletteMemory, layout.gbcPaletteLocation);
  core.mem.set(state.internalState, layout.wasmBoyStateLocation);
  exports.loadState();
}

/**
 * Call `saveState()` and slice the four state sections from WASM memory.
 *
 * Returns owned copies (`.slice()`) so the caller is not affected by
 * subsequent emulator mutations.
 *
 * @param sramSize — how many bytes to read from cartridge RAM.
 *   Defaults to 0x8000 (32 KiB), which covers MBC3 carts used by
 *   Gen 1 Pokémon. The caller should pass the game-specific size
 *   if known.
 */
export function readState(
  core: WasmCore,
  sramSize: number = 0x8000,
): StateSections {
  const { layout, exports } = core;
  exports.saveState();
  ensureMem(core);

  return {
    internalState: core.mem.slice(
      layout.wasmBoyStateLocation,
      layout.wasmBoyStateLocation + layout.wasmBoyStateSize,
    ),
    paletteMemory: core.mem.slice(
      layout.gbcPaletteLocation,
      layout.gbcPaletteLocation + layout.gbcPaletteSize,
    ),
    gameBoyMemory: core.mem.slice(
      layout.gameBoyInternalMemoryLocation,
      layout.gameBoyInternalMemoryLocation + layout.gameBoyInternalMemorySize,
    ),
    cartridgeRam: core.mem.slice(
      layout.cartridgeRamLocation,
      layout.cartridgeRamLocation + sramSize,
    ),
  };
}

// ---------------------------------------------------------------------------
// Memory access
// ---------------------------------------------------------------------------

// WasmBoy's internal memory layout is NOT a flat 0x0000-0xFFFF address space.
// The gameBoyInternalMemory region packs sub-regions at fixed offsets:
//   VIDEO_RAM (GB 0x8000-0x9FFF) → base + 0x0000  (0x4000 bytes, GBC: 2 banks)
//   WORK_RAM  (GB 0xC000-0xDFFF) → base + 0x4000  (0x8000 bytes, GBC: 8 banks)
//   OTHER     (GB 0xE000-0xFFFF) → base + 0xC000  (0x4000 bytes)
const VRAM_OFFSET = 0x0000;
const WRAM_OFFSET = 0x4000;
const OTHER_OFFSET = 0xC000;

function gbToWasm(core: WasmCore, gbAddr: number): number {
  const base = core.layout.gameBoyInternalMemoryLocation;
  const hi = gbAddr >> 12;
  if (hi <= 0x7) return base + gbAddr; // ROM — technically in cartridge ROM area, not reliable
  if (hi <= 0x9) return base + VRAM_OFFSET + (gbAddr - 0x8000);
  if (hi <= 0xB) return base + gbAddr; // Cartridge RAM — in cartridge RAM area, not reliable
  if (hi <= 0xD) return base + WRAM_OFFSET + (gbAddr - 0xC000);
  return base + OTHER_OFFSET + (gbAddr - 0xE000);
}

export function readByte(core: WasmCore, gbAddr: number): number {
  return core.mem[gbToWasm(core, gbAddr)];
}

export function readBytes(
  core: WasmCore,
  gbAddr: number,
  length: number,
): Uint8Array {
  const start = gbToWasm(core, gbAddr);
  return core.mem.slice(start, start + length);
}

// ---------------------------------------------------------------------------
// Frame stepping
// ---------------------------------------------------------------------------

/** Advance the emulator by `frames` frames. Synchronous. */
export function tick(core: WasmCore, frames: number): void {
  if (frames <= 0) return;
  core.exports.executeMultipleFrames(frames);
}

// ---------------------------------------------------------------------------
// Joypad
// ---------------------------------------------------------------------------

/** Set the joypad state. Each parameter is a boolean mapped to 0/1. */
export function setJoypad(
  core: WasmCore,
  up: boolean,
  right: boolean,
  down: boolean,
  left: boolean,
  a: boolean,
  b: boolean,
  select: boolean,
  start: boolean,
): void {
  core.exports.setJoypadState(
    up ? 1 : 0,
    right ? 1 : 0,
    down ? 1 : 0,
    left ? 1 : 0,
    a ? 1 : 0,
    b ? 1 : 0,
    select ? 1 : 0,
    start ? 1 : 0,
  );
}

/** Release all joypad buttons. */
export function clearJoypad(core: WasmCore): void {
  core.exports.setJoypadState(0, 0, 0, 0, 0, 0, 0, 0);
}

// ---------------------------------------------------------------------------
// Framebuffer
// ---------------------------------------------------------------------------

/**
 * Get the current framebuffer pixel data.
 *
 * Returns an owned copy. The framebuffer format is WasmBoy's internal
 * representation (RGB for each pixel of the 160x144 display).
 */
export function getFrameBuffer(core: WasmCore): Uint8Array {
  const { layout, mem } = core;
  return mem.slice(layout.frameLocation, layout.frameLocation + layout.frameSize);
}
