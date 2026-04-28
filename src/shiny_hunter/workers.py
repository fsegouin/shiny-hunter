"""Parallel hunt workers using multiprocessing."""
from __future__ import annotations

import os
import time
import warnings
from dataclasses import dataclass
from multiprocessing import Process, Queue, Event as MPEvent
from pathlib import Path
from queue import Empty
from typing import Callable

from . import macro
from .delays import DEFAULT_DELAY_WINDOW, attempt_cap, delay_for_attempt
from .dv import is_shiny
from .emulator import Emulator
from .polling import run_until_species


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
    stride: int,
    delay_window: int,
    progress_interval: int = 50,
) -> None:
    warnings.filterwarnings("ignore")
    hunt_macro = macro.load(Path(macro_path))
    n = 0
    latest_species = 0
    latest_dvs = (0, 0, 0, 0)

    with Emulator(Path(rom_path), headless=True) as emu:
        global_attempt = worker_id + 1
        if global_attempt > max_attempts:
            progress_queue.put(WorkerProgress(
                worker_id=worker_id,
                attempts=0,
                latest_species=0,
                latest_dvs=(0, 0, 0, 0),
            ))
            return

        current_delay = delay_for_attempt(master_seed, global_attempt, delay_window)
        emu.load_state(state_bytes)
        if current_delay:
            emu.tick(current_delay)

        while global_attempt <= max_attempts:
            if stop_event.is_set():
                break

            n += 1
            delay = current_delay
            pre_macro_state = emu.save_state_bytes()

            species, dvs, _ = run_until_species(
                emu, hunt_macro,
                species_addr=species_addr,
                dv_addr=dv_addr,
            )
            latest_species = species
            latest_dvs = (dvs.atk, dvs.def_, dvs.spd, dvs.spc)

            if n % progress_interval == 0:
                progress_queue.put(WorkerProgress(
                    worker_id=worker_id,
                    attempts=n,
                    latest_species=latest_species,
                    latest_dvs=latest_dvs,
                ))

            if is_shiny(dvs):
                emu_state = emu.save_state_bytes()

                result_queue.put(WorkerResult(
                    worker_id=worker_id,
                    attempt=global_attempt,
                    master_seed=master_seed,
                    delay=delay,
                    species=species,
                    dvs_raw=(dvs.atk << 4 | dvs.def_, dvs.spd << 4 | dvs.spc),
                    state_bytes=emu_state,
                ))
                stop_event.set()
                break

            global_attempt += stride
            if global_attempt <= max_attempts:
                next_delay = delay_for_attempt(master_seed, global_attempt, delay_window)
                if next_delay > current_delay:
                    emu.load_state(pre_macro_state)
                    emu.tick(next_delay - current_delay)
                else:
                    emu.load_state(state_bytes)
                    if next_delay:
                        emu.tick(next_delay)
                current_delay = next_delay

    progress_queue.put(WorkerProgress(
        worker_id=worker_id,
        attempts=n,
        latest_species=latest_species,
        latest_dvs=latest_dvs,
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
    delay_window: int = DEFAULT_DELAY_WINDOW,
) -> ParallelHuntResult:
    if num_workers is None:
        num_workers = max(1, (os.cpu_count() or 2) - 1)

    max_attempts = attempt_cap(max_attempts, delay_window)

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
                master_seed,
                max_attempts,
                result_queue,
                progress_queue,
                stop_event,
                num_workers,
                delay_window,
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

    def drain_progress() -> None:
        nonlocal total_attempts
        while True:
            try:
                prog = progress_queue.get_nowait()
            except Empty:
                break
            worker_attempts[prog.worker_id] = prog.attempts
            total_attempts = sum(worker_attempts)
            if on_progress:
                on_progress(
                    total_attempts,
                    prog.latest_species,
                    len(shinies),
                    prog.latest_dvs,
                )

    def drain_results() -> None:
        while True:
            try:
                res = result_queue.get_nowait()
            except Empty:
                break
            shinies.append(res)

    try:
        while any(p.is_alive() for p in workers):
            drain_progress()
            drain_results()

            time.sleep(0.05)
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        for p in workers:
            p.join(timeout=5)

    drain_progress()
    drain_results()

    total_attempts = sum(worker_attempts)
    return ParallelHuntResult(
        total_attempts=total_attempts,
        shinies=shinies,
        elapsed_s=time.monotonic() - t0,
    )
