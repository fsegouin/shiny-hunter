# Monitor Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--monitor` flag to `shiny-hunt run` that opens a pygame grid window showing live worker emulator screens with DV/shiny overlay.

**Architecture:** Workers stay headless and send screen snapshots + DV data through a `frame_queue` after each macro run. The main process composites all worker screens into a single pygame window with text overlays. Shiny frames are sticky — non-shiny frames never overwrite a shiny frame, but a subsequent shiny does.

**Tech Stack:** pygame (new optional dep), numpy (already available via pyboy), existing multiprocessing Queue infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-29-monitor-mode-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/shiny_hunter/workers.py` | Modify | Add `WorkerFrame` dataclass, `frame_queue` parameter, screen capture after macro run |
| `src/shiny_hunter/monitor.py` | Create | Pygame grid display: layout computation, surface blitting, text overlay, event loop |
| `src/shiny_hunter/cli.py` | Modify | Add `--monitor` flag, wire up `frame_queue` and monitor event loop |
| `pyproject.toml` | Modify | Add `monitor` optional dependency group with pygame |
| `tests/test_workers.py` | Modify | Add `WorkerFrame` dataclass test |
| `tests/test_monitor.py` | Create | Tests for grid layout computation and frame dict update logic |

---

### Task 1: Add WorkerFrame dataclass to workers.py

**Files:**
- Modify: `src/shiny_hunter/workers.py:1-30`
- Test: `tests/test_workers.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_workers.py`, add:

```python
import numpy as np

from shiny_hunter.workers import WorkerFrame


def test_worker_frame_dataclass():
    screen = np.zeros((144, 160, 3), dtype=np.uint8)
    screen[0, 0] = [255, 0, 0]
    f = WorkerFrame(
        worker_id=0,
        screen=screen,
        species=0xB1,
        dvs=(10, 10, 10, 10),
        is_shiny=True,
    )
    assert f.worker_id == 0
    assert f.screen.shape == (144, 160, 3)
    assert f.species == 0xB1
    assert f.dvs == (10, 10, 10, 10)
    assert f.is_shiny is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_workers.py::test_worker_frame_dataclass -v`
Expected: FAIL with `ImportError: cannot import name 'WorkerFrame'`

- [ ] **Step 3: Add WorkerFrame to workers.py**

In `src/shiny_hunter/workers.py`, add the import at the top (after existing imports):

```python
import numpy as np
```

Then add the dataclass after `WorkerProgress` (around line 35):

```python
@dataclass
class WorkerFrame:
    worker_id: int
    screen: np.ndarray
    species: int
    dvs: tuple[int, int, int, int]
    is_shiny: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_workers.py::test_worker_frame_dataclass -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/workers.py tests/test_workers.py
git commit -m "Add WorkerFrame dataclass to workers"
```

---

### Task 2: Add frame capture to _worker_loop

**Files:**
- Modify: `src/shiny_hunter/workers.py:46-122`

- [ ] **Step 1: Add frame_queue parameter to _worker_loop**

In `src/shiny_hunter/workers.py`, update `_worker_loop` signature to add `frame_queue` after `stop_event`:

```python
def _worker_loop(
    worker_id: int,
    rom_path: str,
    state_bytes: bytes,
    macro_path: str,
    species_addr: int,
    dv_addr: int,
    master_seed: int,
    start_delay: int,
    end_delay: int,
    result_queue: Queue,
    progress_queue: Queue,
    stop_event: MPEvent,
    stop_after_first: bool,
    frame_queue: Queue | None = None,
) -> None:
```

- [ ] **Step 2: Add screen capture after run_until_species**

After the `run_until_species()` call and the `latest_species`/`latest_dvs` assignments (around line 86), add screen capture logic:

```python
            if frame_queue is not None:
                shiny = is_shiny(dvs)
                try:
                    screen = emu._pyboy.screen.ndarray[:, :, :3].copy()
                    frame_queue.put_nowait(WorkerFrame(
                        worker_id=worker_id,
                        screen=screen,
                        species=species,
                        dvs=latest_dvs,
                        is_shiny=shiny,
                    ))
                except Exception:
                    pass
