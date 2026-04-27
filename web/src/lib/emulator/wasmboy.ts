/**
 * Thin wrapper around WasmBoy that gives the hunter loop the same
 * primitives the Python `Emulator` class provides:
 *   - load ROM
 *   - save / load state to/from bytes
 *   - tick N frames (headless / non-rendered)
 *   - read raw bytes at a Game Boy address
 *   - dump cartridge SRAM as a .sav
 *   - press/release a button by name
 *
 * Everything client-side; this module must not be imported in server
 * components.
 */

const BUTTONS = ['A', 'B', 'START', 'SELECT', 'UP', 'DOWN', 'LEFT', 'RIGHT'] as const;
export type Button = (typeof BUTTONS)[number];

type JoypadState = Record<Lowercase<Button>, boolean>;

export interface WasmBoyEmulator {
  isReady(): boolean;
  /** Steps the emulator by `frames` frames without canvas updates. */
  tick(frames: number): Promise<void>;
  /** Reads `length` bytes from a Game Boy address (0x0000-0xFFFF). */
  readBytes(addr: number, length: number): Uint8Array;
  /** Convenience: a single byte. */
  readByte(addr: number): number;
  /** Returns a snapshot suitable for `loadState`; opaque to the caller. */
  saveState(): Promise<unknown>;
  loadState(state: unknown): Promise<void>;
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

  // `loadROM` accepts a Uint8Array directly.
  await WasmBoy.loadROM(opts.rom);

  // `play()` starts the run-loop; we immediately pause so we can step
  // frames manually via `_runWasmExport('executeFrame')`.
  await WasmBoy.play();
  await WasmBoy.pause();

  const gbMemoryBase = WasmBoy._getWasmConstant('GAMEBOY_INTERNAL_MEMORY_LOCATION') as number;

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

  const readBytes = (addr: number, length: number): Uint8Array => {
    if (addr < 0 || addr + length > 0x10000) {
      throw new RangeError(`addr+length out of GB memory range: 0x${addr.toString(16)}+${length}`);
    }
    const start = gbMemoryBase + addr;
    const slice = WasmBoy._getWasmMemorySection(start, start + length) as Uint8Array;
    // _getWasmMemorySection returns a *view* into WASM memory; copy so the
    // caller's value doesn't shift under them when the emulator runs again.
    return new Uint8Array(slice);
  };

  const dumpSram = async (): Promise<Uint8Array> => {
    const state = await WasmBoy.saveState();
    // SaveState shape: { wasmBoyMemory: { cartridgeRam: Uint8Array, ... }, ... }
    const cartRam = (state as { wasmBoyMemory?: { cartridgeRam?: Uint8Array } })
      .wasmBoyMemory?.cartridgeRam;
    if (!cartRam) {
      throw new Error('saveState did not include cartridgeRam — wrong schema?');
    }
    return new Uint8Array(cartRam);
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
    readByte: (addr) => readBytes(addr, 1)[0],
    saveState: () => WasmBoy.saveState(),
    loadState: (state) => WasmBoy.loadState(state as Parameters<typeof WasmBoy.loadState>[0]),
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
