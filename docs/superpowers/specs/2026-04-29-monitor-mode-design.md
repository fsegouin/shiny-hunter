# Monitor Mode — Design Spec

## Summary

Add a `--monitor` flag to `shiny-hunt run` that opens a pygame window showing a live grid of all worker emulator screens with DV/shiny overlay text. Workers stay headless; they periodically send screen snapshots to the main process. When a worker finds a shiny, its grid tile freezes on that frame and gets a green border.

## New data type: WorkerFrame

```python
@dataclass
class WorkerFrame:
    worker_id: int
    screen: np.ndarray          # (144, 160, 3) RGB, copied from screen.ndarray
    species: int
    dvs: tuple[int, int, int, int]  # atk, def, spd, spc
    is_shiny: bool
```

Workers send a `WorkerFrame` through a new `frame_queue: Queue` after each macro run completes (so the frame shows the battle result / party screen, not mid-emulation). When a shiny is found, the worker sends one final `WorkerFrame` with `is_shiny=True`.

If `--continue-after-shiny` is set, the worker keeps searching after a shiny. Non-shiny frames never overwrite a shiny frame in the main process's frame dict. A subsequent shiny *does* overwrite the previous one.

## Worker changes (workers.py)

`_worker_loop` gains an optional `frame_queue: Queue | None` parameter. When set:

- After each `run_until_species()` call, grab `emu._pyboy.screen.ndarray[:, :, :3].copy()` and send a `WorkerFrame` through `frame_queue`.
- On shiny: send the `WorkerFrame` with `is_shiny=True`, then send the `WorkerResult` through `result_queue` as today.

When `frame_queue` is `None` (normal non-monitor mode), no screen capture happens. Existing behavior is unchanged.

`hunt_parallel` gains a `frame_queue` parameter, forwarded to each worker.

## Monitor display (monitor.py — new file)

### Grid layout

- N workers arranged in an auto-computed grid (e.g. 8 → 4x2, 3 → 3x1, 1 → 1x1).
- Each cell: Game Boy screen scaled 2x (320x288) with a text bar below (~30px).
- Text bar content: `Worker N | Species | ATK=X DEF=X SPD=X SPC=X | Shiny: YES/NO`
- Shiny cells get a green border.
- Window title: `shiny-hunter monitor`

### Refresh

- The pygame event loop runs at ~15-20 FPS in the main process.
- Each tick: drain the frame dict, blit surfaces, draw text bars, handle pygame events.
- Frame data arrives less frequently (only when workers finish a macro run), but the window stays responsive.

### Lifecycle

- Opens when `--monitor` is passed.
- Closes when all workers finish, or when the user closes the pygame window (triggers `stop_event.set()`, same as KeyboardInterrupt today).

## CLI integration (cli.py)

`--monitor` is a new flag on the `run` command. When set:

- Mutually exclusive with `--headless/--window` (monitor implies headless workers + pygame grid).
- Forces the parallel worker path even if `--workers 1`.
- Rich live progress is replaced by the pygame window. Simple `click.echo` still used for shiny announcements and the final summary.

## New dependency

`pygame` added as an optional dependency (e.g. `pip install shiny-hunter[monitor]`).

## Files changed

- **New:** `src/shiny_hunter/monitor.py` — pygame grid display
- **Modified:** `src/shiny_hunter/workers.py` — add `frame_queue` param, `WorkerFrame` dataclass, screen capture in worker loop
- **Modified:** `src/shiny_hunter/cli.py` — add `--monitor` flag, wire up monitor event loop
- **Modified:** `pyproject.toml` — add `pygame` optional dependency
