# Hunt Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up the shiny hunt loop from ~10.8 attempts/s to ~330/s via early-exit polling, parallel workers, and a resume command.

**Architecture:** Replace the fixed-frame macro settle + post_macro_settle with frame-by-frame species polling that exits the moment a Pokémon appears in RAM. Add multiprocessing workers that each run an independent PyBoy instance. On shiny, save emulator state (not SRAM) so the user can resume interactively.

**Tech Stack:** Python 3.11+, PyBoy 2.7+, multiprocessing, click, rich

---

### Task 1: Early-Exit Polling — `run_until_species`

**Files:**
- Create: `src/shiny_hunter/polling.py`
- Create: `tests/test_polling.py`

This is the core optimization. A new function that replays a macro's button presses, then polls RAM frame-by-frame until a species byte appears — replacing the fixed 720-frame blind wait.

- [ ] **Step 1: Write the failing test for `run_until_species` with a YAML Macro**

```python
# tests/test_polling.py
"""Tests for early-exit species polling."""
from __future__ import annotations

from shiny_hunter.dv import DVs, decode_dvs
from shiny_hunter.macro import Macro, Step, EventMacro, Event
from shiny_hunter.polling import run_until_species

SPECIES_ADDR = 0xD164
DV_ADDR = 0xD186


class _FakeEmulator:
    """Fake that sets species at a known frame and tracks total ticks."""

    def __init__(self, species_at_frame: int, species: int = 0x99,
                 dv_bytes: tuple[int, int] = (0xAA, 0xAA)):
        self.species_at_frame = species_at_frame
        self._species = species
        self._dv_bytes = dv_bytes
        self.frame = 0
        self.buttons_pressed: list[tuple[int, str]] = []

    def tick(self, frames: int = 1, *, render: bool = False) -> bool:
        self.frame += frames
        return True

    def button(self, key: str, hold_frames: int = 2) -> None:
        self.buttons_pressed.append((self.frame, key))

    def button_press(self, key: str) -> None:
        self.buttons_pressed.append((self.frame, f"+{key}"))

    def button_release(self, key: str) -> None:
        self.buttons_pressed.append((self.frame, f"-{key}"))

    def read_byte(self, addr: int) -> int:
        if addr == SPECIES_ADDR and self.frame >= self.species_at_frame:
            return self._species
        return 0

    def read_bytes(self, addr: int, length: int) -> bytes:
        if addr == DV_ADDR and self.frame >= self.species_at_frame:
            return bytes(self._dv_bytes)
        return b"\x00" * length


def test_polls_until_species_appears():
    m = Macro(name="t", steps=(
        Step(button="a", hold=2, after=60),
        Step(button="a", hold=2, after=60),
    ))
    emu = _FakeEmulator(species_at_frame=150, species=0x99, dv_bytes=(0xAA, 0xAA))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0x99
    assert dvs.atk == 10
    assert dvs.def_ == 10
    assert frames == 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_polling.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shiny_hunter.polling'`

- [ ] **Step 3: Implement `run_until_species`**

```python
# src/shiny_hunter/polling.py
"""Early-exit macro replay: poll species RAM instead of waiting fixed frames."""
from __future__ import annotations

from .dv import DVs, decode_dvs
from .macro import Macro, EventMacro, Step

POLL_HARD_CAP = 1200


def run_until_species(
    emu,
    macro: Macro | EventMacro,
    *,
    species_addr: int,
    dv_addr: int,
    hard_cap: int = POLL_HARD_CAP,
) -> tuple[int, DVs, int]:
    """Replay macro button presses, then poll RAM each frame until species appears.

    Returns (species, dvs, total_frames_ticked).
    """
    if isinstance(macro, Macro):
        last_frame = _run_macro_steps(emu, macro, species_addr)
    else:
        last_frame = _run_event_macro(emu, macro, species_addr)

    if last_frame is not None:
        return _read_result(emu, species_addr, dv_addr, last_frame)

    frame = emu.frame if hasattr(emu, "frame") else 0
    return _poll_loop(emu, species_addr, dv_addr, hard_cap, frame)


def _check_species(emu, species_addr: int) -> int:
    return emu.read_byte(species_addr)


def _read_result(emu, species_addr, dv_addr, frame):
    species = emu.read_byte(species_addr)
    raw = emu.read_bytes(dv_addr, 2)
    dvs = decode_dvs(raw[0], raw[1])
    return species, dvs, frame


def _poll_loop(emu, species_addr, dv_addr, remaining, frame):
    for _ in range(remaining):
        emu.tick(1)
        frame += 1
        if _check_species(emu, species_addr):
            return _read_result(emu, species_addr, dv_addr, frame)
    return 0, decode_dvs(0, 0), frame


def _run_macro_steps(emu, macro: Macro, species_addr: int) -> int | None:
    """Run YAML macro steps. For all steps except the last, run normally.
    For the last step, run the button press then poll instead of waiting `after`."""
    frame = 0
    steps = macro.steps
    for i, step in enumerate(steps):
        is_last = i == len(steps) - 1
        if step.button is not None:
            emu.button(step.button, step.hold)
            emu.tick(step.hold)
            frame += step.hold
        if is_last:
            return None
        if step.after:
            emu.tick(step.after)
            frame += step.after
    return None


def _run_event_macro(emu, macro: EventMacro, species_addr: int) -> int | None:
    """Run EventMacro events. After the last event, return None to trigger polling."""
    cur = 0
    for ev in macro.events:
        if ev.frame > cur:
            emu.tick(ev.frame - cur)
            cur = ev.frame
        if ev.kind == "press":
            emu.button_press(ev.button)
        else:
            emu.button_release(ev.button)
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_polling.py::test_polls_until_species_appears -v`
Expected: PASS