```

Note: the `is_shiny` call here reuses the import already at the top of the file. The `put_nowait` with bare except avoids blocking the worker if the queue is full.

- [ ] **Step 3: Add frame_queue parameter to hunt_parallel**

Update `hunt_parallel` signature to accept `frame_queue`:

```python
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
    on_worker_progress: Callable[[int, int], None] | None = None,
    on_shiny: Callable[[WorkerResult], None] | None = None,
    delay_window: int = DEFAULT_DELAY_WINDOW,
    start_delay: int | None = None,
    stop_after_first: bool = True,
    frame_queue: Queue | None = None,
) -> ParallelHuntResult:
```

Pass `frame_queue` through to each worker process in the `args` tuple. Update the `Process` `args` to include `frame_queue` after `stop_after_first`:

```python
        p = Process(
            target=_worker_loop,
            args=(
                i,
                str(rom_path),
                state_bytes,
                str(macro_path),
                species_addr,
                dv_addr,
                master_seed,
                s,
                e,
                result_queue,
                progress_queue,
                stop_event,
                stop_after_first,
                frame_queue,
            ),
            daemon=True,
        )
```

- [ ] **Step 4: Run existing tests to verify nothing breaks**

Run: `pytest tests/test_workers.py -v`
Expected: all tests PASS (existing tests don't pass `frame_queue`, which defaults to `None`)

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/workers.py
git commit -m "Add frame capture to worker loop via frame_queue"
```

---

### Task 3: Create monitor.py — grid layout and frame dict logic

**Files:**
- Create: `src/shiny_hunter/monitor.py`
- Create: `tests/test_monitor.py`

- [ ] **Step 1: Write tests for grid_size**

Create `tests/test_monitor.py`:

```python
from shiny_hunter.monitor import grid_size


def test_grid_size_1():
    assert grid_size(1) == (1, 1)


def test_grid_size_2():
    assert grid_size(2) == (2, 1)


def test_grid_size_3():
    assert grid_size(3) == (3, 1)


def test_grid_size_4():
    assert grid_size(4) == (2, 2)


def test_grid_size_5():
    assert grid_size(5) == (3, 2)


def test_grid_size_8():
    assert grid_size(8) == (4, 2)


def test_grid_size_9():
    assert grid_size(9) == (3, 3)


def test_grid_size_16():
    assert grid_size(16) == (4, 4)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_monitor.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create monitor.py with grid_size**

Create `src/shiny_hunter/monitor.py`:

```python
"""Pygame-based monitor grid for parallel shiny hunting."""
from __future__ import annotations

import math


def grid_size(n: int) -> tuple[int, int]:
    """Compute (cols, rows) for n workers. Prefer wider-than-tall layouts."""
    if n <= 0:
        return (1, 1)
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return (cols, rows)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_monitor.py -v`
Expected: all PASS

- [ ] **Step 5: Write tests for update_frames**

Add to `tests/test_monitor.py`:

```python
import numpy as np

from shiny_hunter.monitor import update_frames
from shiny_hunter.workers import WorkerFrame


def _make_frame(worker_id: int, is_shiny: bool = False, species: int = 0xB1) -> WorkerFrame:
    return WorkerFrame(
        worker_id=worker_id,
        screen=np.zeros((144, 160, 3), dtype=np.uint8),
        species=species,
        dvs=(10, 10, 10, 10),
        is_shiny=is_shiny,
    )


def test_update_frames_inserts_new():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0))
    assert 0 in frames
    assert frames[0].is_shiny is False


def test_update_frames_overwrites_non_shiny():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0, is_shiny=False, species=0x01))
    update_frames(frames, _make_frame(0, is_shiny=False, species=0x02))
    assert frames[0].species == 0x02


def test_update_frames_shiny_not_overwritten_by_non_shiny():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0, is_shiny=True, species=0x01))
    update_frames(frames, _make_frame(0, is_shiny=False, species=0x02))
    assert frames[0].species == 0x01
    assert frames[0].is_shiny is True


def test_update_frames_shiny_overwritten_by_shiny():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0, is_shiny=True, species=0x01))
    update_frames(frames, _make_frame(0, is_shiny=True, species=0x02))
    assert frames[0].species == 0x02
    assert frames[0].is_shiny is True
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `pytest tests/test_monitor.py::test_update_frames_inserts_new -v`
Expected: FAIL with `ImportError: cannot import name 'update_frames'`

- [ ] **Step 7: Implement update_frames**

Add to `src/shiny_hunter/monitor.py`:

```python
from .workers import WorkerFrame


def update_frames(frames: dict[int, WorkerFrame], new: WorkerFrame) -> None:
    """Update the frame dict. A non-shiny frame never overwrites a shiny one."""
    existing = frames.get(new.worker_id)
    if existing is not None and existing.is_shiny and not new.is_shiny:
        return
    frames[new.worker_id] = new
```

- [ ] **Step 8: Run all monitor tests**

Run: `pytest tests/test_monitor.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add src/shiny_hunter/monitor.py tests/test_monitor.py
git commit -m "Add monitor grid layout and frame update logic"
```

---

### Task 4: Add pygame rendering to monitor.py

**Files:**
- Modify: `src/shiny_hunter/monitor.py`

