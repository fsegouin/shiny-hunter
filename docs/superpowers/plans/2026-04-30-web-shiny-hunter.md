# Web Shiny Hunter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the WasmBoy spike page with a 3-step wizard (save state → record macro → hunt) that runs a shiny hunt loop at 40-80 att/sec via a bare-WASM Web Worker.

**Architecture:** WasmBoy handles windowed play/gamepad (steps 1-2). A dedicated Web Worker loads the WasmBoy WASM binary directly for the hunt loop (step 3), eliminating per-frame postMessage overhead. The state bridge uses the same 4-section memory layout both sides already understand.

**Tech Stack:** Next.js 15, React 19, WasmBoy 0.7.1 (windowed play), raw WebAssembly (hunt worker), TypeScript

**Spec:** `docs/superpowers/specs/2026-04-30-web-shiny-hunter-design.md`

---

## File Map

```
web/src/
├── lib/
│   ├── worker/
│   │   ├── wasm-core.ts       — WASM instantiation, memory layout constants, state read/write helpers
│   │   └── hunt-worker.ts     — Web Worker entry: hunt loop, message protocol
│   ├── recorder.ts            — Recording session: RAF frame loop, button event capture
│   ├── hunt.ts                — Main-thread hunt orchestration: spawn worker, handle messages
│   ├── dv.ts                  — (existing, unchanged)
│   ├── games.ts               — (existing, unchanged)
│   ├── macro.ts               — (existing, unchanged)
│   ├── rom.ts                 — (existing, unchanged)
│   ├── state.ts               — (existing, unchanged)
│   └── emulator/
│       └── wasmboy.ts         — (existing, unchanged)
├── app/
│   ├── page.tsx               — Wizard shell: step state machine, data accumulation
│   ├── steps/
│   │   ├── SaveState.tsx      — Step 1: ROM picker + WasmBoy windowed play + save state
│   │   ├── RecordMacro.tsx    — Step 2: Recording mode + auto-verify
│   │   └── Hunt.tsx           — Step 3: Hunt controls + monitor grid + results
│   ├── components/
│   │   ├── StepIndicator.tsx  — Wizard progress bar with completed-step summaries
│   │   ├── GameCanvas.tsx     — WasmBoy canvas wrapper (reusable across steps)
│   │   ├── MonitorGrid.tsx    — Grid of attempt result cards
│   │   └── ShinyResult.tsx    — Shiny celebration panel + actions
│   ├── Gamepad.tsx            — (existing, unchanged)
│   ├── globals.css            — (existing, add new styles)
│   └── gamepad.css            — (existing, unchanged)
└── public/
    └── wasmboy-core.wasm      — Extracted WASM binary from WasmBoy 0.7.1
```

---

### Task 1: Extract the WASM binary

Extract the base64-encoded WASM binary from WasmBoy's worker file and save it as a static asset.

**Files:**
- Create: `web/scripts/extract-wasm.js`
- Create: `web/public/wasmboy-core.wasm`

- [ ] **Step 1: Write the extraction script**

```js
// web/scripts/extract-wasm.js
const fs = require('fs');
const path = require('path');

const workerPath = path.join(
  __dirname,
  '../node_modules/wasmboy/dist/worker/wasmboy.wasm.worker.js',
);
const src = fs.readFileSync(workerPath, 'utf8');
const match = src.match(/data:application\/wasm;base64,([A-Za-z0-9+/=]+)/);
if (!match) {
  console.error('Could not find base64 WASM in wasmboy.wasm.worker.js');
  process.exit(1);
}
const buf = Buffer.from(match[1], 'base64');
const outPath = path.join(__dirname, '../public/wasmboy-core.wasm');
fs.writeFileSync(outPath, buf);
console.log(`Wrote ${buf.length} bytes to ${outPath}`);
```

- [ ] **Step 2: Run the extraction**

Run: `cd /home/florent/Work/shiny-hunter/web && node scripts/extract-wasm.js`
Expected: `Wrote 44973 bytes to <...>/public/wasmboy-core.wasm`

- [ ] **Step 3: Verify the WASM file is valid**

Run: `xxd /home/florent/Work/shiny-hunter/web/public/wasmboy-core.wasm | head -1`
Expected: first bytes are `0061 736d` (`\0asm` magic)

- [ ] **Step 4: Add a postinstall script to package.json**

In `web/package.json`, add to `"scripts"`:

```json
"postinstall": "node scripts/extract-wasm.js"
```

This ensures the WASM binary is re-extracted whenever dependencies are installed.

- [ ] **Step 5: Commit**

```bash
git add web/scripts/extract-wasm.js web/public/wasmboy-core.wasm web/package.json
git commit -m "Extract WasmBoy WASM binary as static asset"
```

---

### Task 2: Build `wasm-core.ts` — bare WASM loader and memory helpers

This module loads the extracted WASM binary, instantiates it, and provides synchronous helpers for state read/write, frame execution, joypad, and memory access.

**Files:**
- Create: `web/src/lib/worker/wasm-core.ts`

- [ ] **Step 1: Create the wasm-core module**

