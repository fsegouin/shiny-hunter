/**
 * Main-thread hunt orchestration.
 *
 * Spawns the hunt Web Worker, sends start/stop/resume messages, and
 * dispatches incoming messages to caller-supplied callbacks. Converts
 * between the app-level types (WasmBoySaveState, EventMacro, GameConfig)
 * and the flat transfer types the worker expects.
 */

import type { WasmBoySaveState } from './state';
import type { EventMacro } from './macro';
import type { GameConfig } from './games';
import type {
  WorkerOutbound,
  StateSectionsTransfer,
  DVsData,
  MacroEvent,
} from './worker/hunt-worker';

// Re-export worker types that callers will need.
export type { StateSectionsTransfer, DVsData };

// ---------------------------------------------------------------------------
// Callbacks & handle
// ---------------------------------------------------------------------------

export interface HuntCallbacks {
  onProgress(data: {
    attempt: number;
    attemptsPerSec: number;
    delay: number;
    latestDvs: DVsData;
    latestSpecies: number;
    pixels: Uint8Array;
    shiny: boolean;
  }): void;
  onShiny(data: {
    state: StateSectionsTransfer;
    species: number;
    dvs: DVsData;
    delay: number;
    attempt: number;
  }): void;
  onDone(data: { totalAttempts: number; shiniesFound: number }): void;
  onError(message: string): void;
}

export interface HuntHandle {
  stop(): void;
  resume(): void;
  terminate(): void;
}

// ---------------------------------------------------------------------------
// State conversion helpers
// ---------------------------------------------------------------------------

/**
 * Convert a worker StateSectionsTransfer back into a WasmBoySaveState,
 * suitable for passing to WasmBoy's `loadState()` for interactive
 * playback after a shiny is found.
 */
export function transferToWasmBoyState(
  t: StateSectionsTransfer,
): WasmBoySaveState {
  return {
    wasmboyMemory: {
      wasmBoyInternalState: new Uint8Array(t.internalState),
      wasmBoyPaletteMemory: new Uint8Array(t.paletteMemory),
      gameBoyMemory: new Uint8Array(t.gameBoyMemory),
      cartridgeRam: new Uint8Array(t.cartridgeRam),
    },
    date: Date.now(),
    isAuto: false,
  };
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

const DELAY_WINDOW = 1 << 16; // 65 536

/**
 * Spawn the hunt worker, post the start message, and wire up message
 * dispatch. Returns a handle for stop / resume / terminate.
 */
export function startHunt(
  rom: Uint8Array,
  state: WasmBoySaveState,
  macro: EventMacro,
  config: GameConfig,
  callbacks: HuntCallbacks,
  masterSeed: number = 0,
): HuntHandle {
  const worker = new Worker(
    new URL('./worker/hunt-worker.ts', import.meta.url),
  );

  // --- Convert EventMacro → MacroEvent[] ---
  const macroEvents: MacroEvent[] = macro.events.map((e) => ({
    frame: e.frame,
    kind: e.kind,
    button: e.button,
  }));

  // --- Clone state arrays, then build the transfer objects ---
  // Cloning is critical: postMessage will detach the underlying
  // ArrayBuffers, and we must not invalidate the caller's state.
  const internalState = new Uint8Array(state.wasmboyMemory.wasmBoyInternalState).buffer as ArrayBuffer;
  const paletteMemory = new Uint8Array(state.wasmboyMemory.wasmBoyPaletteMemory).buffer as ArrayBuffer;
  const gameBoyMemory = new Uint8Array(state.wasmboyMemory.gameBoyMemory).buffer as ArrayBuffer;
  const cartridgeRam = new Uint8Array(state.wasmboyMemory.cartridgeRam).buffer as ArrayBuffer;

  const stateTransfer: StateSectionsTransfer = {
    internalState,
    paletteMemory,
    gameBoyMemory,
    cartridgeRam,
  };

  // --- Build HuntConfig from GameConfig ---
  const huntConfig = {
    dvAddr: config.partyDvAddr,
    speciesAddr: config.partySpeciesAddr,
    sramSize: config.sramSize,
    settleFrames: config.postMacroSettleFrames,
  };

  // --- Post the start message with transferable buffers ---
  worker.postMessage(
    {
      type: 'start' as const,
      rom,
      state: stateTransfer,
      macro: macroEvents,
      macroTotalFrames: macro.totalFrames,
      config: huntConfig,
      masterSeed,
      delayWindow: DELAY_WINDOW,
    },
    [internalState, paletteMemory, gameBoyMemory, cartridgeRam],
  );

  // --- Dispatch incoming messages ---
  worker.onmessage = (e: MessageEvent<WorkerOutbound>) => {
    const msg = e.data;
    switch (msg.type) {
      case 'progress':
        callbacks.onProgress({
          attempt: msg.attempt,
          attemptsPerSec: msg.attemptsPerSec,
          delay: msg.delay,
          latestDvs: msg.latestDvs,
          latestSpecies: msg.latestSpecies,
          pixels: new Uint8Array(msg.pixels),
          shiny: msg.shiny,
        });
        break;
      case 'shiny':
        callbacks.onShiny({
          state: msg.state,
          species: msg.species,
          dvs: msg.dvs,
          delay: msg.delay,
          attempt: msg.attempt,
        });
        break;
      case 'done':
        callbacks.onDone({
          totalAttempts: msg.totalAttempts,
          shiniesFound: msg.shiniesFound,
        });
        break;
      case 'error':
        callbacks.onError(msg.message);
        break;
    }
  };

  worker.onerror = (ev: ErrorEvent) => {
    callbacks.onError(ev.message ?? 'unknown worker error');
  };

  // --- Return the control handle ---
  return {
    stop() {
      worker.postMessage({ type: 'stop' });
    },
    resume() {
      worker.postMessage({ type: 'resume' });
    },
    terminate() {
      worker.terminate();
    },
  };
}