- [ ] **Step 5: Write test for EventMacro path**

Add to `tests/test_polling.py`:

```python
def test_polls_with_event_macro():
    m = EventMacro(
        name="t",
        events=(
            Event(frame=10, kind="press", button="a"),
            Event(frame=12, kind="release", button="a"),
        ),
        total_frames=500,
    )
    emu = _FakeEmulator(species_at_frame=80, species=0xB0, dv_bytes=(0x2A, 0xAA))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0xB0
    assert frames == 80
```

- [ ] **Step 6: Run test to verify it passes**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_polling.py -v`
Expected: 2 passed

- [ ] **Step 7: Write test for hard cap (broken macro)**

Add to `tests/test_polling.py`:

```python
def test_hard_cap_returns_zero_species():
    m = Macro(name="t", steps=(Step(button="a", hold=2, after=8),))
    emu = _FakeEmulator(species_at_frame=99999)
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR, hard_cap=100,
    )
    assert species == 0
    assert frames <= 100 + 10  # button frames + hard_cap
```

- [ ] **Step 8: Run all polling tests**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_polling.py -v`
Expected: 3 passed

- [ ] **Step 9: Commit**

```bash
git add src/shiny_hunter/polling.py tests/test_polling.py
git commit -m "Add early-exit species polling (run_until_species)"
```

---

### Task 2: Wire Early-Exit Polling into Hunt Loop

**Files:**
- Modify: `src/shiny_hunter/hunter.py`

Replace `macro.run()` + `tick(settle)` + manual DV read with `run_until_species()`.

- [ ] **Step 1: Update `hunt()` to use `run_until_species`**

In `src/shiny_hunter/hunter.py`, change the imports and the hunt loop:

```python
# Add import at top
from .polling import run_until_species

# In hunt(), replace lines 67-71:
#     hunt_macro.run(emu)
#     emu.tick(cfg.post_macro_settle_frames)
#     species = emu.read_byte(cfg.party_species_addr)
#     dvs = _read_dvs(emu, cfg.party_dv_addr)
# With:
            species, dvs, _ = run_until_species(
                emu, hunt_macro,
                species_addr=cfg.party_species_addr,
                dv_addr=cfg.party_dv_addr,
            )
```

- [ ] **Step 2: Update `replay_attempt()` the same way**

In `replay_attempt()`, replace lines 164-167:

```python
#     hunt_macro.run(emu)
#     emu.tick(cfg.post_macro_settle_frames)
#     species = emu.read_byte(cfg.party_species_addr)
#     dvs = _read_dvs(emu, cfg.party_dv_addr)
# With:
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=cfg.party_species_addr,
            dv_addr=cfg.party_dv_addr,
        )
```

- [ ] **Step 3: Remove unused `_read_dvs` helper and `save_macro` loading from `hunt()`**

