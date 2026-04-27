/**
 * Minimal ambient types for `wasmboy@0.7.x`.
 *
 * The package ships no .d.ts. We only declare the methods our wrapper
 * uses; everything else stays `unknown`. If we end up using more of the
 * surface area, extend this file.
 */
declare module 'wasmboy' {
  type Button =
    | 'a' | 'b' | 'start' | 'select'
    | 'up' | 'down' | 'left' | 'right';
  type JoypadState = Partial<Record<Button, boolean>>;

  interface SaveState {
    wasmBoyMemory: {
      wasmBoyInternalState: Uint8Array;
      wasmBoyPaletteMemory: Uint8Array;
      gameBoyMemory: Uint8Array;
      cartridgeRam: Uint8Array;
    };
    date: number;
    isAuto: boolean;
  }

  interface ConfigOptions {
    headless?: boolean;
    isAudioEnabled?: boolean;
    gameboyFrameRate?: number;
    disablePauseOnHidden?: boolean;
    enableBootROMIfAvailable?: boolean;
    isGbcEnabled?: boolean;
    [key: string]: unknown;
  }

  type WasmConstantName =
    | 'GAMEBOY_INTERNAL_MEMORY_LOCATION'
    | 'WASMBOY_GAME_BYTES_LOCATION'
    | 'WASMBOY_GAME_RAM_BANKS_LOCATION'
    | 'WASMBOY_INTERNAL_STATE_LOCATION'
    | 'WASMBOY_PALETTE_MEMORY_LOCATION';

  export const WasmBoy: {
    config(options: ConfigOptions, canvas?: HTMLCanvasElement): Promise<void>;
    loadROM(rom: Uint8Array | string | File): Promise<void>;
    play(): Promise<void>;
    pause(): Promise<void>;
    reset(): Promise<void>;
    isReady(): boolean;
    isLoadedAndStarted(): boolean;
    isPlaying(): boolean;
    isPaused(): boolean;

    saveState(): Promise<SaveState>;
    loadState(state: SaveState): Promise<void>;

    enableDefaultJoypad(): void;
    disableDefaultJoypad(): void;
    setJoypadState(state: JoypadState): void;

    setSpeed(speed: number): void;
    getFPS(): number;

    _runWasmExport(name: 'executeFrame' | string, args: unknown[]): Promise<unknown>;
    _getWasmMemorySection(start: number, end: number): Promise<Uint8Array>;
    _getWasmConstant(name: WasmConstantName): Promise<number>;
  };

  export default WasmBoy;
}
