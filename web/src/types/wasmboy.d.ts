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
    // NOTE: outer key is `wasmboyMemory` (lowercase 'b'), inner keys
    // use `wasmBoy*` (uppercase 'B'). Verified against the 0.7.1 source
    // — see `getSaveState` in dist/wasmboy.wasm.cjs.js.
    wasmboyMemory: {
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

  // Bundled ResponsiveGamepad instance. WasmBoy ships its own copy of
  // `responsive-gamepad`; the singleton you'd get from
  // `import('responsive-gamepad')` is a SEPARATE instance whose state
  // isn't polled by WasmBoy. Always use `WasmBoy.ResponsiveGamepad`.
  interface ResponsiveGamepadApi {
    enable(): void;
    disable(): void;
    getState(): Record<string, boolean | number>;
    RESPONSIVE_GAMEPAD_INPUTS: Record<string, string>;
    TouchInput: {
      enable(): void;
      disable(): void;
      addButtonInput(element: HTMLElement, input: string): () => void;
      addDpadInput(element: HTMLElement, options?: { allowMultipleDirections?: boolean }): () => void;
    };
  }

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

    /**
     * The bundled responsive-gamepad singleton. Use this for touch
     * input wiring instead of importing `responsive-gamepad` directly,
     * which gives you a different instance.
     */
    ResponsiveGamepad: ResponsiveGamepadApi;
  };

  export default WasmBoy;
}
