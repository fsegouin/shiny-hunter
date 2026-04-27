/**
 * Thin wrapper around WasmBoy that gives the hunter loop the same
 * primitives the Python `Emulator` class provides:
 *   - load ROM
 *   - save / load state to/from a serializable object
 *   - tick N frames (headless / non-rendered)
 *   - read raw bytes at a Game Boy address
 *   - dump cartridge SRAM as a .sav
 *   - press / release a button by name
 *
 * Notes about WasmBoy 0.7.x worth keeping next to the wrapper:
 *
 *  - `_getWasmMemorySection` and `_getWasmConstant` are *async*
 *    (postMessage to the internal worker). Treating them as sync makes
 *    every memory read return an empty array. We resolve the GB memory
 *    base once during init and await every read.
 *
 *  - `saveState()` returns Uint8Array views into worker-owned memory.
 *    Passing the same object to `loadState()` twice trips a
 *    "the object can not be cloned" DOMException because the buffers
 *    get transferred during the first call. We deep-copy on save AND
 *    again before each load.
 *
 * Everything is client-side; this module must not be imported in
 * server components.
 */
import { cloneState, type WasmBoySaveState } from '../state';

const BUTTONS = ['A', 'B', 'START', 'SELECT', 'UP', 'DOWN', 'LEFT', 'RIGHT'] as const;
export type Button = (typeof BUTTONS)[number];

type JoypadState = Record<Lowercase<Button>, boolean>;

export interface WasmBoyEmulator {
  isReady(): boolean;
  /** Steps the emulator by `frames` frames without canvas updates. */
  tick(frames: number): Promise<void>;
  /** Reads `length` bytes from a Game Boy address (0x0000-0xFFFF). */
  readBytes(addr: number, length: number): Promise<Uint8Array>;
  /** Convenience: a single byte. */
  readByte(addr: number): Promise<number>;
  /** Returns a deep-copied snapshot suitable for `loadState`. */
  saveState(): Promise<WasmBoySaveState>;
  loadState(state: WasmBoySaveState): Promise<void>;
  /** Returns a copy of cartridge battery RAM (the .sav contents). */
  dumpSram(): Promise<Uint8Array>;
  pressButton(button: Button): void;
  releaseButton(button: Button): void;
  /** Resets joypad to all-released. */
  clearJoypad(): void;
  shutdown(): Promise<void>;
}

let wasmBoyModule: typeof import('wasmboy') | null = null;

async function loadWasmBoy(): Promise<typeof import('wasmboy')> {
  if (!wasmBoyModule) {
    wasmBoyModule = await import('wasmboy');
  }
  return wasmBoyModule;
}

export interface InitOptions {
  rom: Uint8Array;
  /** When true, audio is muted and the canvas isn't touched. */
  headless?: boolean;
  /** Optional canvas to render into; ignored when headless. */
  canvas?: HTMLCanvasElement;
}

export async function init(opts: InitOptions): Promise<WasmBoyEmulator> {
  const { WasmBoy } = await loadWasmBoy();
  const headless = opts.headless ?? true;

  await WasmBoy.config(
    {
      headless,
      isAudioEnabled: !headless,
      gameboyFrameRate: 60,
      // We drive frame stepping ourselves, so disable RAF-driven playback.
      disablePauseOnHidden: true,
      enableBootROMIfAvailable: false,
    },
    headless ? undefined : opts.canvas,
  );

  // We send joypad state ourselves; the default keyboard listener would
  // race against `setJoypadState`.
  WasmBoy.disableDefaultJoypad();

  await WasmBoy.loadROM(opts.rom);

  // `play()` starts the run-loop; we immediately pause so we can step
  // frames manually via `_runWasmExport('executeFrame')`.
  await WasmBoy.play();
  await WasmBoy.pause();

  // Resolve the GB memory base once. Async — postMessage to the worker.
  const gbMemoryBase = await WasmBoy._getWasmConstant('GAMEBOY_INTERNAL_MEMORY_LOCATION');

  // Persistent joypad state we mutate via press/release.
  const joypad: JoypadState = {
    a: false, b: false, start: false, select: false,
    up: false, down: false, left: false, right: false,
  };
  const pushJoypad = () => WasmBoy.setJoypadState(joypad);

  const tick = async (frames: number) => {
    for (let i = 0; i < frames; i++) {
      await WasmBoy._runWasmExport('executeFrame', []);
    }
  };

  const readBytes = async (addr: number, length: number): Promise<Uint8Array> => {
    if (addr < 0 || addr + length > 0x10000) {
      throw new RangeError(
        `addr+length out of GB memory range: 0x${addr.toString(16)}+${length}`,
      );
    }
    const start = gbMemoryBase + addr;
    const slice = await WasmBoy._getWasmMemorySection(start, start + length);
    // Copy: the returned view aliases worker memory and may shift
    // under the caller as soon as the emulator advances again.
    return new Uint8Array(slice);
  };

  const saveState = async (): Promise<WasmBoySaveState> => {
    const raw = await WasmBoy.saveState();
    return cloneState(raw as WasmBoySaveState);
  };

  const loadState = async (state: WasmBoySaveState): Promise<void> => {
    // Clone again so the caller's reference isn't disturbed by WasmBoy
    // detaching/transferring buffers during the postMessage hop.
    await WasmBoy.loadState(cloneState(state));
  };

  const dumpSram = async (): Promise<Uint8Array> => {
    const state = await saveState();
    return new Uint8Array(state.wasmBoyMemory.cartridgeRam);
  };

  const setButton = (button: Button, pressed: boolean) => {
    const key = button.toLowerCase() as Lowercase<Button>;
    joypad[key] = pressed;
    pushJoypad();
  };

  return {
    isReady: () => WasmBoy.isReady(),
    tick,
    readBytes,
    readByte: async (addr) => (await readBytes(addr, 1))[0],
    saveState,
    loadState,
    dumpSram,
    pressButton: (b) => setButton(b, true),
    releaseButton: (b) => setButton(b, false),
    clearJoypad: () => {
      (Object.keys(joypad) as Array<keyof JoypadState>).forEach((k) => (joypad[k] = false));
      pushJoypad();
    },
    shutdown: async () => {
      await WasmBoy.pause();
      await WasmBoy.reset();
    },
  };
}

export const ALL_BUTTONS: readonly Button[] = BUTTONS;