```ts
// web/src/lib/worker/wasm-core.ts

interface WasmExports {
  memory: WebAssembly.Memory;
  executeFrame: () => number;
  executeMultipleFrames: (n: number) => number;
  saveState: () => void;
  loadState: () => void;
  config: (
    bootRom: number, isGbc: number, audioBatch: number,
    graphicsBatch: number, timersBatch: number,
    disableScanline: number, accumulateSamples: number,
    tileRendering: number, tileCaching: number,
    enableAudioDebugging: number,
  ) => void;
  setJoypadState: (
    up: number, right: number, down: number, left: number,
    a: number, b: number, select: number, start: number,
  ) => void;
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

export interface MemoryLayout {
  cartridgeRomLocation: number;
  cartridgeRamLocation: number;
  gbMemoryLocation: number;
  gbMemorySize: number;
  paletteLocation: number;
  paletteSize: number;
  stateLocation: number;
  stateSize: number;
  frameLocation: number;
  frameSize: number;
}

export interface WasmCore {
  exports: WasmExports;
  mem: Uint8Array;
  layout: MemoryLayout;
}

const WASM_IMPORTS = {
  index: {
    consoleLog: () => {},
    consoleLogTimeout: () => {},
  },
  env: {
    abort: () => { console.error('WASM abort'); },
  },
};

export async function instantiateCore(wasmBytes: ArrayBuffer): Promise<WasmCore> {
  const { instance } = await WebAssembly.instantiate(wasmBytes, WASM_IMPORTS);
  const exports = instance.exports as unknown as WasmExports;
  const mem = new Uint8Array(exports.memory.buffer);

  const layout: MemoryLayout = {
    cartridgeRomLocation: exports.CARTRIDGE_ROM_LOCATION.valueOf() as number,
    cartridgeRamLocation: exports.CARTRIDGE_RAM_LOCATION.valueOf() as number,
    gbMemoryLocation: exports.GAMEBOY_INTERNAL_MEMORY_LOCATION.valueOf() as number,
    gbMemorySize: exports.GAMEBOY_INTERNAL_MEMORY_SIZE.valueOf() as number,
    paletteLocation: exports.GBC_PALETTE_LOCATION.valueOf() as number,
    paletteSize: exports.GBC_PALETTE_SIZE.valueOf() as number,
    stateLocation: exports.WASMBOY_STATE_LOCATION.valueOf() as number,
    stateSize: exports.WASMBOY_STATE_SIZE.valueOf() as number,
    frameLocation: exports.FRAME_LOCATION.valueOf() as number,
    frameSize: exports.FRAME_SIZE.valueOf() as number,
  };

  return { exports, mem, layout };
}

export function loadRom(core: WasmCore, romBytes: Uint8Array): void {
  core.mem.set(romBytes, core.layout.cartridgeRomLocation);
}

export function configureCore(core: WasmCore): void {
  // All flags 0: no boot ROM, not GBC, no batch processing, no debug
  core.exports.config(0, 0, 0, 0, 0, 0, 0, 0, 0, 0);
}

export interface StateSections {
  internalState: Uint8Array;
  paletteMemory: Uint8Array;
  gameBoyMemory: Uint8Array;
  cartridgeRam: Uint8Array;
}

export function writeState(core: WasmCore, state: StateSections): void {
  const { mem, layout } = core;
  mem.set(state.internalState, layout.stateLocation);
  mem.set(state.paletteMemory, layout.paletteLocation);
  mem.set(state.gameBoyMemory, layout.gbMemoryLocation);
  mem.set(state.cartridgeRam, layout.cartridgeRamLocation);
  core.exports.loadState();
}

export function readState(core: WasmCore): StateSections {
  const { mem, layout } = core;
  core.exports.saveState();
  return {
    internalState: mem.slice(layout.stateLocation, layout.stateLocation + layout.stateSize),
    paletteMemory: mem.slice(layout.paletteLocation, layout.paletteLocation + layout.paletteSize),
    gameBoyMemory: mem.slice(layout.gbMemoryLocation, layout.gbMemoryLocation + layout.gbMemorySize),
    cartridgeRam: mem.slice(layout.cartridgeRamLocation, layout.cartridgeRamLocation + core.mem[core.layout.cartridgeRomLocation + 327] /* sram size from cartridge type — see Task note */),
  };
}

export function readByte(core: WasmCore, gbAddr: number): number {
  return core.mem[core.layout.gbMemoryLocation + gbAddr];
}

export function readBytes(core: WasmCore, gbAddr: number, length: number): Uint8Array {
  const start = core.layout.gbMemoryLocation + gbAddr;
  return core.mem.slice(start, start + length);
}

export function tick(core: WasmCore, frames: number): void {
  for (let i = 0; i < frames; i++) {
    core.exports.executeFrame();
  }
}

export function setJoypad(
  core: WasmCore,
  up: boolean, right: boolean, down: boolean, left: boolean,
  a: boolean, b: boolean, select: boolean, start: boolean,
): void {
  core.exports.setJoypadState(
    up ? 1 : 0, right ? 1 : 0, down ? 1 : 0, left ? 1 : 0,
    a ? 1 : 0, b ? 1 : 0, select ? 1 : 0, start ? 1 : 0,
  );
}

export function clearJoypad(core: WasmCore): void {
  core.exports.setJoypadState(0, 0, 0, 0, 0, 0, 0, 0);
}

export function getFrameBuffer(core: WasmCore): Uint8Array {
  const { mem, layout } = core;
  return mem.slice(layout.frameLocation, layout.frameLocation + layout.frameSize);
}
```

**Note on `readState` cartridgeRam size:** WasmBoy determines SRAM size from the cartridge type byte at ROM offset 0x147 (i.e., `cartridgeRomLocation + 327`). For Red/Blue/Yellow (MBC3, type 0x13), the size is 32768 bytes. Rather than replicate the full cartridge-type-to-size mapping, we'll pass the known `sramSize` from `GameConfig` into the hunt worker and use it in `readState`. This will be refined in Task 3 when we write the worker.

- [ ] **Step 2: Verify the module type-checks**

Run: `cd /home/florent/Work/shiny-hunter/web && npx tsc --noEmit src/lib/worker/wasm-core.ts`
Expected: no errors (or only errors from imports of types that exist — the file is self-contained)

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/worker/wasm-core.ts
git commit -m "Add bare WASM core loader with synchronous memory helpers"
```

---

### Task 3: Build `hunt-worker.ts` — the hunt loop Web Worker

The worker receives ROM, state, macro, and config from the main thread, instantiates the WASM core, and runs the hunt loop synchronously. It posts progress, framebuffer snapshots, shiny results, and completion back to the main thread.

**Files:**
- Create: `web/src/lib/worker/hunt-worker.ts`

- [ ] **Step 1: Define the message protocol types**

Create a shared types section at the top of the worker file. These types are also used by `hunt.ts` (Task 4), so they'll be importable.

```ts
// web/src/lib/worker/hunt-worker.ts

// === Message protocol types (also importable by hunt.ts) ===

export interface HuntConfig {
  dvAddr: number;
  speciesAddr: number;
  sramSize: number;
  settleFrames: number;
}

export interface MacroEvent {
  frame: number;
  kind: 'press' | 'release';
  button: string;
}

export type WorkerInbound =
  | { type: 'start'; rom: Uint8Array; state: StateSectionsTransfer; macro: MacroEvent[]; macroTotalFrames: number; config: HuntConfig; masterSeed: number; delayWindow: number }
  | { type: 'stop' }
  | { type: 'resume' };

export interface StateSectionsTransfer {
  internalState: ArrayBuffer;
  paletteMemory: ArrayBuffer;
  gameBoyMemory: ArrayBuffer;
  cartridgeRam: ArrayBuffer;
}

export type WorkerOutbound =
  | { type: 'progress'; attempt: number; attemptsPerSec: number; delay: number; latestDvs: { atk: number; def: number; spd: number; spc: number; hp: number } }
  | { type: 'frame'; pixels: ArrayBuffer }
  | { type: 'shiny'; state: StateSectionsTransfer; species: number; dvs: { atk: number; def: number; spd: number; spc: number; hp: number }; delay: number; attempt: number }
  | { type: 'done'; totalAttempts: number; shiniesFound: number }
  | { type: 'error'; message: string };
```

- [ ] **Step 2: Implement the worker message handler and hunt loop**

Append to the same file:

```ts
import {
  instantiateCore, loadRom, configureCore, writeState, readState,
  readByte, readBytes, tick, setJoypad, clearJoypad, getFrameBuffer,
  type WasmCore, type StateSections,
} from './wasm-core';

const BUTTON_MAP: Record<string, [boolean, boolean, boolean, boolean, boolean, boolean, boolean, boolean]> = {
  up:     [true,  false, false, false, false, false, false, false],
  right:  [false, true,  false, false, false, false, false, false],
  down:   [false, false, true,  false, false, false, false, false],
  left:   [false, false, false, true,  false, false, false, false],
  a:      [false, false, false, false, true,  false, false, false],
  b:      [false, false, false, false, false, true,  false, false],
  select: [false, false, false, false, false, false, true,  false],
  start:  [false, false, false, false, false, false, false, true],
};

const SHINY_ATK = new Set([2, 3, 6, 7, 10, 11, 14, 15]);

function decodeDvs(byte0: number, byte1: number) {
  const atk = (byte0 >> 4) & 0xf;
  const def_ = byte0 & 0xf;
  const spd = (byte1 >> 4) & 0xf;
  const spc = byte1 & 0xf;
  const hp = ((atk & 1) << 3) | ((def_ & 1) << 2) | ((spd & 1) << 1) | (spc & 1);
  return { atk, def: def_, spd, spc, hp };
}

function isShiny(dvs: { atk: number; def: number; spd: number; spc: number }) {
  return dvs.def === 10 && dvs.spd === 10 && dvs.spc === 10 && SHINY_ATK.has(dvs.atk);
}

