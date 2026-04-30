import type { WasmBoySaveState } from './state';
import type { EventMacro } from './macro';
import type { GameConfig } from './games';
import type {
  WorkerOutbound,
  StateSectionsTransfer,
  MacroEvent,
  DVsData,
} from './worker/hunt-worker';

export interface VerifyResult {
  species: number;
  dvs: DVsData;
}

export function verifyMacro(
  rom: Uint8Array,
  state: WasmBoySaveState,
  macro: EventMacro,
  config: GameConfig,
): Promise<VerifyResult> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(
      new URL('./worker/hunt-worker.ts', import.meta.url),
    );

    const macroEvents: MacroEvent[] = macro.events.map((e) => ({
      frame: e.frame,
      kind: e.kind,
      button: e.button,
    }));

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

    let resolved = false;
    worker.onmessage = (e: MessageEvent<WorkerOutbound>) => {
      if (resolved) return;
      const msg = e.data;
      switch (msg.type) {
        case 'progress':
          resolved = true;
          resolve({ species: msg.latestSpecies, dvs: msg.latestDvs });
          worker.postMessage({ type: 'stop' });
          setTimeout(() => worker.terminate(), 100);
          break;
        case 'shiny':
          resolved = true;
          resolve({ species: msg.species, dvs: msg.dvs });
          worker.postMessage({ type: 'stop' });
          setTimeout(() => worker.terminate(), 100);
          break;
        case 'done':
          if (!resolved) {
            reject(new Error('Hunt ended without producing a result'));
          }
          worker.terminate();
          break;
        case 'error':
          resolved = true;
          reject(new Error(msg.message));
          worker.terminate();
          break;
      }
    };

    worker.postMessage(
      {
        type: 'start' as const,
        rom,
        state: stateTransfer,
        macro: macroEvents,
        macroTotalFrames: macro.totalFrames,
        config: {
          dvAddr: config.partyDvAddr,
          speciesAddr: config.partySpeciesAddr,
          sramSize: config.sramSize,
          settleFrames: config.postMacroSettleFrames,
        },
        masterSeed: 0,
        delayWindow: 1,
      },
      [internalState, paletteMemory, gameBoyMemory, cartridgeRam],
    );
  });
}
