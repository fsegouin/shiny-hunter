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

Fill this in after running the spike against a real ROM:

- [ ] Init succeeds with `headless: true`
- [ ] tick benchmark: ___× realtime
- [ ] saveState median latency: ___ ms
- [ ] loadState median latency: ___ ms
- [ ] readBytes returns expected non-zero values from a known WRAM addr
- [ ] dumpSram returns 0x8000 bytes for Red/Blue
- [ ] determinism check PASSES from the same state

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
2. Macro replay using the `.events.json` format already produced by the
   Python `record` command.
3. Bootstrap state upload (user provides the `.state` from the Python
   tool for v1; in-browser bootstrap comes later).
4. Live progress UI + `.sav` Blob download on shiny.

## Running the spike

```bash
cd web
npm install
npm run dev
# open http://localhost:3000
```