Remove:
- `from . import macro, pokemon, trace` → keep `pokemon, trace`, remove `macro` only if no longer used (it's still needed for `macro.load`)
- `save_macro = macro.load(_macro_path(cfg.save_macro))` line from `hunt()`
- `_read_dvs` function (no longer called)
- `save_macro` parameter from `_persist_shiny` call and function signature

- [ ] **Step 4: Update `_verify_windowed` in `cli.py`**

In `src/shiny_hunter/cli.py`, replace the macro run + settle + manual read block in `_verify_windowed`:

```python
def _verify_windowed(cfg: GameConfig, rom: Path, state_path: Path, macro_path: Path):
    from .polling import run_until_species

    state_bytes = state_path.read_bytes()
    hunt_macro = macro.load(macro_path)

    with Emulator(rom, headless=False, realtime=True) as emu:
        emu.load_state(state_bytes)
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=cfg.party_species_addr,
            dv_addr=cfg.party_dv_addr,
        )

        click.echo("Macro complete — inspect the game state. Close the PyBoy window to continue.")
        while emu.tick(1, render=True):
            pass

    return species, dvs
```

- [ ] **Step 5: Run full test suite**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/ -v`
Expected: all pass (55 existing + 3 new polling tests)

- [ ] **Step 6: Commit**

```bash
git add src/shiny_hunter/hunter.py src/shiny_hunter/cli.py
git commit -m "Wire early-exit polling into hunt loop and verify"
```

---

### Task 3: Save State on Shiny (Replace SRAM Dump)

**Files:**
- Modify: `src/shiny_hunter/hunter.py` — `_persist_shiny()`
- Modify: `tests/test_trace.py`

- [ ] **Step 1: Rewrite `_persist_shiny` to save emulator state instead of SRAM**

Replace the current `_persist_shiny` in `src/shiny_hunter/hunter.py`:

```python
def _persist_shiny(
    *,
    emu: Emulator,
    cfg: GameConfig,
    rom_path: Path,
    state_bytes: bytes,
    state_path: str,
    out_dir: Path,
    master_seed: int,
    attempt: int,
    delay: int,
    species: int,
    dvs: DVs,
) -> None:
    """On shiny: save emulator state + write trace."""
    name = pokemon.species_name(species)
    state_name = f"{name}_{cfg.region}_{attempt:06d}.state"
    trace_name = f"{name}_{cfg.region}_{attempt:06d}.trace.json"

    emu.save_state(out_dir / state_name)

    trace.write(
        out_dir / trace_name,
        rom_path=rom_path,
        state_bytes=state_bytes,
        game=cfg.game,
        region=cfg.region,
        state_path=state_path,
        master_seed=master_seed,
        attempt=attempt,
        delay=delay,
        species=species,
        species_name=name,
        dvs=dvs,
    )
```

- [ ] **Step 2: Update `hunt()` — remove `save_macro` references**

Remove `save_macro = macro.load(...)` line and remove `save_macro` from the `_persist_shiny(...)` call.

- [ ] **Step 3: Run tests**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/shiny_hunter/hunter.py
git commit -m "Save emulator state on shiny instead of running save macro + SRAM dump"
```

---

### Task 4: `resume` Command

**Files:**
- Modify: `src/shiny_hunter/cli.py`
- Modify: `tests/test_cli_help.py`

- [ ] **Step 1: Add `resume` command to CLI**

Add to `src/shiny_hunter/cli.py`, before the `record` command:

```python
@main.command()
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the Game Boy ROM (.gb).",
)
@click.option(
    "--state",
    "state_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Save-state to load (.state).",
)
def resume(rom: Path, state_path: Path) -> None:
    """Load a save-state and play in a windowed emulator."""
    click.echo(f"Resuming from {state_path}")
    emu = Emulator(rom, headless=False)
    try:
        emu.load_state(state_path.read_bytes())
        while emu.tick(1, render=True):
            pass
    finally:
        emu.stop(save=False)
```

- [ ] **Step 2: Update CLI help test**

In `tests/test_cli_help.py`, add to `EXPECTED_OPTIONS`:

```python
    "resume": {"--rom", "--state"},
```

- [ ] **Step 3: Run tests**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_cli_help.py -v`
Expected: all pass (resume now included)

- [ ] **Step 4: Commit**

```bash
git add src/shiny_hunter/cli.py tests/test_cli_help.py
git commit -m "Add resume command to load a shiny state in windowed mode"
```

---

### Task 5: Parallel Workers

**Files:**
- Create: `src/shiny_hunter/workers.py`
- Create: `tests/test_workers.py`
- Modify: `src/shiny_hunter/hunter.py`

This is the biggest task. A new module handles spawning worker processes, each running an independent hunt loop with its own PyBoy instance.

- [ ] **Step 1: Write the failing test for `hunt_parallel`**

```python
# tests/test_workers.py
"""Tests for parallel hunt workers.

These tests use mock patching to avoid needing a real ROM/PyBoy.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

from shiny_hunter.workers import WorkerResult


def test_worker_result_dataclass():
    r = WorkerResult(
        worker_id=0,
        attempt=42,
        master_seed=123,
        delay=100,
        species=0x99,
        dvs_raw=(0xAA, 0xAA),
        state_bytes=b"\x00" * 10,
    )
    assert r.worker_id == 0
    assert r.species == 0x99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_workers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shiny_hunter.workers'`

- [ ] **Step 3: Implement `workers.py`**

```python
# src/shiny_hunter/workers.py
"""Parallel hunt workers using multiprocessing."""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass
from multiprocessing import Process, Queue, Event as MPEvent
from pathlib import Path
from typing import Callable

from . import config as cfg_mod, macro
from .dv import DVs, decode_dvs, is_shiny
from .emulator import Emulator
from .polling import run_until_species

JITTER_RANGE = 256


@dataclass
class WorkerResult:
    worker_id: int
    attempt: int
    master_seed: int
    delay: int
    species: int
    dvs_raw: tuple[int, int]
    state_bytes: bytes


@dataclass
class WorkerProgress:
    worker_id: int
    attempts: int
    latest_species: int
    latest_dvs: tuple[int, int, int, int]


@dataclass
class ParallelHuntResult:
    total_attempts: int
    shinies: list[WorkerResult]
    elapsed_s: float


def _worker_loop(
    worker_id: int,
    rom_path: str,
    state_bytes: bytes,
    macro_path: str,
    species_addr: int,
    dv_addr: int,
    master_seed: int,
    max_attempts: int,
    result_queue: Queue,
    progress_queue: Queue,
    stop_event: MPEvent,
    progress_interval: int = 50,
) -> None:
    rng = random.Random(master_seed)
    hunt_macro = macro.load(Path(macro_path))

    with Emulator(Path(rom_path), headless=True) as emu:
        for n in range(1, max_attempts + 1):
            if stop_event.is_set():
                break

            delay = rng.randint(0, JITTER_RANGE)
            emu.load_state(state_bytes)
            if delay:
                emu.tick(delay)

            species, dvs, _ = run_until_species(
                emu, hunt_macro,
                species_addr=species_addr,
                dv_addr=dv_addr,
            )

            if n % progress_interval == 0:
                progress_queue.put(WorkerProgress(
                    worker_id=worker_id,
                    attempts=n,
                    latest_species=species,
                    latest_dvs=(dvs.atk, dvs.def_, dvs.spd, dvs.spc),
                ))

            if is_shiny(dvs):
                import io
                buf = io.BytesIO()
                emu._pyboy.save_state(buf)
                emu_state = buf.getvalue()

                result_queue.put(WorkerResult(
                    worker_id=worker_id,
                    attempt=n,
                    master_seed=master_seed,
                    delay=delay,
                    species=species,
                    dvs_raw=(dvs.atk << 4 | dvs.def_, dvs.spd << 4 | dvs.spc),
                    state_bytes=emu_state,
                ))
                stop_event.set()
                break

    progress_queue.put(WorkerProgress(
        worker_id=worker_id,
        attempts=n if 'n' in dir() else 0,
        latest_species=0,
        latest_dvs=(0, 0, 0, 0),
    ))


def hunt_parallel(
    *,
    rom_path: Path,
    state_bytes: bytes,
    macro_path: Path,
    species_addr: int,
    dv_addr: int,
    master_seed: int,
    max_attempts: int,
    num_workers: int | None = None,
    on_progress: Callable[[int, int, int, tuple[int, int, int, int]], None] | None = None,
) -> ParallelHuntResult:
    if num_workers is None:
        num_workers = max(1, (os.cpu_count() or 2) - 1)

    attempts_per_worker = max_attempts // num_workers

    result_queue: Queue = Queue()
    progress_queue: Queue = Queue()
    stop_event = MPEvent()

    workers: list[Process] = []
    for i in range(num_workers):
        p = Process(
            target=_worker_loop,
            args=(
                i,
                str(rom_path),
                state_bytes,
                str(macro_path),
                species_addr,
                dv_addr,
                master_seed + i,
                attempts_per_worker,
                result_queue,
                progress_queue,
                stop_event,
            ),
            daemon=True,
        )
        workers.append(p)

    t0 = time.monotonic()
    for p in workers:
        p.start()

    shinies: list[WorkerResult] = []
    total_attempts = 0
    worker_attempts = [0] * num_workers

    try:
        while any(p.is_alive() for p in workers):
            while not progress_queue.empty():
                prog = progress_queue.get_nowait()
                worker_attempts[prog.worker_id] = prog.attempts
                total_attempts = sum(worker_attempts)
                if on_progress:
                    on_progress(
                        total_attempts,
                        prog.latest_species,
                        len(shinies),
                        prog.latest_dvs,
                    )

            while not result_queue.empty():
                res = result_queue.get_nowait()
                shinies.append(res)

            time.sleep(0.05)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        for p in workers:
            p.join(timeout=5)

    while not result_queue.empty():
        shinies.append(result_queue.get_nowait())

    total_attempts = sum(worker_attempts)
    return ParallelHuntResult(
        total_attempts=total_attempts,
        shinies=shinies,
        elapsed_s=time.monotonic() - t0,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/test_workers.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/workers.py tests/test_workers.py
git commit -m "Add parallel hunt workers module"
```

---

### Task 6: Wire Parallel Workers into CLI `run` Command

**Files:**
- Modify: `src/shiny_hunter/cli.py`
- Modify: `tests/test_cli_help.py`

- [ ] **Step 1: Add `--workers` option to `run` command**

In `src/shiny_hunter/cli.py`, add the option decorator to `run`:

```python
@click.option(
    "--workers",
    "num_workers",
    type=int,
    default=None,
    help="Number of parallel workers (default: cpu_count - 1). Use 1 for single-threaded.",
)
```

Add `num_workers: int | None` to the `run()` function signature.

- [ ] **Step 2: Branch on `num_workers` in the `run` handler**

Replace the body of `run()` after `master_seed` computation:

```python
    if num_workers == 1:
        # Single-threaded path (existing behavior)
        with live_progress() as (progress, updater):
            def on_attempt(n: int, species: int, dvs, shiny: bool) -> None:
                progress.attempts = n
                progress.last_dvs = (dvs.atk, dvs.def_, dvs.spd, dvs.spc)
                progress.last_species = species
                if shiny:
                    progress.shinies += 1
                updater.push()

            result = hunter.hunt(
                cfg=cfg,
                rom_path=rom,
                state_bytes=state_bytes,
                state_path=str(state_path),
                macro_path=macro_path,
                out_dir=out_dir,
                master_seed=master_seed,
                max_attempts=max_attempts,
                headless=headless,
                on_attempt=on_attempt,
                stop_on_first_shiny=not continue_after_shiny,
            )

        click.echo(
            f"done: {result.attempts:,} attempts, {result.shinies_found} shiny in "
            f"{result.elapsed_s:0.1f}s ({result.attempts / max(result.elapsed_s, 1e-6):0.1f}/s)"
        )
    else:
        # Parallel path
        from .workers import hunt_parallel

        with live_progress() as (progress, updater):
            def on_progress(total: int, species: int, shiny_count: int, dvs: tuple) -> None:
                progress.attempts = total
                progress.last_species = species
                progress.last_dvs = dvs
                progress.shinies = shiny_count
                updater.push()

            result = hunt_parallel(
                rom_path=rom,
                state_bytes=state_bytes,
                macro_path=macro_path,
                species_addr=cfg.party_species_addr,
                dv_addr=cfg.party_dv_addr,
                master_seed=master_seed,
                max_attempts=max_attempts,
                num_workers=num_workers,
                on_progress=on_progress,
            )

        click.echo(
            f"done: {result.total_attempts:,} attempts, {len(result.shinies)} shiny in "
            f"{result.elapsed_s:0.1f}s ({result.total_attempts / max(result.elapsed_s, 1e-6):0.1f}/s)"
        )

        if result.shinies:
            out_dir.mkdir(parents=True, exist_ok=True)
            for res in result.shinies:
                from . import pokemon
                name = pokemon.species_name(res.species)
                state_name = f"{name}_{cfg.region}_{res.attempt:06d}.state"
                trace_name = f"{name}_{cfg.region}_{res.attempt:06d}.trace.json"
                (out_dir / state_name).write_bytes(res.state_bytes)
                dvs = decode_dvs(res.dvs_raw[0], res.dvs_raw[1])
                trace.write(
                    out_dir / trace_name,
                    rom_path=rom,
                    state_bytes=state_bytes,
                    game=cfg.game,
                    region=cfg.region,
                    state_path=str(state_path),
                    master_seed=res.master_seed,
                    attempt=res.attempt,
                    delay=res.delay,
                    species=res.species,
                    species_name=name,
                    dvs=dvs,
                )
                click.echo(f"shiny! {name} (worker {res.worker_id}, attempt {res.attempt})")
                click.echo(f"  state: {out_dir / state_name}")
                click.echo(f"  trace: {out_dir / trace_name}")
```

- [ ] **Step 3: Update CLI help test**

In `tests/test_cli_help.py`, add `"--workers"` to the `run` entry:

```python
    "run": {
        "--rom", "--state", "--macro", "--game", "--region",
        "--max-attempts", "--seed", "--out",
        "--headless/--window", "--continue-after-shiny", "--workers",
    },
```

- [ ] **Step 4: Run tests**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/cli.py tests/test_cli_help.py
git commit -m "Wire parallel workers into run command with --workers flag"
```

---

### Task 7: Update Emulator to Expose `save_state_bytes`

**Files:**
- Modify: `src/shiny_hunter/emulator.py`

The parallel worker needs to save emulator state as bytes without writing to disk. Currently `save_state` always writes to a path/file. Add a convenience method.

- [ ] **Step 1: Add `save_state_bytes` method**

In `src/shiny_hunter/emulator.py`, add after `save_state`:

```python
    def save_state_bytes(self) -> bytes:
        """Save state and return the raw bytes without writing to disk."""
        buf = io.BytesIO()
        self._pyboy.save_state(buf)
        return buf.getvalue()
```

- [ ] **Step 2: Use it in `workers.py`**

In `workers.py`, replace the direct `emu._pyboy.save_state(buf)` with:

```python
                emu_state = emu.save_state_bytes()
```

- [ ] **Step 3: Run tests**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add src/shiny_hunter/emulator.py src/shiny_hunter/workers.py
git commit -m "Add save_state_bytes to Emulator, use in workers"
```

---

### Task 8: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update README**

Add `--workers` to the run flags table. Add the `resume` command to the onboarding flow. Update the "hunt" section to mention parallel workers and the `.state` output.

Update the run command example:

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --headless
# Runs on all available cores by default.
# When a shiny is found, writes:
#   shinies/eevee_us_<NNNNNN>.state       — resume with `shiny-hunt resume`
#   shinies/eevee_us_<NNNNNN>.trace.json  — for `shiny-hunt replay`
```

Add resume section:

```bash
# Resume a found shiny interactively
shiny-hunt resume --rom roms/red.gb --state shinies/eevee_us_004200.state
# Opens PyBoy windowed. Save in-game, check stats, keep playing.
```

Add `--workers N` to the flags table:

```
| `--workers N` | Parallel worker count (default: cpu_count - 1; use 1 for single-threaded) |
```

- [ ] **Step 2: Update CLAUDE.md commands section**

Add `resume` to the command list:

```
shiny-hunt resume --rom ROM --state STATE          # Load a state and play interactively
```

- [ ] **Step 3: Update project layout in README**

Add `polling.py` and `workers.py`:

```
  polling.py          early-exit species polling (run_until_species)
  workers.py          parallel hunt workers (multiprocessing)
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Update docs for parallel workers, resume command, and early-exit polling"
```

---

### Task 9: Run Full Test Suite and Manual Smoke Test

- [ ] **Step 1: Run full test suite**

Run: `src/shiny_hunter/.venv/bin/python -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 2: Manual smoke test (single-threaded)**

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_bulbasaur.state \
  --macro macros/red_us_bulbasaur.events.json \
  --workers 1 --max-attempts 100
```

Verify: rate is higher than baseline 10.8/s (expected ~30/s with early-exit polling).

- [ ] **Step 3: Manual smoke test (parallel)**

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_bulbasaur.state \
  --macro macros/red_us_bulbasaur.events.json \
  --max-attempts 1000
```

Verify: rate scales with core count (expected ~300+/s on 12 cores).

- [ ] **Step 4: Manual smoke test (resume)**

```bash
# If a shiny was found:
shiny-hunt resume --rom roms/red.gb --state shinies/<found_state>.state
# Verify: PyBoy window opens with the game at the shiny's state.
```

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "Fix any issues found during smoke testing"
```
