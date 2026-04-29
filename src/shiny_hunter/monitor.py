"""Pygame-based monitor grid for parallel shiny hunting."""
from __future__ import annotations

import math

from .workers import WorkerFrame


def grid_size(n: int) -> tuple[int, int]:
    """Compute (cols, rows) for n workers. Prefer wider-than-tall layouts."""
    if n <= 0:
        return (1, 1)
    rows = max(1, math.floor(math.sqrt(n)))
    cols = math.ceil(n / rows)
    return (cols, rows)


def update_frames(frames: dict[int, WorkerFrame], new: WorkerFrame) -> None:
    """Update the frame dict. A non-shiny frame never overwrites a shiny one."""
    existing = frames.get(new.worker_id)
    if existing is not None and existing.is_shiny and not new.is_shiny:
        return
    frames[new.worker_id] = new
