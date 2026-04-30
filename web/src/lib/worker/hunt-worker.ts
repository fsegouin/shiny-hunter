/**
 * Hunt-loop Web Worker — bare-WASM implementation.
 *
 * Receives ROM + save state + macro from the main thread, then runs
 * the shiny-hunting loop synchronously inside the worker.  Posts
 * progress, framebuffers, and shiny results back.
 *
 * Mirrors the Python `hunter.py` reset loop: walk a 65 536-frame delay
 * window without replacement, seeded by `masterSeed`.  Each attempt
 * replays the macro, polls for species/DV bytes, and checks the shiny
 * predicate.
 */

import {
  type WasmCore,
  type StateSections,
  instantiateCore,
  loadRom,
  configureCore,
  writeState,
  readState,
  readByte,
  readBytes,
  tick,
  setJoypad,
  clearJoypad,
  getFrameBuffer,
} from './wasm-core';

// ---------------------------------------------------------------------------
// Message protocol — shared with the main-thread hunt.ts
// ---------------------------------------------------------------------------

export interface HuntConfig {
  dvAddr: number;
  speciesAddr: number;
  sramSize: number;
  settleFrames: number;
}

export interface MacroEvent {
  frame: number;
  kind: 'press' | 'release';
  button: string; // lowercase: 'a', 'b', 'up', 'down', etc.
}

export interface StateSectionsTransfer {
  internalState: ArrayBuffer;
  paletteMemory: ArrayBuffer;
  gameBoyMemory: ArrayBuffer;
  cartridgeRam: ArrayBuffer;
}

export type WorkerInbound =
  | {
      type: 'start';
      workerId: number;
      rom: Uint8Array;
      state: StateSectionsTransfer;
      macro: MacroEvent[];
      macroTotalFrames: number;
      config: HuntConfig;
      /** First absolute delay this worker should probe (within [0, delayWindow)). */
      startDelay: number;
      /** Number of contiguous delays this worker walks. */
      delayCount: number;
    }
  | { type: 'pause' }
  | { type: 'resume' }
  | { type: 'stop' };

export interface DVsData {
  atk: number;
  def: number;
  spd: number;
  spc: number;
  hp: number;
}

export type WorkerOutbound =
  | {
      type: 'progress';
      workerId: number;
      attempt: number;
      attemptsPerSec: number;
      delay: number;
      latestDvs: DVsData;
      latestSpecies: number;
      pixels: ArrayBuffer;
      shiny: boolean;
    }
  | {
      type: 'shiny';
      workerId: number;
      state: StateSectionsTransfer;
      species: number;
      dvs: DVsData;
      delay: number;
      attempt: number;
    }
  | { type: 'done'; workerId: number; totalAttempts: number; shiniesFound: number }
  | { type: 'error'; workerId: number; message: string };

// ---------------------------------------------------------------------------
// DV helpers (inline — avoids importing from the lib which may reference DOM)
// ---------------------------------------------------------------------------

const SHINY_ATK = new Set([2, 3, 6, 7, 10, 11, 14, 15]);

function decodeDVs(byte0: number, byte1: number): DVsData {
  const atk = (byte0 >> 4) & 0xf;
  const def_ = byte0 & 0xf;
  const spd = (byte1 >> 4) & 0xf;
  const spc = byte1 & 0xf;
  const hp =
    ((atk & 1) << 3) | ((def_ & 1) << 2) | ((spd & 1) << 1) | (spc & 1);
  return { atk, def: def_, spd, spc, hp };
}

function isShiny(dvs: DVsData): boolean {
  return (
    dvs.def === 10 && dvs.spd === 10 && dvs.spc === 10 && SHINY_ATK.has(dvs.atk)
  );
}

// ---------------------------------------------------------------------------
// Joypad mapping
// ---------------------------------------------------------------------------

/** Map a lowercase button name to setJoypad boolean positions. */
function applyButton(
  state: JoypadState,
  button: string,
  pressed: boolean,
): void {
  switch (button) {
    case 'up':
      state.up = pressed;
      break;
    case 'right':
      state.right = pressed;
      break;
    case 'down':
      state.down = pressed;
      break;
    case 'left':
      state.left = pressed;
      break;
    case 'a':
      state.a = pressed;
      break;
    case 'b':
      state.b = pressed;
      break;
    case 'select':
      state.select = pressed;
      break;
    case 'start':
      state.start = pressed;
      break;
  }
}

interface JoypadState {
  up: boolean;
  right: boolean;
  down: boolean;
  left: boolean;
  a: boolean;
  b: boolean;
  select: boolean;
  start: boolean;
}

function freshJoypad(): JoypadState {
  return {
    up: false,
    right: false,
    down: false,
    left: false,
    a: false,
    b: false,
    select: false,
    start: false,
  };
}

function pushJoypad(core: WasmCore, s: JoypadState): void {
  setJoypad(core, s.up, s.right, s.down, s.left, s.a, s.b, s.select, s.start);
}

// ---------------------------------------------------------------------------
// State conversion helpers
// ---------------------------------------------------------------------------

