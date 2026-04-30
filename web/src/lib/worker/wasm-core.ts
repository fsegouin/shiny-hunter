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

/** Instantiate the WasmBoy WASM binary and resolve its memory layout. */
export async function instantiateCore(
  wasmBytes: ArrayBuffer,
): Promise<WasmCore> {
  const { instance } = await WebAssembly.instantiate(wasmBytes, wasmImports);
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

/**
 * Configure the emulator for headless operation.
 *
 * All flags zeroed: no boot ROM, no GBC, no audio batching, no graphics
 * batching, no timer batching, scanline rendering off, no sample
 * accumulation, no tile rendering, no tile caching, no audio debugging.
 */
export function configureCore(core: WasmCore): void {
  core.exports.config(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
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
  const { mem, layout, exports } = core;
  mem.set(state.cartridgeRam, layout.cartridgeRamLocation);
  mem.set(state.gameBoyMemory, layout.gameBoyInternalMemoryLocation);
  mem.set(state.paletteMemory, layout.gbcPaletteLocation);
  mem.set(state.internalState, layout.wasmBoyStateLocation);
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
  const { mem, layout, exports } = core;
  exports.saveState();

  return {
    internalState: mem.slice(
      layout.wasmBoyStateLocation,
      layout.wasmBoyStateLocation + layout.wasmBoyStateSize,
    ),
    paletteMemory: mem.slice(
      layout.gbcPaletteLocation,
      layout.gbcPaletteLocation + layout.gbcPaletteSize,
    ),
    gameBoyMemory: mem.slice(
      layout.gameBoyInternalMemoryLocation,
      layout.gameBoyInternalMemoryLocation + layout.gameBoyInternalMemorySize,
    ),
    cartridgeRam: mem.slice(
      layout.cartridgeRamLocation,
      layout.cartridgeRamLocation + sramSize,
    ),
  };
}

// ---------------------------------------------------------------------------
// Memory access
// ---------------------------------------------------------------------------

/**
 * Read a single byte at a Game Boy address (0x0000-0xFFFF).
 *
 * This indexes directly into the WASM linear memory at
 * `gameBoyInternalMemoryLocation + gbAddr` — no async, no postMessage.
 */
export function readByte(core: WasmCore, gbAddr: number): number {
  return core.mem[core.layout.gameBoyInternalMemoryLocation + gbAddr];
}

/**
 * Read `length` bytes starting at a Game Boy address.
 *
 * Returns an owned copy so the caller is not affected by subsequent
 * emulator mutations.
 */
export function readBytes(
  core: WasmCore,
  gbAddr: number,
  length: number,
): Uint8Array {
  const start = core.layout.gameBoyInternalMemoryLocation + gbAddr;
  return core.mem.slice(start, start + length);
}

// ---------------------------------------------------------------------------
// Frame stepping
// ---------------------------------------------------------------------------

/** Advance the emulator by `frames` frames. Synchronous. */
export function tick(core: WasmCore, frames: number): void {
  for (let i = 0; i < frames; i++) {
    core.exports.executeFrame();
  }
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
