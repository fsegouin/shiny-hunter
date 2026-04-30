/**
 * Main-thread hunt orchestration.
 *
 * Spawns N hunt Web Workers, each walking a contiguous slice of the
 * 65,536-frame delay window in parallel. Aggregates their progress
 * messages into a single stream the UI can consume, and coordinates
 * pause/resume/stop across the pool. Per-worker progress is also
 * surfaced through `onWorkerProgress` so a monitor grid can render
 * one cell per worker.
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

export interface WorkerProgress {
  workerId: number;
  attempt: number;
  delay: number;
  latestDvs: DVsData;
  latestSpecies: number;
  pixels: Uint8Array;
  shiny: boolean;
}

export interface HuntCallbacks {
  /** Aggregate progress across all workers — fired on every per-worker tick. */
  onProgress(data: {
    totalAttempts: number;
    attemptsPerSec: number;
    workerCount: number;
  }): void;
  /** Per-worker progress — feeds the monitor grid. */
  onWorkerProgress(data: WorkerProgress): void;
  onShiny(data: {
    workerId: number;
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

/** Pick a sensible worker pool size based on the host's reported core count. */
export function defaultWorkerCount(): number {
  const cores = (typeof navigator !== 'undefined' && navigator.hardwareConcurrency) || 4;
  return Math.max(2, Math.min(6, cores - 1));
}

/** Build the inbound state buffers, owning fresh copies the worker can detach. */
function cloneStateBuffers(state: WasmBoySaveState): StateSectionsTransfer {
  return {
    internalState: new Uint8Array(state.wasmboyMemory.wasmBoyInternalState).buffer as ArrayBuffer,
    paletteMemory: new Uint8Array(state.wasmboyMemory.wasmBoyPaletteMemory).buffer as ArrayBuffer,
    gameBoyMemory: new Uint8Array(state.wasmboyMemory.gameBoyMemory).buffer as ArrayBuffer,
    cartridgeRam: new Uint8Array(state.wasmboyMemory.cartridgeRam).buffer as ArrayBuffer,
  };
}

/**
 * Spawn `workerCount` workers, each assigned a contiguous slice of the
 * delay window. Returns a handle for stop / resume / terminate.
 *
 * Slices are computed by integer division; the last worker absorbs the
 * remainder so we always cover the full window.
 */
export function startHunt(
  rom: Uint8Array,
  state: WasmBoySaveState,
  macro: EventMacro,
  config: GameConfig,
  callbacks: HuntCallbacks,
  workerCount: number = defaultWorkerCount(),
): HuntHandle {
  const macroEvents: MacroEvent[] = macro.events.map((e) => ({
    frame: e.frame,
    kind: e.kind,
    button: e.button,
  }));
  const huntConfig = {
    dvAddr: config.partyDvAddr,
    speciesAddr: config.partySpeciesAddr,
    sramSize: config.sramSize,
    settleFrames: config.postMacroSettleFrames,
  };

  const baseSlice = Math.floor(DELAY_WINDOW / workerCount);
  const workers: Worker[] = [];
  const lastAttempt = new Array(workerCount).fill(0);
  const lastSpeed = new Array(workerCount).fill(0);
  const doneCount = { n: 0 };
  const totals = { totalAttempts: 0, shiniesFound: 0 };
  let errored = false;

  const broadcast = (msg: { type: 'pause' | 'resume' | 'stop' }) => {
    for (const w of workers) w.postMessage(msg);
  };

  const emitAggregateProgress = () => {
    let total = 0;
    let speed = 0;
    for (let i = 0; i < workerCount; i++) {
      total += lastAttempt[i];
      speed += lastSpeed[i];
    }
    callbacks.onProgress({
      totalAttempts: total,
      attemptsPerSec: speed,
      workerCount,
    });
  };

  for (let i = 0; i < workerCount; i++) {
    const startDelay = i * baseSlice;
    const delayCount = i === workerCount - 1
      ? DELAY_WINDOW - startDelay
      : baseSlice;

    const w = new Worker(new URL('./worker/hunt-worker.ts', import.meta.url));
    workers.push(w);

    const buffers = cloneStateBuffers(state);

    w.onmessage = (e: MessageEvent<WorkerOutbound>) => {
      const msg = e.data;
      switch (msg.type) {
        case 'progress':
          lastAttempt[msg.workerId] = msg.attempt;
          lastSpeed[msg.workerId] = msg.attemptsPerSec;
          callbacks.onWorkerProgress({
            workerId: msg.workerId,
            attempt: msg.attempt,
            delay: msg.delay,
            latestDvs: msg.latestDvs,
            latestSpecies: msg.latestSpecies,
            pixels: new Uint8Array(msg.pixels),
            shiny: msg.shiny,
          });
          emitAggregateProgress();
          break;
        case 'shiny':
          // Pause every other worker at its next attempt boundary while the
          // user reviews this shiny. The worker that found it is already
          // self-paused.
          for (let j = 0; j < workers.length; j++) {
            if (j !== msg.workerId) workers[j].postMessage({ type: 'pause' });
          }
          callbacks.onShiny({
            workerId: msg.workerId,
            state: msg.state,
            species: msg.species,
            dvs: msg.dvs,
            delay: msg.delay,
            attempt: msg.attempt,
          });
          break;
        case 'done':
          totals.totalAttempts += msg.totalAttempts;
          totals.shiniesFound += msg.shiniesFound;
          doneCount.n++;
          if (doneCount.n === workerCount && !errored) {
            callbacks.onDone({
              totalAttempts: totals.totalAttempts,
              shiniesFound: totals.shiniesFound,
            });
          }
          break;
        case 'error':
          if (!errored) {
            errored = true;
            callbacks.onError(`worker#${msg.workerId}: ${msg.message}`);
          }
          break;
      }
    };

    w.onerror = (ev: ErrorEvent) => {
      if (!errored) {
        errored = true;
        callbacks.onError(`worker#${i}: ${ev.message ?? 'unknown worker error'}`);
      }
    };

    w.postMessage(
      {
        type: 'start' as const,
        workerId: i,
        rom,
        state: buffers,
        macro: macroEvents,
        macroTotalFrames: macro.totalFrames,
        config: huntConfig,
        startDelay,
        delayCount,
      },
      [
        buffers.internalState,
        buffers.paletteMemory,
        buffers.gameBoyMemory,
        buffers.cartridgeRam,
      ],
    );
  }

  return {
    stop() { broadcast({ type: 'stop' }); },
    resume() { broadcast({ type: 'resume' }); },
    terminate() {
      for (const w of workers) w.terminate();
    },
  };
}
