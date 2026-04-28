"""Diagnostic scans for state/macro delay coverage."""
from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from multiprocessing import Event as MPEvent, Process, Queue
from pathlib import Path
from queue import Empty
from typing import Callable

from .delays import DEFAULT_DELAY_WINDOW
from .dv import DVs, is_shiny
from .emulator import Emulator
from .macro import EventMacro, Macro
from .polling import run_until_species


@dataclass(frozen=True)
class ShinyDelay:
    delay: int
    species: int
    dvs: DVs


@dataclass(frozen=True)
class CoverageResult:
    scanned: int
    delay_window: int
    unique_dv_pairs: int
    shiny_delays: tuple[ShinyDelay, ...]
    unknown_species: int

    @property
    def exhausted(self) -> bool:
        return self.scanned >= self.delay_window


@dataclass(frozen=True)
class _CoverageChunk:
    scanned: int
    raw_pairs: frozenset[tuple[int, int]]
    shiny_delays: tuple[ShinyDelay, ...]
    unknown_species: int


@dataclass
class _WorkerProgress:
    worker_id: int
    scanned: int


def _scan_chunk(
    *,
    rom_path: str,
    state_bytes: bytes,
    macro_path: str,
    species_addr: int,
    dv_addr: int,
    start_delay: int,
    end_delay: int,
    stop_after_first: bool,
    stop_event: MPEvent | None = None,
    progress_queue: Queue | None = None,
    worker_id: int = 0,
) -> _CoverageChunk:
    from . import macro as macro_mod

    hunt_macro = macro_mod.load(Path(macro_path))

    raw_pairs: set[tuple[int, int]] = set()
    shiny_delays: list[ShinyDelay] = []
    unknown_species = 0
    scanned = 0
    last_report = time.monotonic()

    with Emulator(Path(rom_path), headless=True) as emu:
        emu.load_state(state_bytes)
        if start_delay:
            emu.tick(start_delay)

        for delay in range(start_delay, end_delay):
            if stop_event is not None and stop_event.is_set():
                break

            pre_macro_state = emu.save_state_bytes()
            species, dvs, _ = run_until_species(
                emu,
                hunt_macro,
                species_addr=species_addr,
                dv_addr=dv_addr,
            )

            raw_pairs.add(((dvs.atk << 4) | dvs.def_, (dvs.spd << 4) | dvs.spc))
            if species == 0:
                unknown_species += 1
            scanned += 1

            now = time.monotonic()
            if progress_queue is not None and now - last_report >= 1.0:
                progress_queue.put(_WorkerProgress(worker_id=worker_id, scanned=scanned))
                last_report = now

            if is_shiny(dvs):
                shiny_delays.append(ShinyDelay(delay=delay, species=species, dvs=dvs))
                if stop_after_first:
                    break

            if delay + 1 < end_delay:
                emu.load_state(pre_macro_state)
                emu.tick(1)

    if progress_queue is not None:
        progress_queue.put(_WorkerProgress(worker_id=worker_id, scanned=scanned))

    return _CoverageChunk(
        scanned=scanned,
        raw_pairs=frozenset(raw_pairs),
        shiny_delays=tuple(shiny_delays),
        unknown_species=unknown_species,
    )


def _coverage_worker(
    worker_id: int,
    rom_path: str,
    state_bytes: bytes,
    macro_path: str,
    species_addr: int,
    dv_addr: int,
    start_delay: int,
    end_delay: int,
    stop_after_first: bool,
    stop_event: MPEvent,
    result_queue: Queue,
    progress_queue: Queue,
) -> None:
    warnings.filterwarnings("ignore")
    result = _scan_chunk(
        rom_path=rom_path,
        state_bytes=state_bytes,
        macro_path=macro_path,
        species_addr=species_addr,
        dv_addr=dv_addr,
        start_delay=start_delay,
        end_delay=end_delay,
        stop_after_first=stop_after_first,
        stop_event=stop_event,
        progress_queue=progress_queue,
        worker_id=worker_id,
    )
    result_queue.put(result)