function toSections(t: StateSectionsTransfer): StateSections {
  return {
    internalState: new Uint8Array(t.internalState),
    paletteMemory: new Uint8Array(t.paletteMemory),
    gameBoyMemory: new Uint8Array(t.gameBoyMemory),
    cartridgeRam: new Uint8Array(t.cartridgeRam),
  };
}

function toTransfer(s: StateSections): StateSectionsTransfer {
  return {
    internalState: s.internalState.buffer,
    paletteMemory: s.paletteMemory.buffer,
    gameBoyMemory: s.gameBoyMemory.buffer,
    cartridgeRam: s.cartridgeRam.buffer,
  };
}

// Joypad state tracked across macro replay
const joypadState = { up: false, right: false, down: false, left: false, a: false, b: false, select: false, start: false };

function applyJoypad(core: WasmCore) {
  setJoypad(core, joypadState.up, joypadState.right, joypadState.down, joypadState.left, joypadState.a, joypadState.b, joypadState.select, joypadState.start);
}

function resetJoypad(core: WasmCore) {
  joypadState.up = joypadState.right = joypadState.down = joypadState.left = false;
  joypadState.a = joypadState.b = joypadState.select = joypadState.start = false;
  clearJoypad(core);
}

function replayMacroSync(core: WasmCore, events: MacroEvent[]): number {
  let cur = 0;
  for (const ev of events) {
    if (ev.frame > cur) {
      tick(core, ev.frame - cur);
      cur = ev.frame;
    }
    const btn = ev.button.toLowerCase();
    if (btn in joypadState) {
      (joypadState as Record<string, boolean>)[btn] = ev.kind === 'press';
      applyJoypad(core);
    }
  }
  return cur;
}

function pollForSpecies(
  core: WasmCore, speciesAddr: number, dvAddr: number, hardCap: number,
): { species: number; dvs: ReturnType<typeof decodeDvs>; frames: number } {
  for (let i = 0; i < hardCap; i++) {
    tick(core, 1);
    const species = readByte(core, speciesAddr);
    if (species !== 0) {
      const raw = readBytes(core, dvAddr, 2);
      if (raw[0] !== 0 || raw[1] !== 0) {
        return { species, dvs: decodeDvs(raw[0], raw[1]), frames: i + 1 };
      }
    }
  }
  return { species: 0, dvs: decodeDvs(0, 0), frames: hardCap };
}

let stopRequested = false;
let paused = false;

async function runHunt(msg: Extract<WorkerInbound, { type: 'start' }>) {
  const wasmBytes = await fetch('/wasmboy-core.wasm').then(r => r.arrayBuffer());
  const core = await instantiateCore(wasmBytes);

  loadRom(core, msg.rom);
  configureCore(core);

  const bootstrapState = toSections(msg.state);
  const { config, macro, macroTotalFrames, masterSeed } = msg;
  const delayWindow = msg.delayWindow;
  const maxAttempts = delayWindow;
  const POLL_HARD_CAP = 1200;
  const PROGRESS_INTERVAL = 50;
  const FRAME_INTERVAL_MS = 200;

  let currentDelay = masterSeed % delayWindow;
  let attempt = 0;
  let shiniesFound = 0;
  const t0 = performance.now();
  let lastFrameTime = t0;

  // Initial load: bootstrap state + tick to starting delay
  writeState(core, bootstrapState);
  if (currentDelay > 0) {
    tick(core, currentDelay);
  }

  while (attempt < maxAttempts && !stopRequested) {
    attempt++;
    const delay = currentDelay;

    // Save pre-macro state for incremental advance
    const preMacroState = readState(core);

    // Replay macro (events only, skip trailing frames — poll instead)
    resetJoypad(core);
    replayMacroSync(core, macro);
    resetJoypad(core);

    // Poll for species
    const result = pollForSpecies(core, config.speciesAddr, config.dvAddr, POLL_HARD_CAP);
    const shiny = isShiny(result.dvs);

    // Send progress periodically
    if (attempt % PROGRESS_INTERVAL === 0) {
      const elapsed = (performance.now() - t0) / 1000;
      const msg: WorkerOutbound = {
        type: 'progress',
        attempt,
        attemptsPerSec: Math.round(attempt / elapsed),
        delay,
        latestDvs: result.dvs,
      };
      self.postMessage(msg);
    }

    // Send framebuffer periodically
    const now = performance.now();
    if (now - lastFrameTime >= FRAME_INTERVAL_MS) {
      const pixels = getFrameBuffer(core);
      const msg: WorkerOutbound = { type: 'frame', pixels: pixels.buffer };
      self.postMessage(msg, [pixels.buffer]);
      lastFrameTime = now;
    }

    if (shiny) {
      shiniesFound++;
      const shinyState = readState(core);
      const msg: WorkerOutbound = {
        type: 'shiny',
        state: toTransfer(shinyState),
        species: result.species,
        dvs: result.dvs,
        delay,
        attempt,
      };
      self.postMessage(msg, [
        shinyState.internalState.buffer,
        shinyState.paletteMemory.buffer,
        shinyState.gameBoyMemory.buffer,
        shinyState.cartridgeRam.buffer,
      ]);

      // Pause and wait for resume or stop
      paused = true;
      while (paused && !stopRequested) {
        await new Promise(r => setTimeout(r, 100));
      }
      if (stopRequested) break;
    }

    // Advance to next delay
    if (attempt < maxAttempts) {
      currentDelay = (currentDelay + 1) % delayWindow;
      if (currentDelay === 0) {
        writeState(core, bootstrapState);
      } else {
        writeState(core, preMacroState);
        tick(core, 1);
      }
    }
  }

  const doneMsg: WorkerOutbound = { type: 'done', totalAttempts: attempt, shiniesFound };
  self.postMessage(doneMsg);
}

self.onmessage = (e: MessageEvent<WorkerInbound>) => {
  const msg = e.data;
  switch (msg.type) {
    case 'start':
      stopRequested = false;
      paused = false;
      runHunt(msg).catch(err => {
        const errMsg: WorkerOutbound = { type: 'error', message: String(err) };
        self.postMessage(errMsg);
      });
      break;
    case 'stop':
      stopRequested = true;
      paused = false;
      break;
    case 'resume':
      paused = false;
      break;
  }
};
```

- [ ] **Step 3: Fix `readState` to accept sramSize parameter**

The `readState` function in `wasm-core.ts` needs the sramSize from config rather than trying to derive it from the cartridge type byte. Update:

In `wasm-core.ts`, change the `readState` signature and body:

```ts
export function readState(core: WasmCore, sramSize?: number): StateSections {
  const { mem, layout } = core;
  core.exports.saveState();
  const ramSize = sramSize ?? 0x8000;
  return {
    internalState: mem.slice(layout.stateLocation, layout.stateLocation + layout.stateSize),
    paletteMemory: mem.slice(layout.paletteLocation, layout.paletteLocation + layout.paletteSize),
    gameBoyMemory: mem.slice(layout.gbMemoryLocation, layout.gbMemoryLocation + layout.gbMemorySize),
    cartridgeRam: mem.slice(layout.cartridgeRamLocation, layout.cartridgeRamLocation + ramSize),
  };
}
```

And update all `readState(core)` calls in `hunt-worker.ts` to `readState(core, config.sramSize)`.

- [ ] **Step 4: Add webpack config for the worker**

In `web/next.config.js`, add a rule so the worker file is handled correctly by webpack. Next.js 15 with webpack 5 supports `new Worker(new URL(...), { type: 'module' })` out of the box, but we need to make sure the worker file can import from `wasm-core.ts`. Add to the webpack config:

```js
webpack: (config, { isServer }) => {
  config.experiments = { ...config.experiments, asyncWebAssembly: true };
  if (!isServer) {
    config.output.workerChunkLoading = 'import-scripts';
  }
  return config;
},
```

- [ ] **Step 5: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/worker/hunt-worker.ts web/src/lib/worker/wasm-core.ts web/next.config.js
git commit -m "Add hunt worker with bare-WASM hunt loop"
```

