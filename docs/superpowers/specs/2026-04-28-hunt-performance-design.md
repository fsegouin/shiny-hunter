# Hunt Performance: Early-Exit Polling + Parallel Workers

**Date:** 2026-04-28
**Status:** Draft

## Problem

Single-threaded hunt loop runs ~10.8 attempts/s on Red US. Each attempt ticks ~908 frames, but only ~188 are button presses — the remaining 720 are blind waiting for the party to populate. At 1/8192 odds, average time to shiny is ~13 minutes. We want to bring this under 1 minute.

## Design

Three changes, each independent but multiplicative:

### 1. Early-Exit Polling

**Current flow per attempt:**
```
load_state → tick(jitter) → macro.run() [788 frames] → tick(120 settle) → read DVs
```

**New flow:**
```
load_state → tick(jitter) → play button presses → poll species each frame → read DVs
```

The macro's button presses (A×4 for the YAML starter macro) complete within ~188 frames. After the last button event, we tick frame-by-frame and check `party_species_addr` on each frame. The moment a non-zero species byte appears, we read DVs and stop.

**Implementation:**

Add a `run_until_species` function in `hunter.py` that:

1. Extracts the button-press timeline from the macro (works for both YAML and EventMacro formats)
2. Ticks frame-by-frame through the macro's button events
3. After the last button event, continues ticking frame-by-frame, checking `emu.read_byte(species_addr)` each frame
4. Returns as soon as species != 0, or after a hard cap (e.g., 1200 frames) to prevent infinite loops on broken macros

For the YAML macro, the button timeline is derived from the steps: each step produces a press at a known frame offset. The `after` values on all steps except the last are preserved (they're needed for dialog timing). The last step's `after` and `post_macro_settle_frames` are replaced by the polling loop.

For EventMacro, all events are replayed at their original frame indices. After the last event's frame, polling begins. `total_frames` is ignored.

**Estimated speedup:** If species appears ~100-200 frames after the last button press (typical for the cry animation + `AddPartyMon`), total frames drop from ~908 to ~300-400. **~2-3x speedup.**

**Hard cap:** 1200 frames after the last button event. If species hasn't appeared by then, the macro is broken. Log a warning and treat as a failed attempt (species=0, not shiny).

### 2. Parallel Workers

Spawn N worker processes (default: `os.cpu_count() - 1`, capped at 11 on this machine), each running its own hunt loop with its own PyBoy instance.

**Architecture:**

```
Main process
  ├── spawns N workers via multiprocessing
  ├── each worker gets: rom_path, state_bytes, macro_path, cfg, seed_offset
  ├── workers run independent hunt loops (no shared state)
  ├── on shiny found: worker puts result on a multiprocessing.Queue
  ├── main process monitors queue + aggregates progress
  └── on first shiny (or user Ctrl+C): signals all workers to stop
```

**Attempt partitioning:** Each worker gets a different `master_seed` derived from the user's seed + worker index. Worker 0 gets `seed`, worker 1 gets `seed + 1`, etc. Each worker runs attempts 1..max_attempts/N independently. This avoids any synchronization between workers.

**Worker function signature:**
```python
def _hunt_worker(
    rom_path: Path,
    state_bytes: bytes,
    macro_path: Path,
    cfg_key: tuple[str, str],   # (game, region) — GameConfig can't be pickled
    master_seed: int,
    max_attempts: int,
    species_addr: int,
    dv_addr: int,
    result_queue: Queue,        # sends back (species, dvs, attempt, delay, state_bytes)
    stop_event: Event,          # checked each attempt
) -> None:
```

Workers create their own `Emulator` instance on startup. GameConfig is looked up by key inside the worker (avoids pickling frozen dataclasses with complex fields).

**Result payload:** When a shiny is found, the worker saves the emulator state to bytes and sends:
```python
{
    "worker": worker_id,
    "attempt": attempt_number,
    "master_seed": seed,
    "delay": delay,
    "species": species_id,
    "dvs": dvs,
    "state_bytes": emulator_state_bytes,  # for resume
}
```

**Progress reporting:** Each worker periodically (every 100 attempts) puts a progress update on a separate progress queue. The main process aggregates across all workers for the Rich live display.

**Shutdown:** `multiprocessing.Event` — main process sets it when a shiny is found or on Ctrl+C. Workers check `stop_event.is_set()` at the top of each attempt loop.

**Estimated speedup:** Linear with core count. 11 workers = **~11x**.

### 3. Shiny Output: Save State + Resume Command

**Current behavior on shiny:** Run save macro, dump SRAM, write `.sav` + `.trace.json`.

**New behavior on shiny:**
1. Save the PyBoy emulator state (the moment after DVs are confirmed shiny)
2. Write `.state` + `.trace.json` to the output directory
3. No SRAM dump, no save macro execution

**Output files:**
- `shinies/<species>_<region>_<attempt>.state` — PyBoy save-state
- `shinies/<species>_<region>_<attempt>.trace.json` — deterministic replay metadata

**New `resume` command:**
```bash
shiny-hunt resume --rom roms/red.gb --state shinies/eevee_us_004200.state
```

Opens PyBoy in windowed mode with the state loaded. The user takes control: save in-game, check stats, keep playing, etc.

Implementation is trivial — identical to `bootstrap` but loads an existing state instead of starting from ROM boot:
```python
@main.command()
@click.option("--rom", required=True, ...)
@click.option("--state", required=True, ...)
def resume(rom, state):
    emu = Emulator(rom, headless=False)
    emu.load_state(state.read_bytes())
    while emu.tick(1, render=True):
        pass
    emu.stop()
```

### Config Changes

- `save_macro` field in GameConfig becomes unused by the hunt loop (kept for backward compat, can be removed later)
- `post_macro_settle_frames` becomes unused (replaced by early-exit polling)
- Add `--workers N` flag to `run` command (default: `cpu_count() - 1`)

### CLI Changes

**`run` command:**
- Add `--workers N` option (default: auto-detect cores - 1)
- `--workers 1` for single-threaded mode (backward compat / debugging)
- Progress display shows aggregate rate across all workers

**New `resume` command:**
- `--rom` (required): ROM path
- `--state` (required): state file to load

**`replay` command:** Unchanged (single-threaded verification).

**`verify` command:** Uses early-exit polling too (faster feedback).

## Projected Performance

| Optimization | Attempts/s | Avg time to shiny |
|---|---|---|
| Current | 10.8 | ~13 min |
| + Early-exit polling (~3x) | ~30 | ~4.5 min |
| + 11 parallel workers (~11x) | ~330 | ~25 sec |

## Testing

- **Early-exit polling:** Unit test with a fake emulator that sets species at a known frame. Verify polling stops at the right frame and reads correct DVs.
- **Parallel workers:** Integration test: run with `--workers 2 --max-attempts 100 --seed 0` and verify deterministic output matches single-threaded run with the same seed range.
- **Resume command:** CLI help test (already pattern-established). Manual test with a real ROM.

## Out of Scope

- GPU acceleration or JIT compilation of PyBoy
- Web frontend parallelism (WasmBoy is single-threaded by nature)
- Macro format changes (existing YAML and EventMacro formats work as-is)
