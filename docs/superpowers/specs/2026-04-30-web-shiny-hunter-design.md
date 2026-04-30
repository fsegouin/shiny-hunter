# Web Shiny Hunter — Design Spec

Browser-based shiny hunter that replicates the Python CLI's full workflow. The user plays, saves state, records a macro, and hunts — all client-side, no server, no Python dependency.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Page structure | Wizard (3 steps) | Focused UX, can't misorder steps |
| Hunt worker | Bare WASM core in own Web Worker | Eliminates per-frame postMessage overhead (~50× speedup over WasmBoy API) |
| Monitor style | Stats grid + single preview canvas | Keeps the worker hot, no per-attempt rendering overhead |
| Shiny behavior | Stop on first, offer "Keep scanning?" | Immediate dopamine hit, power users can opt into full window scan |
| Macro source | In-browser recording | Fully self-contained, no Python CLI dependency |

## Wizard Flow

Three steps, one visible at a time. Completed steps collapse into a one-line summary. Data accumulates across steps.

### Step 1 — Save State

ROM file picker, then WasmBoy in windowed mode with on-screen gamepad. User plays until positioned on the "Do you want this Pokémon?" YES/NO dialog. "Save State" pauses the emulator, captures a `WasmBoySaveState`, and stores it in memory.

Summary after completion: game/region identifier.

Outputs carried forward: `romBytes`, `gameConfig`, `savedState`.

### Step 2 — Record Macro

Reloads `savedState` into WasmBoy windowed mode in recording mode. The user accepts the pokemon using the on-screen gamepad, then clicks "Done".

**Recording mode**: We take over WasmBoy's frame loop. Pause WasmBoy's internal RAF playback, run our own `requestAnimationFrame` loop that:

1. Reads responsive-gamepad button states
2. Compares against previous frame — logs press/release transitions as `{ frame, kind, button }`
3. Calls `setJoypadState` with current state
4. Calls `_runWasmExport('executeFrame')` (one await per frame — fine at 60fps, 16.7ms budget vs ~1ms overhead)
5. Increments frame counter

On "Done": stops the loop, releases held buttons, builds an `EventMacro`.

**Auto-verify**: Immediately after recording, switches to headless, reloads state from step 1, replays the just-recorded macro, ticks settle frames, reads species + DVs. If species is non-zero and DVs decode, the macro is good. If not, shows an error and lets the user re-record.

Summary after completion: event count, frame count, verified species name.

Outputs carried forward: `eventMacro` (added to accumulated data).

### Step 3 — Hunt

"Hunt!" button spawns the bare-WASM hunt worker.

**During the hunt**:
- Stats bar: attempt count, attempts/sec, elapsed time, estimated time remaining
- Monitor grid: small cards that fill in as attempts complete. Each card shows delay number + colored dot (grey = normal, green = shiny). Hover/tap shows full DVs in a tooltip.
- Preview canvas: single canvas showing the latest framebuffer snapshot from the worker, updated every ~200ms
- Stop button to pause

**On shiny found**:
- Hunt pauses automatically
- Result panel: species name, full DVs, shiny star
- "Play" button: loads the shiny state into WasmBoy windowed mode on the preview canvas
- "Download .sav" button: loads shiny state, dumps SRAM, downloads as Blob
- "Keep scanning?" button: resumes the hunt worker to scan remaining delays

## Hunt Worker Architecture

A standalone Web Worker that loads WasmBoy's WASM binary directly — no WasmBoy JS library, no internal sub-worker, no postMessage per frame.

### WASM Binary

WasmBoy embeds its WASM binary as a base64 data URI inside `wasmboy.wasm.worker.js`. We extract it once and bundle it as a static asset that the hunt worker fetches and instantiates with `WebAssembly.instantiate`.

