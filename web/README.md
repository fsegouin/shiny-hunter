# shiny-hunter (web)

Browser version of the Gen 1 shiny hunter. Sibling to the Python CLI in
the parent directory; eventually static-deployable (GH Pages / Vercel).

**Status:** WasmBoy spike. See [SPIKE.md](./SPIKE.md).

## Why a separate stack

The Python project uses PyBoy, which doesn't run in browsers. The web
version uses [WasmBoy](https://github.com/torch2424/wasmboy) as the
emulator core but reuses the same data model:
- DV decoding + shiny predicate (`src/lib/dv.ts`, port of `dv.py`).
- Per-(game, region) RAM addresses (`src/lib/games.ts`, port of
  `src/shiny_hunter/games/*.py`).
- Eventually: the same `.events.json` macro format the Python `record`
  command emits.

## Develop

```bash
npm install
npm run dev      # http://localhost:3000
npm run typecheck
npm run build
```