def scan_delay_window(
    emu,
    hunt_macro: Macro | EventMacro,
    *,
    species_addr: int,
    dv_addr: int,
    delay_window: int = DEFAULT_DELAY_WINDOW,
    stop_after_first: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
) -> CoverageResult:
    """Scan sequential frame delays and report whether any shiny delay exists."""
    if delay_window < 1:
        raise ValueError("delay_window must be >= 1")

    raw_pairs: set[tuple[int, int]] = set()
    shiny_delays: list[ShinyDelay] = []
    unknown_species = 0
    last_report = time.monotonic()

    for delay in range(delay_window):
        pre_macro_state = emu.save_state_bytes()
        species, dvs, _ = run_until_species(
            emu,
            hunt_macro,
            species_addr=species_addr,
            dv_addr=dv_addr,
        )

        raw_pairs.add(((dvs.atk << 4) | dvs.def_, (dvs.spd << 4) | dvs.spc))
        if species == 0:
            unknown_species += 1

        if is_shiny(dvs):
            shiny_delays.append(ShinyDelay(delay=delay, species=species, dvs=dvs))
            if stop_after_first:
                if on_progress is not None:
                    on_progress(delay + 1, len(raw_pairs))
                return CoverageResult(
                    scanned=delay + 1,
                    delay_window=delay_window,
                    unique_dv_pairs=len(raw_pairs),
                    shiny_delays=tuple(shiny_delays),
                    unknown_species=unknown_species,
                )

        emu.load_state(pre_macro_state)
        if delay + 1 < delay_window:
            emu.tick(1)

        now = time.monotonic()
        scanned = delay + 1
        if on_progress is not None and (now - last_report >= 1.0 or scanned == delay_window):
            on_progress(scanned, len(raw_pairs))
            last_report = now

    return CoverageResult(
        scanned=delay_window,
        delay_window=delay_window,
        unique_dv_pairs=len(raw_pairs),
        shiny_delays=tuple(shiny_delays),
        unknown_species=unknown_species,
    )


def scan_delay_window_parallel(
    *,
    rom_path: Path,
    state_bytes: bytes,
    macro_path: Path,
    species_addr: int,
    dv_addr: int,
    delay_window: int = DEFAULT_DELAY_WINDOW,
    num_workers: int | None = None,
    stop_after_first: bool = True,
    on_worker_progress: Callable[[int, int, int], None] | None = None,
) -> CoverageResult:
    """Parallel version of scan_delay_window.

    on_worker_progress(worker_id, scanned, chunk_size) is called ~once per second per worker.
    """
    if delay_window < 1:
        raise ValueError("delay_window must be >= 1")
    if num_workers is None:
        num_workers = max(1, (os.cpu_count() or 2) - 1)
    num_workers = max(1, min(num_workers, delay_window))

    if num_workers == 1:
        from . import macro as macro_mod

        def _single_on_progress(scanned: int, unique_pairs: int) -> None:
            if on_worker_progress is not None:
                on_worker_progress(0, scanned, delay_window)

        with Emulator(rom_path, headless=True) as emu:
            emu.load_state(state_bytes)
            return scan_delay_window(
                emu,
                macro_mod.load(macro_path),
                species_addr=species_addr,
                dv_addr=dv_addr,
                delay_window=delay_window,
                stop_after_first=stop_after_first,
                on_progress=_single_on_progress,
            )

    result_queue: Queue = Queue()
    progress_queue: Queue = Queue()
    stop_event = MPEvent()
    chunk = (delay_window + num_workers - 1) // num_workers
    workers: list[Process] = []
    chunk_sizes: list[int] = []

    for i in range(num_workers):
        start = i * chunk
        end = min(delay_window, start + chunk)
        if start >= end:
            break
        chunk_sizes.append(end - start)
        p = Process(
            target=_coverage_worker,
            args=(
                i,
                str(rom_path),
                state_bytes,
                str(macro_path),
                species_addr,
                dv_addr,
                start,
                end,
                stop_after_first,
                stop_event,
                result_queue,
                progress_queue,
            ),
            daemon=True,
        )
        workers.append(p)

    for p in workers:
        p.start()

    total_pairs: set[tuple[int, int]] = set()
    unknown_species = 0
    shiny_delays: list[ShinyDelay] = []
    completed = 0
    worker_scanned = [0] * len(workers)

    def _drain_progress() -> None:
        while True:
            try:
                prog = progress_queue.get_nowait()
            except Empty:
                break
            worker_scanned[prog.worker_id] = prog.scanned
            if on_worker_progress is not None:
                on_worker_progress(prog.worker_id, prog.scanned, chunk_sizes[prog.worker_id])

    try:
        while completed < len(workers):
            _drain_progress()

            while True:
                try:
                    part = result_queue.get_nowait()
                except Empty:
                    break
                completed += 1
                total_pairs.update(part.raw_pairs)
                unknown_species += part.unknown_species
                shiny_delays.extend(part.shiny_delays)
                if part.shiny_delays and stop_after_first:
                    stop_event.set()

            time.sleep(0.05)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        for p in workers:
            p.join(timeout=5)

    _drain_progress()
    while True:
        try:
            part = result_queue.get_nowait()
        except Empty:
            break
        total_pairs.update(part.raw_pairs)
        unknown_species += part.unknown_species
        shiny_delays.extend(part.shiny_delays)

    return CoverageResult(
        scanned=sum(worker_scanned),
        delay_window=delay_window,
        unique_dv_pairs=len(total_pairs),
        shiny_delays=tuple(shiny_delays),
        unknown_species=unknown_species,
    )
