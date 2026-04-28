# WasmBoy spike

Goal: confirm we can build the browser hunter against
[WasmBoy](https://github.com/torch2424/wasmboy) before committing to a full
implementation. Each numbered step on the spike page exercises one
primitive the hunter loop needs.

## Verified API surface (from inspecting `wasmboy@0.7.1`)

| Need | WasmBoy method |
|---|---|
| Load ROM from `Uint8Array` | `WasmBoy.loadROM(bytes)` |
| Headless run (no canvas) | `WasmBoy.config({ headless: true, isAudioEnabled: false, ... })` |
| Frame-by-frame stepping | `WasmBoy._runWasmExport('executeFrame', [])` (loop in JS) |
| Save state | `await WasmBoy.saveState()` → `{ wasmBoyMemory: { gameBoyMemory, cartridgeRam, … }, … }` |
| Load state | `await WasmBoy.loadState(state)` |
| Read GB memory at address | `WasmBoy._getWasmMemorySection(base + addr, base + addr + n)` where `base = WasmBoy._getWasmConstant('GAMEBOY_INTERNAL_MEMORY_LOCATION')` |
| Dump cartridge SRAM (`.sav`) | `(await saveState()).wasmBoyMemory.cartridgeRam` |
| Press / release buttons | `WasmBoy.disableDefaultJoypad(); WasmBoy.setJoypadState({ a: bool, … })` |

## Open questions the spike answers

The buttons on the page are designed to validate, in order:

1. **Init** — does `loadROM` + `play` + `pause` actually leave the emulator
   in a usable state with no canvas?
2. **tick(600) benchmark** — what is the realtime multiplier of headless
   frame stepping? At 1× it's useless; at 50–100× the hunter is viable.
   PyBoy gets ~395×; if WasmBoy is at ~10× we still finish a 1/8192
   hunt in roughly 14 minutes wall-clock. That's the threshold.
3. **saveState / loadState** — round-trip latency. PyBoy is ~1 ms;
   anything under ~10 ms works for the inner loop (we load-state once
   per attempt).
4. **read DV addr** — confirms `_getWasmMemorySection` returns the right
   bytes for a GB address. The values shown right after init are
   garbage (we're not at the DV-roll site); the point is that the call
   succeeds and returns 2 bytes from the configured address.
5. **dump SRAM** — confirms we can extract a real `.sav`.
6. **determinism check** — runs forward N frames from the same state
   twice and asserts the read bytes match. If this fails, our
   per-attempt jitter design is wrong (or `loadState` is doing something
   weird with `rDIV`).

## Findings

- [x] Init succeeds with `headless: true`
- [x] tick benchmark: **31.2× realtime** on an iPhone 16e (Safari, headless)
- [x] saveState: ~9 ms · loadState: ~20 ms (iPhone 16e)
- [x] readBytes returns valid bytes from a known WRAM address
- [ ] dumpSram returns the expected SRAM size — pending
- [ ] determinism check — pending

At 31× realtime headless and ~7s of emulated time per attempt
(load_state + ~256 frames jitter + ~1s macro + 120 frames settle), wall
time is ~225 ms / attempt → roughly **4 attempts/sec**, or **~30 min
average per shiny** at 1/8192 odds. Mobile-viable.

## Bugs found during the spike

1. **`_getWasmMemorySection` and `_getWasmConstant` are async.** The
   first version of the wrapper treated them as sync, so
   `gbMemoryBase` was a `Promise<number>` and every `readBytes` call
   produced an empty `Uint8Array` (which then crashed with "undefined
   is not an object" when downstream code called `.toString` on a byte
   that wasn't there). Fix: await both.
2. **`saveState()` returns Uint8Array views into worker memory.**
   Passing the same returned object to `loadState()` a second time
   trips a "the object can not be cloned" `DOMException` because the
   underlying buffers get transferred during the first call. Fix:
   `cloneState()` (in `src/lib/state.ts`) deep-copies all four sections
   into fresh `Uint8Array`s; the wrapper clones on save AND before each
   load, so callers get a stable reference.

## ROM input

The file picker accepts `.gb`, `.gbc`, and `.zip`. When the dropped file
starts with the ZIP magic (`PK\x03\x04`), `src/lib/rom.ts` decompresses
it via [`fflate`](https://github.com/101arrowz/fflate) and picks the
largest `.gb` / `.gbc` entry inside. SHA-1 detection runs on the
extracted bytes, so registry lookup works regardless of whether the
user dropped a raw ROM or an archive.

## Known caveats so far

- WasmBoy uses Web Workers internally; the host page must serve the
  WASM binary with the correct MIME and not be inside a sandboxed iframe
  with `sandbox` flags that disable workers.
- `saveState` returns a plain JS object containing `Uint8Array`s. To
  serialize for download or persistence it'd need `JSON.stringify` with
  array conversion or `structuredClone` — fine for in-memory use but not
  drop-in for our existing PyBoy `.state` files.
- The default joypad listener (keyboard) is disabled in the wrapper
  because it would race against `setJoypadState` once we wire the
  recorded macros.

## After the spike

If all six checks pass, the next milestone is:

1. Web Worker hosting the hunter loop (so the UI thread stays
   responsive).
2. ~~Macro replay using the `.events.json` format already produced by
   the Python `record` command.~~ **Done in this commit** — see
   section 3 of the spike page.
3. Bootstrap state upload (user takes one in-browser via section 3 and
   downloads as `.wbst`; in-browser play-to-checkpoint UX comes later).
4. Live progress UI + `.sav` Blob download on shiny.

### About `.wbst` vs PyBoy `.state`

The downloadable `.wbst` is a **WasmBoy-specific** save state in a
custom binary container (header + four sections, defined in
`src/lib/state.ts`). It is **not** interchangeable with `.state` files
produced by the Python `shiny-hunt bootstrap` command — PyBoy and
WasmBoy don't share an internal layout.

To produce a `.wbst`, use **section 2** of the spike page: init
windowed, play the game with the on-screen Game Boy buttons (touch
works on iPhone) until the cursor is parked on YES at the
&quot;Do you want this Pokémon?&quot; prompt, then click
**checkpoint here**. The `.wbst` is auto-downloaded and held in
memory so the macro-replay flow in section 4 can load it
immediately.

## Running the spike

```bash
cd web
npm install
npm run dev
# open http://localhost:3000
```