---

### Task 4: Build `hunt.ts` — main-thread hunt orchestration

Spawns the hunt worker, sends start/stop/resume messages, and dispatches incoming messages to callbacks.

**Files:**
- Create: `web/src/lib/hunt.ts`

- [ ] **Step 1: Create the hunt orchestration module**

```ts
// web/src/lib/hunt.ts
import type { WasmBoySaveState } from './state';
import type { EventMacro } from './macro';
import type { GameConfig } from './games';
import type {
  WorkerOutbound, StateSectionsTransfer, HuntConfig, MacroEvent,
} from './worker/hunt-worker';

export interface HuntCallbacks {
  onProgress: (data: Extract<WorkerOutbound, { type: 'progress' }>) => void;
  onFrame: (pixels: Uint8Array) => void;
  onShiny: (data: Extract<WorkerOutbound, { type: 'shiny' }>) => void;
  onDone: (data: Extract<WorkerOutbound, { type: 'done' }>) => void;
  onError: (message: string) => void;
}

export interface HuntHandle {
  stop: () => void;
  resume: () => void;
  terminate: () => void;
}

function stateToTransfer(state: WasmBoySaveState): StateSectionsTransfer {
  const m = state.wasmboyMemory;
  return {
    internalState: m.wasmBoyInternalState.buffer,
    paletteMemory: m.wasmBoyPaletteMemory.buffer,
    gameBoyMemory: m.gameBoyMemory.buffer,
    cartridgeRam: m.cartridgeRam.buffer,
  };
}

export function transferToWasmBoyState(t: StateSectionsTransfer): WasmBoySaveState {
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

function macroToEvents(macro: EventMacro): MacroEvent[] {
  return macro.events.map(e => ({
    frame: e.frame,
    kind: e.kind,
    button: e.button,
  }));
}

export function startHunt(
  rom: Uint8Array,
  state: WasmBoySaveState,
  macro: EventMacro,
  config: GameConfig,
  callbacks: HuntCallbacks,
  masterSeed?: number,
): HuntHandle {
  const worker = new Worker(
    new URL('./worker/hunt-worker.ts', import.meta.url),
    { type: 'module' },
  );

  worker.onmessage = (e: MessageEvent<WorkerOutbound>) => {
    const msg = e.data;
    switch (msg.type) {
      case 'progress':
        callbacks.onProgress(msg);
        break;
      case 'frame':
        callbacks.onFrame(new Uint8Array(msg.pixels));
        break;
      case 'shiny':
        callbacks.onShiny(msg);
        break;
      case 'done':
        callbacks.onDone(msg);
        break;
      case 'error':
        callbacks.onError(msg.message);
        break;
    }
  };

  worker.onerror = (e) => {
    callbacks.onError(e.message ?? 'Worker crashed');
  };

  const huntConfig: HuntConfig = {
    dvAddr: config.partyDvAddr,
    speciesAddr: config.partySpeciesAddr,
    sramSize: config.sramSize,
    settleFrames: config.postMacroSettleFrames,
  };

  // Clone state arrays so transferring doesn't detach the caller's copies
  const clonedState: WasmBoySaveState = {
    wasmboyMemory: {
      wasmBoyInternalState: new Uint8Array(state.wasmboyMemory.wasmBoyInternalState),
      wasmBoyPaletteMemory: new Uint8Array(state.wasmboyMemory.wasmBoyPaletteMemory),
      gameBoyMemory: new Uint8Array(state.wasmboyMemory.gameBoyMemory),
      cartridgeRam: new Uint8Array(state.wasmboyMemory.cartridgeRam),
    },
    date: state.date,
    isAuto: state.isAuto,
  };
  const transfer = stateToTransfer(clonedState);

  worker.postMessage({
    type: 'start',
    rom: rom,
    state: transfer,
    macro: macroToEvents(macro),
    macroTotalFrames: macro.totalFrames,
    config: huntConfig,
    masterSeed: masterSeed ?? Math.floor(Math.random() * 0xFFFFFFFF),
    delayWindow: 1 << 16,
  }, [
    transfer.internalState,
    transfer.paletteMemory,
    transfer.gameBoyMemory,
    transfer.cartridgeRam,
  ]);

  return {
    stop: () => worker.postMessage({ type: 'stop' }),
    resume: () => worker.postMessage({ type: 'resume' }),
    terminate: () => worker.terminate(),
  };
}
```

- [ ] **Step 2: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/hunt.ts
git commit -m "Add main-thread hunt orchestration"
```

---

### Task 5: Build `recorder.ts` — macro recording in the browser

Takes over WasmBoy's frame loop during step 2, polls responsive-gamepad each frame, logs button transitions as an EventMacro.

**Files:**
- Create: `web/src/lib/recorder.ts`

- [ ] **Step 1: Create the recorder module**

```ts
// web/src/lib/recorder.ts
import type { WasmBoyEmulator, Button } from './emulator/wasmboy';
import type { EventEntry, EventMacro } from './macro';

const ALL_BUTTONS: Button[] = ['UP', 'DOWN', 'LEFT', 'RIGHT', 'A', 'B', 'START', 'SELECT'];

const RG_INPUT_MAP: Record<Button, string> = {
  UP: 'DPAD_UP',
  DOWN: 'DPAD_DOWN',
  LEFT: 'DPAD_LEFT',
  RIGHT: 'DPAD_RIGHT',
  A: 'A',
  B: 'B',
  START: 'START',
  SELECT: 'SELECT',
};

export interface RecordingSession {
  stop: () => EventMacro;
}