The WASM import object is minimal — just `consoleLog` and `abort` stubs (same as what WasmBoy's worker provides).

### Initialization

Main thread sends to worker: ROM bytes, state sections (4 Uint8Arrays from the `.wbst`/`WasmBoySaveState`), macro events, game config (DV addr, species addr, settle frames, SRAM size).

Worker:
1. Fetches and instantiates the WASM binary
2. Resolves memory layout constants from WASM exports (`CARTRIDGE_ROM_LOCATION`, `GAMEBOY_INTERNAL_MEMORY_LOCATION`, `CARTRIDGE_RAM_LOCATION`, `GBC_PALETTE_LOCATION`, `WASMBOY_STATE_LOCATION`, etc.)
3. Writes ROM bytes into `wasmByteMemory` at `CARTRIDGE_ROM_LOCATION`
4. Calls the `config` WASM export
5. Loads the initial state (write 4 sections into memory, call `loadState` export)

### Hunt Loop

Runs synchronously inside the worker. Mirrors the Python `hunter.py` logic:

```
seed offset from master_seed
for each delay in [0, delay_window):
  1. Restore bootstrap state:
     - write state sections into wasmByteMemory
     - call loadState WASM export
  2. Tick `delay` frames (tight for-loop calling executeFrame)
  3. Replay macro:
     - iterate events, tick to each frame boundary, set joypad state
  4. Poll for species:
     - tick one frame at a time
     - read species byte directly from wasmByteMemory[gbMemBase + speciesAddr]
     - stop when non-zero (or after 1200 frame hard cap)
  5. Read DV bytes directly from wasmByteMemory (synchronous, zero overhead)
  6. Check shiny predicate
  7. If shiny: call saveState export, slice state sections, post to main thread
```

All memory reads are direct array indexing into `wasmByteMemory` — no async, no postMessage.

### Optimization: Incremental State Loading

Same as the Python implementation: after the first attempt, save the pre-macro state. For the next attempt, reload the pre-macro state and tick 1 additional frame instead of reloading the bootstrap state and ticking the full delay. Full bootstrap reload only when wrapping around the delay window.

### Communication Protocol

Worker → main thread (via postMessage, infrequent):
- `{ type: 'progress', attempt, attemptsPerSec, delay, latestDvs }` — every ~50 attempts
- `{ type: 'frame', pixels: Uint8Array }` — every ~200ms, framebuffer from `FRAME_LOCATION` in WASM memory
- `{ type: 'shiny', state: { cartridgeRam, gameBoyMemory, paletteMemory, internalState }, species, dvs, delay, attempt }` — on shiny found, state sections as transferable buffers
- `{ type: 'done', totalAttempts, shiniesFound }` — window exhausted or stopped
- `{ type: 'error', message }` — on crash

Main thread → worker:
- `{ type: 'start', rom, state, macro, config, masterSeed }` — begin hunting
- `{ type: 'stop' }` — pause the hunt
- `{ type: 'resume' }` — continue after shiny

### Performance Estimate

| Platform | Estimated att/sec | Avg shiny time |
|---|---|---|
| Desktop (conservative) | 40 | ~3.5 min |
| Desktop (optimistic) | 80 | ~1.7 min |
| Mobile (conservative) | 15 | ~9 min |
| Mobile (optimistic) | 30 | ~4.5 min |

## State Bridge

Both WasmBoy (windowed, steps 1-2) and the bare WASM worker (step 3) use the same underlying memory layout. No format conversion needed.

**WasmBoy → Worker**: `WasmBoySaveState` contains 4 `Uint8Array` sections (`cartridgeRam`, `gameBoyMemory`, `paletteMemory`, `internalState`). Send these directly to the worker, which writes them into `wasmByteMemory` at the offsets resolved from WASM exported constants.

**Worker → WasmBoy**: On shiny, worker slices the 4 sections from `wasmByteMemory` and posts them as transferable buffers. Main thread wraps them into a `WasmBoySaveState` object, loadable by WasmBoy for playback.

The existing `.wbst` serialization format works for both directions — it's just a header + 4 concatenated byte arrays.

## UI Components

**Shared**:
- `StepIndicator` — shows step 1/2/3 progress, completed steps as summary bars
- `GameCanvas` — WasmBoy canvas wrapper (160×144 scaled, pixelated rendering, dark background)
- `Gamepad` — existing on-screen gamepad component (responsive-gamepad based)

**Step 1**:
- `RomPicker` — file input, SHA-1 detection, game config lookup
- `PlaySession` — GameCanvas + Gamepad + "Save State" button

**Step 2**:
- `RecordSession` — GameCanvas + Gamepad + "Done"/"Re-record" buttons, recording indicator
- Verify status display (spinner → success/failure)

**Step 3**:
- `HuntControls` — "Hunt!" / "Stop" buttons, stats bar
- `MonitorGrid` — grid of attempt cards (delay number + colored dot, tooltip with DVs)
- `PreviewCanvas` — GameCanvas showing latest worker framebuffer
- `ShinyResult` — result panel with DVs, "Play" / "Download .sav" / "Keep scanning?" buttons

## Data Flow

```
Step 1                    Step 2                    Step 3
───────                   ───────                   ───────
User plays                Load savedState           Spawn hunt worker
  ↓                       WasmBoy recording mode    Send: rom, state, macro, config
WasmBoy windowed            ↓                         ↓
  ↓                       RAF loop captures          Worker: WASM instantiate
"Save State"              button events              Load ROM + state
  ↓                         ↓                         ↓
savedState in memory      "Done" → EventMacro       Hunt loop (synchronous)
                            ↓                         ↓
                          Auto-verify (headless)    progress/frame → main thread
                          Replay → read DVs         Update grid + preview
                            ↓                         ↓
                          eventMacro verified        Shiny found → pause
                                                    State → WasmBoy playback
                                                    SRAM → .sav download
```

## File Structure

New/modified files under `web/src/`:

```
lib/
  worker/
    hunt-worker.ts        — hunt loop Web Worker
    wasm-core.ts          — bare WASM loading, memory helpers, state read/write
  recorder.ts             — recording session (RAF loop, event capture)
  hunt.ts                 — hunt orchestration (spawn worker, handle messages)

app/
  page.tsx                — wizard shell (step state machine, data accumulation)
  steps/
    SaveState.tsx         — step 1 component
    RecordMacro.tsx       — step 2 component
    Hunt.tsx              — step 3 component
  components/
    StepIndicator.tsx     — wizard progress bar
    MonitorGrid.tsx       — attempt results grid
    ShinyResult.tsx       — shiny celebration + actions
    GameCanvas.tsx        — WasmBoy canvas wrapper
    Gamepad.tsx           — (existing, may need minor refactoring)
```

Existing files kept as-is: `lib/dv.ts`, `lib/games.ts`, `lib/macro.ts`, `lib/rom.ts`, `lib/state.ts`, `lib/emulator/wasmboy.ts`.

## Error Handling

- **Step 1**: ROM not recognized → show warning but allow proceeding (user might have a supported ROM with different hash). No game config → block advancement.
- **Step 2**: Verify fails (species 0) → "Macro didn't capture the pokemon. Try again." with re-record option. Verify reads unexpected data → same treatment.
- **Step 3**: Worker crashes → post error, show "Something went wrong. Retry?" which re-spawns the worker. Worker posts error if WASM instantiation fails.

## Out of Scope

- Multi-worker parallelism (potential future optimization — spawn 2-4 workers with partitioned delay ranges)
- Framebuffer thumbnails per attempt in the grid (potential upgrade from stats-only cards)
- Audio during playback
- Saving hunt progress to IndexedDB / localStorage across sessions
- Sharing results / leaderboards