function transferToSections(t: StateSectionsTransfer): StateSections {
  return {
    internalState: new Uint8Array(t.internalState),
    paletteMemory: new Uint8Array(t.paletteMemory),
    gameBoyMemory: new Uint8Array(t.gameBoyMemory),
    cartridgeRam: new Uint8Array(t.cartridgeRam),
  };
}

/** Copy a Uint8Array into a fresh ArrayBuffer (owned, transferable). */
function toOwnedBuffer(arr: Uint8Array): ArrayBuffer {
  const buf = new ArrayBuffer(arr.byteLength);
  new Uint8Array(buf).set(arr);
  return buf;
}

function sectionsToTransfer(s: StateSections): StateSectionsTransfer {
  return {
    internalState: toOwnedBuffer(s.internalState),
    paletteMemory: toOwnedBuffer(s.paletteMemory),
    gameBoyMemory: toOwnedBuffer(s.gameBoyMemory),
    cartridgeRam: toOwnedBuffer(s.cartridgeRam),
  };
}

// ---------------------------------------------------------------------------
// Worker globals
// ---------------------------------------------------------------------------

/**
 * TypeScript's lib.dom types `self` as `Window`, but inside a dedicated
 * worker `postMessage(msg, transfer[])` has a different overload.
 * We use a minimal interface to avoid pulling in `lib.webworker` (which
 * conflicts with `lib.dom` in the shared tsconfig).
 */
interface WorkerSelf {
  postMessage(message: unknown, transfer: Transferable[]): void;
  postMessage(message: unknown): void;
  onmessage: ((ev: MessageEvent) => void) | null;
}
const ctx = self as unknown as WorkerSelf;

let stopped = false;
let paused = false;
let currentWorkerId = 0;

/** Post a typed message to the main thread. */
function post(msg: WorkerOutbound, transfer?: Transferable[]): void {
  if (transfer) {
    ctx.postMessage(msg, transfer);
  } else {
    ctx.postMessage(msg);
  }
}

/** Async sleep helper for the pause loop. */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ---------------------------------------------------------------------------
// Hunt loop
// ---------------------------------------------------------------------------