export function startRecording(emu: WasmBoyEmulator): RecordingSession {
  const events: EventEntry[] = [];
  let frame = 0;
  let running = true;
  const prev: Record<Button, boolean> = {
    UP: false, DOWN: false, LEFT: false, RIGHT: false,
    A: false, B: false, START: false, SELECT: false,
  };

  const RG = emu.responsiveGamepad;
  const inputs = RG.RESPONSIVE_GAMEPAD_INPUTS;

  const loop = async () => {
    while (running) {
      // Wait for next animation frame (keeps ~60fps visual playback)
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      if (!running) break;

      frame++;

      // Poll responsive-gamepad for each button
      for (const btn of ALL_BUTTONS) {
        const inputKey = RG_INPUT_MAP[btn];
        const inputId = (inputs as Record<string, unknown>)[inputKey];
        const state = RG.getState();
        const now = !!(state as Record<string, boolean>)[inputKey];

        if (now !== prev[btn]) {
          events.push({
            frame,
            button: btn.toLowerCase() as Lowercase<Button>,
            kind: now ? 'press' : 'release',
          });
          prev[btn] = now;
        }
      }

      // Apply button state to emulator and tick one frame
      const joypadState: Record<string, boolean> = {};
      for (const btn of ALL_BUTTONS) {
        joypadState[btn] = prev[btn];
      }
      // WasmBoy expects UPPERCASE keys
      (emu as unknown as { setJoypadState?: (s: Record<string, boolean>) => void })
        // Not available on our wrapper, so we use press/release
      ;
      for (const btn of ALL_BUTTONS) {
        if (prev[btn]) {
          emu.pressButton(btn);
        } else {
          emu.releaseButton(btn);
        }
      }

      await emu.tick(1);
    }
  };

  // Kick off the recording loop
  // First, pause WasmBoy's internal playback
  emu.pause().then(() => loop());

  return {
    stop(): EventMacro {
      running = false;

      // Release any held buttons
      for (const btn of ALL_BUTTONS) {
        if (prev[btn]) {
          events.push({
            frame,
            button: btn.toLowerCase() as Lowercase<Button>,
            kind: 'release',
          });
        }
      }

      emu.clearJoypad();

      return {
        events,
        totalFrames: frame,
      };
    },
  };
}
```

**Note:** The responsive-gamepad API varies across versions. The `getState()` method returns an object with `DPAD_UP`, `DPAD_DOWN`, etc. boolean fields. This will need to be verified against the actual responsive-gamepad singleton bundled with WasmBoy 0.7.1 during implementation. If the API is different, the polling logic will need adjustment — the structure of the recorder stays the same.

- [ ] **Step 2: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors (or minor type issues from responsive-gamepad API that we'll fix during implementation)

- [ ] **Step 3: Commit**

```bash
git add web/src/lib/recorder.ts
git commit -m "Add in-browser macro recorder"
```

---

### Task 6: Build shared UI components

Create the reusable components used across wizard steps.

**Files:**
- Create: `web/src/app/components/StepIndicator.tsx`
- Create: `web/src/app/components/GameCanvas.tsx`
- Create: `web/src/app/components/MonitorGrid.tsx`
- Create: `web/src/app/components/ShinyResult.tsx`
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Create StepIndicator**

```tsx
// web/src/app/components/StepIndicator.tsx
'use client';

interface Step {
  label: string;
  summary?: string;
}

interface Props {
  steps: Step[];
  currentStep: number; // 0-indexed
}

