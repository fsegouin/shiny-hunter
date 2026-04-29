"""Tests for parallel hunt worker data structures."""
from __future__ import annotations

import numpy as np

from shiny_hunter.workers import WorkerResult, WorkerProgress, ParallelHuntResult, WorkerFrame


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
    assert r.state_bytes == b"\x00" * 10


def test_worker_progress_dataclass():
    p = WorkerProgress(
        worker_id=1,
        attempts=500,
        latest_species=0xB0,
        latest_dvs=(10, 9, 10, 12),
    )
    assert p.attempts == 500


def test_parallel_hunt_result():
    r = ParallelHuntResult(total_attempts=1000, shinies=[], elapsed_s=5.0)
    assert r.total_attempts == 1000
    assert len(r.shinies) == 0


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