async function runHunt(
  workerId: number,
  rom: Uint8Array,
  stateTransfer: StateSectionsTransfer,
  macro: MacroEvent[],
  macroTotalFrames: number,
  config: HuntConfig,
  startDelay: number,
  delayCount: number,
): Promise<void> {
  const tag = `[hunt-worker#${workerId}]`;
  // 1. Fetch WASM binary and boot the emulator core
  console.log(tag, 'phase 1: fetching WASM...');
  const wasmResp = await fetch('/wasmboy-core.wasm');
  const wasmBytes = await wasmResp.arrayBuffer();
  console.log(tag, 'phase 1: instantiating core...');
  const core = await instantiateCore(wasmBytes);
  loadRom(core, rom);
  configureCore(core);
  console.log(tag, 'phase 1: core ready');

  // 2. Write bootstrap state and tick forward to this worker's slice start.
  const bootstrapState = transferToSections(stateTransfer);
  writeState(core, bootstrapState);

  console.log(tag, 'phase 2: startDelay =', startDelay, ', delayCount =', delayCount);
  if (startDelay > 0) {
    const t = performance.now();
    tick(core, startDelay);
    console.log(tag, 'phase 2: ticked to startDelay in', (performance.now() - t).toFixed(0), 'ms');
  }

  let currentDelay = startDelay;
  const maxAttempts = delayCount;
  let attempt = 0;
  let shiniesFound = 0;
  const t0 = performance.now();
  console.log(tag, 'phase 3: entering hunt loop, slice attempts =', maxAttempts);

  // 3. Main hunt loop
  while (attempt < maxAttempts && !stopped) {
    attempt++;
    const delay = currentDelay;

    const measure = workerId === 0 && attempt <= 3;
    const tA = measure ? performance.now() : 0;

    // 3a. Save pre-macro state
    const preMacroState = readState(core, config.sramSize);

    const tB = measure ? performance.now() : 0;

    // 3b. Reset joypad and replay macro events
    clearJoypad(core);
    const joypad = freshJoypad();
    let macroFrame = 0;

    for (const ev of macro) {
      if (ev.frame > macroFrame) {
        tick(core, ev.frame - macroFrame);
        macroFrame = ev.frame;
      }
      applyButton(joypad, ev.button, ev.kind === 'press');
      pushJoypad(core, joypad);
    }

    // Tick the trailing wait in one batched call — `executeMultipleFrames`
    // is much faster than per-frame ticks, so do this rather than relying
    // on the 1-frame settle loop below.
    if (macroTotalFrames > macroFrame) {
      tick(core, macroTotalFrames - macroFrame);
    }

    const tC = measure ? performance.now() : 0;

    // 3c. Reset joypad, poll for species
    clearJoypad(core);

    let species = 0;
    let dvs: DVsData = { atk: 0, def: 0, spd: 0, spc: 0, hp: 0 };
    const HARD_CAP = 1200;
    let settleF = -1;

    for (let f = 0; f < HARD_CAP; f++) {
      tick(core, 1);
      species = readByte(core, config.speciesAddr);
      if (species !== 0) {
        const raw = readBytes(core, config.dvAddr, 2);
        if (raw[0] !== 0 || raw[1] !== 0) {
          dvs = decodeDVs(raw[0], raw[1]);
          settleF = f;
          break;
        }
      }
    }

    if (measure) {
      const tD = performance.now();
      console.log('[hunt-worker] attempt', attempt, 'timings (ms):',
        'readState=', (tB - tA).toFixed(1),
        'macro=', (tC - tB).toFixed(1),
        'settle=', (tD - tC).toFixed(1),
        '(settleF=', settleF, ', macroTotalFrames=', macroTotalFrames, ')');
    }

    // One-shot diagnostic on attempt 1 of worker 0: re-replay the macro
    // with per-event polling to find the earliest frame at which species
    // + DVs become readable. If much earlier than macroTotalFrames the
    // macro is over-recorded and the hunt could run faster by trimming.
    if (workerId === 0 && attempt === 1) {
      writeState(core, preMacroState);
      let mFrame = 0;
      let firstSet = -1;
      const checkSpecies = () => {
        const sp = readByte(core, config.speciesAddr);
        if (sp === 0) return false;
        const raw = readBytes(core, config.dvAddr, 2);
        return raw[0] !== 0 || raw[1] !== 0;
      };
      const POLL_CHUNK = 30;
      const last = macro.length > 0 ? macro[macro.length - 1].frame : 0;
      const tipFrame = Math.max(last, macroTotalFrames);
      const jp = freshJoypad();
      clearJoypad(core);
      for (const ev of macro) {
        while (ev.frame > mFrame) {
          const step = Math.min(POLL_CHUNK, ev.frame - mFrame);
          tick(core, step);
          mFrame += step;
          if (checkSpecies()) { firstSet = mFrame; break; }
        }
        if (firstSet >= 0) break;
        applyButton(jp, ev.button, ev.kind === 'press');
        pushJoypad(core, jp);
      }
      while (firstSet < 0 && mFrame < tipFrame + HARD_CAP) {
        const step = Math.min(POLL_CHUNK, tipFrame + HARD_CAP - mFrame);
        tick(core, step);
        mFrame += step;
        if (checkSpecies()) { firstSet = mFrame; break; }
      }
      console.log('[hunt-worker] earliest-species frame =', firstSet,
        '(macro events end at', last, ', macroTotalFrames =', macroTotalFrames, ')');
    }

    // 3d. Check shiny predicate
    const shiny = isShiny(dvs);

    // 3e. Post progress (with framebuffer) every attempt.
    const elapsed = (performance.now() - t0) / 1000;
    const attemptsPerSec = elapsed > 0 ? attempt / elapsed : 0;
    const pixelBuf = toOwnedBuffer(getFrameBuffer(core));
    post(
      {
        type: 'progress',
        workerId,
        attempt,
        attemptsPerSec,
        delay,
        latestDvs: dvs,
        latestSpecies: species,
        pixels: pixelBuf,
        shiny,
      },
      [pixelBuf],
    );

    // 3f. If shiny: post result and pause this worker.
    if (shiny) {
      shiniesFound++;
      const shinyState = readState(core, config.sramSize);
      const transfer = sectionsToTransfer(shinyState);
      post(
        {
          type: 'shiny',
          workerId,
          state: transfer,
          species,
          dvs,
          delay,
          attempt,
        },
        [
          transfer.internalState,
          transfer.paletteMemory,
          transfer.gameBoyMemory,
          transfer.cartridgeRam,
        ],
      );
      paused = true;
    }

    // 3g. Honor pause requests at attempt boundaries (set by this worker on
    // shiny, or sent by the main thread when another worker found shiny).
    while (paused && !stopped) {
      await sleep(100);
    }
    if (stopped) break;

    // 3h. Advance to next delay (linear within this worker's slice — no wrap).
    if (attempt < maxAttempts) {
      currentDelay++;
      writeState(core, preMacroState);
      tick(core, 1);
    }
  }

  // 4. Done
  post({ type: 'done', workerId, totalAttempts: attempt, shiniesFound });
}

// ---------------------------------------------------------------------------
// Message handler
// ---------------------------------------------------------------------------

ctx.onmessage = (e: MessageEvent<WorkerInbound>) => {
  const msg = e.data;

  switch (msg.type) {
    case 'start':
      stopped = false;
      paused = false;
      currentWorkerId = msg.workerId;
      runHunt(
        msg.workerId,
        msg.rom,
        msg.state,
        msg.macro,
        msg.macroTotalFrames,
        msg.config,
        msg.startDelay,
        msg.delayCount,
      ).catch((err: unknown) => {
        const message =
          err instanceof Error ? err.message : String(err);
        post({ type: 'error', workerId: currentWorkerId, message });
      });
      break;

    case 'pause':
      paused = true;
      break;

    case 'resume':
      paused = false;
      break;

    case 'stop':
      stopped = true;
      paused = false; // unblock any pause loop
      break;
  }
};