export function StepIndicator({ steps, currentStep }: Props) {
  return (
    <div className="step-indicator">
      {steps.map((step, i) => (
        <div
          key={i}
          className={`step-item ${i < currentStep ? 'step-done' : i === currentStep ? 'step-active' : 'step-pending'}`}
        >
          <span className="step-number">{i + 1}</span>
          <span className="step-label">{step.label}</span>
          {i < currentStep && step.summary && (
            <span className="step-summary">{step.summary}</span>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Create GameCanvas**

```tsx
// web/src/app/components/GameCanvas.tsx
'use client';

import { forwardRef } from 'react';

interface Props {
  visible?: boolean;
}

export const GameCanvas = forwardRef<HTMLCanvasElement, Props>(
  function GameCanvas({ visible = true }, ref) {
    return (
      <div
        className="canvas-wrap"
        style={{ display: visible ? 'block' : 'none' }}
      >
        <canvas
          ref={ref}
          width={160}
          height={144}
          className="emu-canvas"
        />
      </div>
    );
  },
);
```

- [ ] **Step 3: Create MonitorGrid**

```tsx
// web/src/app/components/MonitorGrid.tsx
'use client';

import { useState } from 'react';

export interface AttemptResult {
  attempt: number;
  delay: number;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  shiny: boolean;
}

interface Props {
  attempts: AttemptResult[];
}

export function MonitorGrid({ attempts }: Props) {
  const [tooltip, setTooltip] = useState<AttemptResult | null>(null);

  return (
    <div className="monitor-grid-wrap">
      <div className="monitor-grid">
        {attempts.map((a) => (
          <div
            key={a.attempt}
            className={`grid-dot ${a.shiny ? 'grid-dot-shiny' : ''}`}
            onMouseEnter={() => setTooltip(a)}
            onMouseLeave={() => setTooltip(null)}
            title={`#${a.attempt} d=${a.delay} ATK=${a.dvs.atk} DEF=${a.dvs.def} SPD=${a.dvs.spd} SPC=${a.dvs.spc}`}
          />
        ))}
      </div>
      {tooltip && (
        <div className="grid-tooltip">
          <span>#{tooltip.attempt} delay={tooltip.delay}</span>
          <span>ATK {tooltip.dvs.atk} DEF {tooltip.dvs.def} SPD {tooltip.dvs.spd} SPC {tooltip.dvs.spc} HP {tooltip.dvs.hp}</span>
          {tooltip.shiny && <span className="shiny-star">SHINY</span>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create ShinyResult**

```tsx
// web/src/app/components/ShinyResult.tsx
'use client';

interface DVs {
  atk: number;
  def: number;
  spd: number;
  spc: number;
  hp: number;
}

interface Props {
  speciesName: string;
  dvs: DVs;
  attempt: number;
  delay: number;
  onPlay: () => void;
  onDownloadSav: () => void;
  onKeepScanning: () => void;
}

export function ShinyResult({ speciesName, dvs, attempt, delay, onPlay, onDownloadSav, onKeepScanning }: Props) {
  return (
    <div className="shiny-result">
      <div className="shiny-header">SHINY FOUND!</div>
      <div className="shiny-details">
        <span className="shiny-species">{speciesName}</span>
        <span>ATK {dvs.atk} DEF {dvs.def} SPD {dvs.spd} SPC {dvs.spc} HP {dvs.hp}</span>
        <span className="muted">Attempt #{attempt} · Delay {delay}</span>
      </div>
      <div className="row">
        <button onClick={onPlay}>Play</button>
        <button onClick={onDownloadSav}>Download .sav</button>
        <button onClick={onKeepScanning}>Keep scanning?</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Add CSS for new components**

Append to `web/src/app/globals.css`:

```css
/* Step indicator */
.step-indicator {
  display: flex;
  gap: 4px;
  margin-bottom: 24px;
  border-bottom: 1px solid #222;
  padding-bottom: 12px;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 13px;
}
.step-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid #444;
  flex-shrink: 0;
}
.step-done { opacity: 0.6; }
.step-done .step-number { background: #6c6; color: #000; border-color: #6c6; }
.step-active .step-number { background: #9bd; color: #000; border-color: #9bd; }
.step-pending { opacity: 0.3; }
.step-summary { color: #888; font-size: 12px; }

/* Game canvas wrapper */
.canvas-wrap {
  position: relative;
  width: 100%;
  max-width: 720px;
  aspect-ratio: 160 / 144;
  background: #000;
  border: 1px solid #333;
  margin: 12px 0;
}

/* Monitor grid */
.monitor-grid-wrap { position: relative; }
.monitor-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  padding: 8px;
  background: #111;
  border: 1px solid #222;
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}
.grid-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #333;
  cursor: pointer;
  flex-shrink: 0;
}
.grid-dot-shiny {
  background: #0dc850;
  box-shadow: 0 0 6px #0dc850;
}
.grid-tooltip {
  position: absolute;
  top: -4px;
  right: 0;
  transform: translateY(-100%);
  background: #1a1a1a;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 10;
}
.shiny-star { color: #0dc850; font-weight: 700; }

/* Shiny result */
.shiny-result {
  border: 2px solid #0dc850;
  border-radius: 8px;
  padding: 16px;
  margin: 16px 0;
  background: rgba(13, 200, 80, 0.05);
}
.shiny-header {
  font-size: 20px;
  font-weight: 700;
  color: #0dc850;
  margin-bottom: 8px;
}
.shiny-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.shiny-species {
  font-size: 16px;
  font-weight: 700;
  text-transform: capitalize;
}

/* Stats bar */
.stats-bar {
  display: flex;
  gap: 16px;
  padding: 8px 12px;
  background: #111;
  border: 1px solid #222;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: 13px;
}
.stats-bar span { color: #888; }
.stats-bar strong { color: #e6e6e6; }

/* Preview canvas (smaller in hunt view) */
.preview-wrap {
  position: relative;
  width: 320px;
  aspect-ratio: 160 / 144;
  background: #000;
  border: 1px solid #333;
}
```

- [ ] **Step 6: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add web/src/app/components/ web/src/app/globals.css
git commit -m "Add shared UI components: StepIndicator, GameCanvas, MonitorGrid, ShinyResult"
```

---

### Task 7: Build Step 1 — SaveState

The first wizard step: ROM picker → WasmBoy windowed play → save state.

**Files:**
- Create: `web/src/app/steps/SaveState.tsx`

- [ ] **Step 1: Create the SaveState step component**

```tsx
// web/src/app/steps/SaveState.tsx
'use client';

import { useCallback, useRef, useState } from 'react';
import { findBySha1, sha1OfBytes, type GameConfig } from '@/lib/games';
import { loadRomFromFile } from '@/lib/rom';
import { init as initEmulator, type WasmBoyEmulator } from '@/lib/emulator/wasmboy';
import type { WasmBoySaveState } from '@/lib/state';
import { GameCanvas } from '../components/GameCanvas';
import { Gamepad } from '../Gamepad';

interface Props {
  onComplete: (data: {
    romBytes: Uint8Array;
    config: GameConfig;
    savedState: WasmBoySaveState;
  }) => void;
}

export function SaveState({ onComplete }: Props) {
  const [config, setConfig] = useState<GameConfig | null>(null);
  const [romBytes, setRomBytes] = useState<Uint8Array | null>(null);
  const [emu, setEmu] = useState<WasmBoyEmulator | null>(null);
  const [status, setStatus] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [saving, setSaving] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const onRomChosen = useCallback(async (file: File) => {
    setError('');
    try {
      const load = await loadRomFromFile(file);
      const sha = await sha1OfBytes(load.bytes);
      setRomBytes(load.bytes);
      const cfg = findBySha1(sha);
      if (!cfg) {
        setError(`Unknown ROM (SHA-1: ${sha}). Only Red, Blue, Yellow (US) are supported.`);
        return;
      }
      setConfig(cfg);
      setStatus(`${cfg.game}/${cfg.region} detected`);

      // Auto-init windowed mode
      if (!canvasRef.current) return;
      const e = await initEmulator({
        rom: load.bytes,
        mode: 'windowed',
        canvas: canvasRef.current,
      });
      setEmu(e);
      setStatus(`Playing ${cfg.game}/${cfg.region} — navigate to the YES/NO dialog, then click Save State`);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  const saveState = useCallback(async () => {
    if (!emu || !config || !romBytes) return;
    setSaving(true);
    try {
      await emu.pause();
      const state = await emu.saveState();
      onComplete({ romBytes, config, savedState: state });
    } catch (err) {
      setError((err as Error).message);
      setSaving(false);
    }
  }, [emu, config, romBytes, onComplete]);

  return (
    <div>
      <h2>Step 1: Save State</h2>
      <p className="muted">
        Load a Gen 1 ROM, play until the &quot;Do you want this Pok&eacute;mon?&quot;
        YES/NO dialog, then click Save State.
      </p>

      {!emu && (
        <div className="row">
          <input
            type="file"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onRomChosen(f);
            }}
          />
          {status && <span className="ok">{status}</span>}
        </div>
      )}

      {error && <p className="err">{error}</p>}

      <GameCanvas ref={canvasRef} visible={!!emu} />
      {emu && <Gamepad emu={emu} />}

      {emu && (
        <div className="row" style={{ marginTop: 12 }}>
          <button onClick={saveState} disabled={saving}>
            {saving ? 'Saving…' : 'Save State'}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add web/src/app/steps/SaveState.tsx
git commit -m "Add Step 1: SaveState wizard step"
```

---

### Task 8: Build Step 2 — RecordMacro

Recording mode: reload state, capture button inputs, auto-verify.

**Files:**
- Create: `web/src/app/steps/RecordMacro.tsx`

- [ ] **Step 1: Create the RecordMacro step component**

```tsx
// web/src/app/steps/RecordMacro.tsx
'use client';

import { useCallback, useRef, useState } from 'react';
import { init as initEmulator, type WasmBoyEmulator } from '@/lib/emulator/wasmboy';
import type { WasmBoySaveState } from '@/lib/state';
import type { GameConfig } from '@/lib/games';
import type { EventMacro } from '@/lib/macro';
import { replayMacro } from '@/lib/macro';
import { decodeDVs, isShiny } from '@/lib/dv';
import { startRecording, type RecordingSession } from '@/lib/recorder';
import { GameCanvas } from '../components/GameCanvas';
import { Gamepad } from '../Gamepad';

interface Props {
  romBytes: Uint8Array;
  config: GameConfig;
  savedState: WasmBoySaveState;
  onComplete: (macro: EventMacro, verifiedSpecies: string) => void;
}

type Phase = 'init' | 'recording' | 'verifying' | 'verified' | 'error';

export function RecordMacro({ romBytes, config, savedState, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>('init');
  const [emu, setEmu] = useState<WasmBoyEmulator | null>(null);
  const [session, setSession] = useState<RecordingSession | null>(null);
  const [error, setError] = useState('');
  const [verifyInfo, setVerifyInfo] = useState('');
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const macroRef = useRef<EventMacro | null>(null);
  const speciesRef = useRef('');

  const startRecordingFlow = useCallback(async () => {
    if (!canvasRef.current) return;
    setError('');
    try {
      const e = await initEmulator({
        rom: romBytes,
        mode: 'windowed',
        canvas: canvasRef.current,
      });
      await e.loadState(savedState);
      setEmu(e);

      const rec = startRecording(e);
      setSession(rec);
      setPhase('recording');
    } catch (err) {
      setError((err as Error).message);
    }
  }, [romBytes, savedState]);

  const stopRecording = useCallback(async () => {
    if (!session || !emu) return;
    const macro = session.stop();
    macroRef.current = macro;
    setPhase('verifying');

    // Auto-verify: headless replay
    try {
      await emu.shutdown();
      const headless = await initEmulator({ rom: romBytes, mode: 'headless' });
      await headless.loadState(savedState);
      headless.clearJoypad();
      await replayMacro(headless, macro);

      // Tick settle frames
      await headless.tick(config.postMacroSettleFrames);

      const species = await headless.readByte(config.partySpeciesAddr);
      const dvBytes = await headless.readBytes(config.partyDvAddr, 2);
      const dvs = decodeDVs(dvBytes[0], dvBytes[1]);

      await headless.shutdown();

      if (species === 0) {
        setError('Macro didn\'t capture the pokemon. Try recording again.');
        setPhase('error');
        return;
      }

      const name = config.starters[species] ?? `species(0x${species.toString(16)})`;
      const shinyTag = isShiny(dvs) ? ' (shiny!)' : '';
      speciesRef.current = name;
      setVerifyInfo(
        `${macro.events.length} events, ${macro.totalFrames} frames — ` +
        `verified: ${name} ATK=${dvs.atk} DEF=${dvs.def} SPD=${dvs.spd} SPC=${dvs.spc}${shinyTag}`
      );
      setPhase('verified');
    } catch (err) {
      setError(`Verify failed: ${(err as Error).message}`);
      setPhase('error');
    }
  }, [session, emu, romBytes, savedState, config]);

  const confirm = useCallback(() => {
    if (macroRef.current) {
      onComplete(macroRef.current, speciesRef.current);
    }
  }, [onComplete]);

  return (
    <div>
      <h2>Step 2: Record Macro</h2>
      <p className="muted">
        Accept the Pok&eacute;mon using the on-screen buttons, then click Done.
      </p>

      {error && <p className="err">{error}</p>}

      {phase === 'init' && (
        <button onClick={startRecordingFlow}>Start Recording</button>
      )}

      <GameCanvas ref={canvasRef} visible={phase === 'recording'} />
      {phase === 'recording' && emu && <Gamepad emu={emu} />}

      {phase === 'recording' && (
        <div className="row" style={{ marginTop: 12 }}>
          <span className="recording-indicator">REC</span>
          <button onClick={stopRecording}>Done</button>
        </div>
      )}

      {phase === 'verifying' && <p>Verifying macro…</p>}

      {phase === 'verified' && (
        <div>
          <p className="ok">{verifyInfo}</p>
          <button onClick={confirm}>Continue to Hunt</button>
        </div>
      )}

      {phase === 'error' && (
        <button onClick={startRecordingFlow}>Re-record</button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add recording indicator CSS**

Append to `web/src/app/globals.css`:

```css
.recording-indicator {
  display: inline-block;
  padding: 2px 8px;
  background: #d33;
  color: #fff;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  animation: rec-blink 1s infinite;
}
@keyframes rec-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

- [ ] **Step 3: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add web/src/app/steps/RecordMacro.tsx web/src/app/globals.css
git commit -m "Add Step 2: RecordMacro wizard step with auto-verify"
```

---

### Task 9: Build Step 3 — Hunt

The hunt step: start/stop controls, stats bar, monitor grid, preview canvas, shiny results.

**Files:**
- Create: `web/src/app/steps/Hunt.tsx`

- [ ] **Step 1: Create the Hunt step component**

```tsx
// web/src/app/steps/Hunt.tsx
'use client';

import { useCallback, useRef, useState, useEffect } from 'react';
import type { WasmBoySaveState } from '@/lib/state';
import type { GameConfig } from '@/lib/games';
import type { EventMacro } from '@/lib/macro';
import { startHunt, transferToWasmBoyState, type HuntHandle } from '@/lib/hunt';
import type { WorkerOutbound } from '@/lib/worker/hunt-worker';
import { init as initEmulator, type WasmBoyEmulator } from '@/lib/emulator/wasmboy';
import { MonitorGrid, type AttemptResult } from '../components/MonitorGrid';
import { ShinyResult } from '../components/ShinyResult';

interface Props {
  romBytes: Uint8Array;
  config: GameConfig;
  savedState: WasmBoySaveState;
  macro: EventMacro;
}

type Phase = 'ready' | 'hunting' | 'paused-shiny' | 'done';

interface ShinyInfo {
  speciesName: string;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  attempt: number;
  delay: number;
  state: WasmBoySaveState;
}

function downloadBlob(filename: string, bytes: Uint8Array, mime = 'application/octet-stream') {
  const blob = new Blob([bytes as BlobPart], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function Hunt({ romBytes, config, savedState, macro }: Props) {
  const [phase, setPhase] = useState<Phase>('ready');
  const [attempts, setAttempts] = useState<AttemptResult[]>([]);
  const [stats, setStats] = useState({ attempt: 0, attemptsPerSec: 0, elapsed: 0 });
  const [shinies, setShinies] = useState<ShinyInfo[]>([]);
  const [error, setError] = useState('');
  const huntRef = useRef<HuntHandle | null>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const startTimeRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setInterval>>();

  const updateElapsed = useCallback(() => {
    if (startTimeRef.current) {
      setStats(s => ({ ...s, elapsed: (Date.now() - startTimeRef.current) / 1000 }));
    }
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      huntRef.current?.terminate();
    };
  }, []);

  const onStart = useCallback(() => {
    setPhase('hunting');
    setAttempts([]);
    setShinies([]);
    setError('');
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(updateElapsed, 1000);

    const handle = startHunt(romBytes, savedState, macro, config, {
      onProgress(data) {
        setStats({
          attempt: data.attempt,
          attemptsPerSec: data.attemptsPerSec,
          elapsed: (Date.now() - startTimeRef.current) / 1000,
        });
        const SHINY_ATK = new Set([2, 3, 6, 7, 10, 11, 14, 15]);
        const shiny = data.latestDvs.def === 10 && data.latestDvs.spd === 10 &&
          data.latestDvs.spc === 10 && SHINY_ATK.has(data.latestDvs.atk);
        setAttempts(prev => [...prev, {
          attempt: data.attempt,
          delay: data.delay,
          dvs: data.latestDvs,
          shiny,
        }]);
      },
      onFrame(pixels) {
        const canvas = previewRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        // WasmBoy framebuffer is RGBA 160x144
        if (pixels.length >= 160 * 144 * 4) {
          const imageData = new ImageData(new Uint8ClampedArray(pixels.buffer), 160, 144);
          ctx.putImageData(imageData, 0, 0);
        }
      },
      onShiny(data) {
        setPhase('paused-shiny');
        const speciesName = config.starters[data.species] ?? `species(0x${data.species.toString(16)})`;
        const shinyState = transferToWasmBoyState(data.state);
        setShinies(prev => [...prev, {
          speciesName,
          dvs: data.dvs,
          attempt: data.attempt,
          delay: data.delay,
          state: shinyState,
        }]);
        // Also add to the grid
        setAttempts(prev => [...prev, {
          attempt: data.attempt,
          delay: data.delay,
          dvs: data.dvs,
          shiny: true,
        }]);
      },
      onDone(data) {
        setPhase('done');
        if (timerRef.current) clearInterval(timerRef.current);
        setStats(s => ({
          ...s,
          attempt: data.totalAttempts,
          elapsed: (Date.now() - startTimeRef.current) / 1000,
        }));
      },
      onError(message) {
        setError(message);
        setPhase('done');
        if (timerRef.current) clearInterval(timerRef.current);
      },
    });

    huntRef.current = handle;
  }, [romBytes, savedState, macro, config, updateElapsed]);

  const onStop = useCallback(() => {
    huntRef.current?.stop();
    setPhase('done');
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  const onKeepScanning = useCallback(() => {
    huntRef.current?.resume();
    setPhase('hunting');
  }, []);

  const onPlayShiny = useCallback(async (shiny: ShinyInfo) => {
    const canvas = previewRef.current;
    if (!canvas) return;
    const emu = await initEmulator({
      rom: romBytes,
      mode: 'windowed',
      canvas,
    });
    await emu.loadState(shiny.state);
  }, [romBytes]);

  const onDownloadSav = useCallback(async (shiny: ShinyInfo) => {
    const emu = await initEmulator({ rom: romBytes, mode: 'headless' });
    await emu.loadState(shiny.state);
    const sram = await emu.dumpSram();
    await emu.shutdown();
    downloadBlob(`${shiny.speciesName}_shiny.sav`, sram);
  }, [romBytes]);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const estimatedTotal = stats.attemptsPerSec > 0 ? 8192 / stats.attemptsPerSec : 0;

  return (
    <div>
      <h2>Step 3: Hunt</h2>

      {error && <p className="err">{error}</p>}

      {phase === 'ready' && (
        <button onClick={onStart}>Hunt!</button>
      )}

      {(phase === 'hunting' || phase === 'paused-shiny' || phase === 'done') && (
        <>
          <div className="stats-bar">
            <span>Attempts: <strong>{stats.attempt.toLocaleString()}</strong></span>
            <span>Speed: <strong>{stats.attemptsPerSec} att/s</strong></span>
            <span>Elapsed: <strong>{formatTime(stats.elapsed)}</strong></span>
            {stats.attemptsPerSec > 0 && phase === 'hunting' && (
              <span>Est. avg: <strong>~{formatTime(estimatedTotal)}</strong></span>
            )}
          </div>

          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 200 }}>
              <MonitorGrid attempts={attempts} />
            </div>
            <div className="preview-wrap">
              <canvas
                ref={previewRef}
                width={160}
                height={144}
                className="emu-canvas"
              />
            </div>
          </div>

          {phase === 'hunting' && (
            <div className="row" style={{ marginTop: 12 }}>
              <button onClick={onStop}>Stop</button>
            </div>
          )}
        </>
      )}

      {shinies.map((shiny, i) => (
        <ShinyResult
          key={i}
          speciesName={shiny.speciesName}
          dvs={shiny.dvs}
          attempt={shiny.attempt}
          delay={shiny.delay}
          onPlay={() => onPlayShiny(shiny)}
          onDownloadSav={() => onDownloadSav(shiny)}
          onKeepScanning={onKeepScanning}
        />
      ))}

      {phase === 'done' && shinies.length === 0 && (
        <p className="muted">Hunt complete. No shinies found in scanned range.</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add web/src/app/steps/Hunt.tsx
git commit -m "Add Step 3: Hunt wizard step with monitor grid and shiny results"
```

---

### Task 10: Build the wizard page shell

Replace the spike page with the wizard shell that manages step transitions and accumulated data.

**Files:**
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Rewrite page.tsx as the wizard shell**

Replace the entire contents of `web/src/app/page.tsx`:

```tsx
// web/src/app/page.tsx
'use client';

import { useCallback, useState } from 'react';
import type { GameConfig } from '@/lib/games';
import type { WasmBoySaveState } from '@/lib/state';
import type { EventMacro } from '@/lib/macro';
import { StepIndicator } from './components/StepIndicator';
import { SaveState } from './steps/SaveState';
import { RecordMacro } from './steps/RecordMacro';
import { Hunt } from './steps/Hunt';

interface WizardData {
  romBytes: Uint8Array | null;
  config: GameConfig | null;
  savedState: WasmBoySaveState | null;
  macro: EventMacro | null;
  verifiedSpecies: string;
}

export default function HuntPage() {
  const [step, setStep] = useState(0);
  const [data, setData] = useState<WizardData>({
    romBytes: null,
    config: null,
    savedState: null,
    macro: null,
    verifiedSpecies: '',
  });

  const stepDefs = [
    {
      label: 'Save State',
      summary: data.config ? `${data.config.game}/${data.config.region}` : undefined,
    },
    {
      label: 'Record Macro',
      summary: data.macro
        ? `${data.macro.events.length} events — ${data.verifiedSpecies}`
        : undefined,
    },
    {
      label: 'Hunt',
    },
  ];

  const onStep1Complete = useCallback((result: {
    romBytes: Uint8Array;
    config: GameConfig;
    savedState: WasmBoySaveState;
  }) => {
    setData(d => ({
      ...d,
      romBytes: result.romBytes,
      config: result.config,
      savedState: result.savedState,
    }));
    setStep(1);
  }, []);

  const onStep2Complete = useCallback((macro: EventMacro, verifiedSpecies: string) => {
    setData(d => ({ ...d, macro, verifiedSpecies }));
    setStep(2);
  }, []);

  return (
    <main>
      <h1>shiny-hunter web</h1>
      <StepIndicator steps={stepDefs} currentStep={step} />

      {step === 0 && (
        <SaveState onComplete={onStep1Complete} />
      )}

      {step === 1 && data.romBytes && data.config && data.savedState && (
        <RecordMacro
          romBytes={data.romBytes}
          config={data.config}
          savedState={data.savedState}
          onComplete={onStep2Complete}
        />
      )}

      {step === 2 && data.romBytes && data.config && data.savedState && data.macro && (
        <Hunt
          romBytes={data.romBytes}
          config={data.config}
          savedState={data.savedState}
          macro={data.macro}
        />
      )}
    </main>
  );
}
```

- [ ] **Step 2: Verify type-checking passes**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run typecheck`
Expected: no errors

- [ ] **Step 3: Verify the build succeeds**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run build`
Expected: build succeeds (may have warnings about unused old imports, which are fine since we replaced the page)

- [ ] **Step 4: Commit**

```bash
git add web/src/app/page.tsx
git commit -m "Replace spike page with 3-step wizard shell"
```

---

### Task 11: Integration test — end-to-end in dev server

Verify the full flow works in a browser.

**Files:** None (manual testing)

- [ ] **Step 1: Start the dev server**

Run: `cd /home/florent/Work/shiny-hunter/web && pnpm run dev`

- [ ] **Step 2: Test Step 1 — Save State**

1. Open http://localhost:3000
2. Verify step indicator shows step 1 active, steps 2-3 greyed out
3. Load a Pokemon Red US ROM
4. Verify game starts in windowed mode with on-screen gamepad
5. Play to the YES/NO dialog
6. Click "Save State"
7. Verify step 1 collapses to summary, step 2 becomes active

- [ ] **Step 3: Test Step 2 — Record Macro**

1. Click "Start Recording"
2. Verify game reloads from saved state
3. Use on-screen gamepad to accept the pokemon
4. Click "Done"
5. Verify "Verifying macro…" appears
6. Verify verify succeeds and shows species + DVs
7. Click "Continue to Hunt"
8. Verify step 2 collapses, step 3 becomes active

- [ ] **Step 4: Test Step 3 — Hunt**

1. Click "Hunt!"
2. Verify stats bar updates (attempts, att/sec, elapsed)
3. Verify monitor grid fills with dots
4. Verify preview canvas shows game frames
5. If a shiny is found: verify result panel appears with species, DVs, and action buttons
6. Test "Download .sav" button — verify a .sav file downloads
7. Test "Keep scanning?" — verify hunt resumes
8. Test "Stop" button — verify hunt stops

- [ ] **Step 5: Fix any issues found during testing**

Address any bugs discovered during the manual test pass.

- [ ] **Step 6: Commit any fixes**

```bash
git add -A
git commit -m "Fix issues found during integration testing"
```

---

### Task 12: Performance benchmark

Measure actual att/sec to validate the design's performance claims.

**Files:** None (manual testing)

- [ ] **Step 1: Run the hunt for 1000+ attempts**

Start a hunt and let it run. Watch the stats bar for the att/sec figure.

- [ ] **Step 2: Record the benchmark results**

Note:
- Desktop att/sec (browser + OS)
- Mobile att/sec if available (device + browser)
- Whether the preview canvas updates smoothly
- Whether the main thread stays responsive (can click Stop, tooltips work)

- [ ] **Step 3: Tune progress/frame intervals if needed**

If att/sec is lower than expected, try:
- Increasing `PROGRESS_INTERVAL` from 50 to 100 (less postMessage overhead)
- Increasing `FRAME_INTERVAL_MS` from 200 to 500
- Check if `readState` (for incremental state save) is the bottleneck — if so, consider using `mem.set`/`mem.slice` more efficiently

- [ ] **Step 4: Commit any tuning changes**

```bash
git add -A
git commit -m "Tune hunt worker performance parameters"
```