This task adds the pygame display code. It cannot be unit-tested without a display, so we test it manually via the CLI in Task 6.

- [ ] **Step 1: Add MonitorWindow class**

Add to `src/shiny_hunter/monitor.py`:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from multiprocessing import Queue as QueueType

import numpy as np

from . import pokemon
from .dv import is_shiny as _is_shiny, decode_dvs

GB_W, GB_H = 160, 144
SCALE = 2
CELL_W = GB_W * SCALE
CELL_H = GB_H * SCALE
BAR_H = 28
BORDER = 2
BG_COLOR = (30, 30, 30)
SHINY_BORDER_COLOR = (0, 220, 80)
TEXT_COLOR = (220, 220, 220)
SHINY_TEXT_COLOR = (0, 255, 100)


class MonitorWindow:
    def __init__(self, num_workers: int) -> None:
        import pygame
        self._pg = pygame
        pygame.init()
        pygame.display.set_caption("shiny-hunter monitor")

        self.num_workers = num_workers
        self.cols, self.rows = grid_size(num_workers)
        self.cell_w = CELL_W + BORDER * 2
        self.cell_h = CELL_H + BAR_H + BORDER * 2
        win_w = self.cols * self.cell_w
        win_h = self.rows * self.cell_h
        self._screen = pygame.display.set_mode((win_w, win_h))
        self._font = pygame.font.SysFont("monospace", 13)
        self._clock = pygame.time.Clock()
        self._frames: dict[int, WorkerFrame] = {}

    def update(self, frame: WorkerFrame) -> None:
        update_frames(self._frames, frame)

    def render(self) -> bool:
        """Draw the grid. Returns False if the user closed the window."""
        pg = self._pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                return False

        self._screen.fill(BG_COLOR)

        for worker_id in range(self.num_workers):
            col = worker_id % self.cols
            row = worker_id // self.cols
            x = col * self.cell_w
            y = row * self.cell_h

            wf = self._frames.get(worker_id)
            if wf is not None:
                if wf.is_shiny:
                    pg.draw.rect(self._screen, SHINY_BORDER_COLOR,
                                 (x, y, self.cell_w, self.cell_h), BORDER)

                surf = pg.surfarray.make_surface(
                    np.transpose(wf.screen, (1, 0, 2))
                )
                surf = pg.transform.scale(surf, (CELL_W, CELL_H))
                self._screen.blit(surf, (x + BORDER, y + BORDER))

                label = self._label(wf)
                color = SHINY_TEXT_COLOR if wf.is_shiny else TEXT_COLOR
                text_surf = self._font.render(label, True, color)
                self._screen.blit(text_surf, (x + BORDER + 4, y + BORDER + CELL_H + 4))
            else:
                label = f"Worker {worker_id} | waiting..."
                text_surf = self._font.render(label, True, TEXT_COLOR)
                self._screen.blit(text_surf, (x + BORDER + 4, y + BORDER + CELL_H + 4))

        pg.display.flip()
        self._clock.tick(15)
        return True

    def close(self) -> None:
        self._pg.quit()

    @staticmethod
    def _label(wf: WorkerFrame) -> str:
        name = pokemon.species_name(wf.species)
        a, d, s, c = wf.dvs
        shiny = "YES" if wf.is_shiny else "no"
        return f"W{wf.worker_id} | {name} | A={a} D={d} S={s} C={c} | Shiny: {shiny}"
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `pytest tests/test_monitor.py -v`
Expected: all PASS (new code only imports pygame inside __init__)

- [ ] **Step 3: Commit**

```bash
git add src/shiny_hunter/monitor.py
git commit -m "Add MonitorWindow pygame grid renderer"
```

---

### Task 5: Add pygame optional dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add monitor optional dependency group**

In `pyproject.toml`, add after the `dev` group:

```toml
monitor = [
    "pygame>=2.5",
]
```

- [ ] **Step 2: Install the optional dependency**

Run: `pip install -e ".[monitor]"`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "Add pygame as optional monitor dependency"
```

---

### Task 6: Wire up --monitor flag in cli.py

**Files:**
- Modify: `src/shiny_hunter/cli.py:218-484`

- [ ] **Step 1: Add --monitor flag to run command**

Add the `--monitor` option to the `run` command, after the `--headless/--window` option (around line 263):

```python
@click.option(
    "--monitor",
    is_flag=True,
    help="Show a live pygame grid of all worker screens with DV overlay.",
)
```

Add `monitor: bool` to the `run` function signature.

- [ ] **Step 2: Add validation for --monitor**

At the start of the `run` function body (after `cfg = _resolve_config(...)`, around line 334), add:

```python
    if monitor and not headless:
        raise click.ClickException("--monitor cannot be combined with --window")
```

- [ ] **Step 3: Add the monitor branch in the run function**

After the existing `if num_workers == 1:` / `else:` block, restructure to add a monitor path. The monitor path replaces the `else:` (parallel) branch when `--monitor` is set. Insert this before the existing `if num_workers == 1:` block:

```python
    if monitor:
        from multiprocessing import Queue as MPQueue
        from .monitor import MonitorWindow
        from .workers import hunt_parallel, WorkerFrame
        from .dv import decode_dvs
        from queue import Empty

        frame_queue: MPQueue = MPQueue()

        actual_workers = num_workers if num_workers is not None else max(1, (os.cpu_count() or 2) - 1)
        if actual_workers < 1:
            actual_workers = 1

        out_dir.mkdir(parents=True, exist_ok=True)

        monitor_win = MonitorWindow(actual_workers)

        # We run hunt_parallel in a background thread so we can run
        # the pygame event loop in the main thread (required by SDL2).
        import threading

        hunt_result_holder: list[object] = []

        def _run_hunt() -> None:
            def on_shiny(res) -> None:
                name = pokemon.species_name(res.species)
                dvs = decode_dvs(res.dvs_raw[0], res.dvs_raw[1])
                state_name = f"{name}_{cfg.region}_{res.delay:06d}.state"
                trace_name = f"{name}_{cfg.region}_{res.delay:06d}.trace.json"
                (out_dir / state_name).write_bytes(res.state_bytes)
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
                click.echo(
                    f"shiny! {name} — delay={res.delay:,} "
                    f"ATK={dvs.atk} DEF={dvs.def_} SPD={dvs.spd} SPC={dvs.spc} HP={dvs.hp}"
                )
                if preview_cb is not None:
                    preview_cb(out_dir / state_name)

            result = hunt_parallel(
                rom_path=rom,
                state_bytes=state_bytes,
                macro_path=macro_path,
                species_addr=species_addr,
                dv_addr=dv_addr,
                master_seed=master_seed,
                max_attempts=max_attempts,
                num_workers=num_workers,
                on_shiny=on_shiny,
                delay_window=delay_window,
                start_delay=start_delay,
                stop_after_first=not continue_after_shiny,
                frame_queue=frame_queue,
            )
            hunt_result_holder.append(result)

        hunt_thread = threading.Thread(target=_run_hunt, daemon=True)
        hunt_thread.start()

        try:
            while hunt_thread.is_alive():
                while True:
                    try:
                        wf = frame_queue.get_nowait()
                    except Empty:
                        break
                    monitor_win.update(wf)
                if not monitor_win.render():
                    break
        except KeyboardInterrupt:
            pass
        finally:
            monitor_win.close()

        hunt_thread.join(timeout=10)

        if hunt_result_holder:
            result = hunt_result_holder[0]
            click.echo(
                f"done: {result.total_attempts:,} attempts, {len(result.shinies)} shiny in "
                f"{result.elapsed_s:0.1f}s ({result.total_attempts / max(result.elapsed_s, 1e-6):0.1f}/s)"
            )
        return
```

- [ ] **Step 4: Verify existing CLI tests still pass**

Run: `pytest tests/test_cli_help.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/cli.py
git commit -m "Add --monitor flag to run command"
```

---

### Task 7: Manual integration test

**Files:** none (manual test)

- [ ] **Step 1: Test with --monitor flag**

Run a real hunt with monitor mode to verify end-to-end:

```bash
shiny-hunt run \
  --rom roms/pokered.gb \
  --state states/red_us_charmander.state \
  --macro macros/red_us_charmander.events.json \
  --workers 4 \
  --max-attempts 100 \
  --monitor
```

Verify:
- A pygame window opens showing a 2x2 grid
- Each cell shows the Game Boy screen updating as workers progress
- Text bars show worker ID, species, DVs, and shiny status
- Closing the pygame window stops all workers
- If a shiny is found, its cell gets a green border and freezes

- [ ] **Step 2: Test without --monitor flag (regression)**

```bash
shiny-hunt run \
  --rom roms/pokered.gb \
  --state states/red_us_charmander.state \
  --macro macros/red_us_charmander.events.json \
  --workers 4 \
  --max-attempts 100
```

Verify: existing behavior unchanged, Rich progress display works as before.

- [ ] **Step 3: Test --monitor with --window conflict**

```bash
shiny-hunt run \
  --rom roms/pokered.gb \
  --state states/red_us_charmander.state \
  --macro macros/red_us_charmander.events.json \
  --window \
  --monitor
```

Verify: error message about incompatible flags.

- [ ] **Step 4: Run full test suite**

Run: `pytest -v`
Expected: all PASS
