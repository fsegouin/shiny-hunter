"""Live progress reporting via rich."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

_WORKER_COLORS = [
    "cyan", "green", "yellow", "magenta", "blue", "red",
    "bright_cyan", "bright_green", "bright_yellow", "bright_magenta",
]


def _segmented_bar(worker_attempts: list[int], per_worker: int, width: int) -> Text:
    """Build a defrag-style bar: each worker occupies an equal slice, filled by their progress."""
    n = len(worker_attempts)
    text = Text()
    for i, wa in enumerate(worker_attempts):
        # distribute rounding residue across the first few segments
        seg_width = width // n + (1 if i < width % n else 0)
        filled = round(min(wa, per_worker) / per_worker * seg_width) if per_worker > 0 else 0
        color = _WORKER_COLORS[i % len(_WORKER_COLORS)]
        text.append("█" * filled, style=f"bold {color}")
        text.append("░" * (seg_width - filled), style=f"dim {color}")
    return text


class Progress:
    def __init__(self, *, total_attempts: int | None = None, num_workers: int = 1) -> None:
        self._start = time.monotonic()
        self.attempts = 0
        self.shinies = 0
        self.last_dvs: tuple[int, int, int, int] | None = None
        self.last_species: int | None = None
        self.total_attempts = total_attempts
        self.num_workers = num_workers
        self.worker_attempts: list[int] = [0] * max(1, num_workers)

    def render(self) -> Table:
        elapsed = max(time.monotonic() - self._start, 1e-6)
        rate = self.attempts / elapsed
        prob = 1 - (8191 / 8192) ** self.attempts if self.attempts > 0 else 0.0
        total = self.total_attempts if self.total_attempts and self.total_attempts > 0 else None
        table = Table.grid(padding=(0, 2))
        if total is not None:
            pct = min(self.attempts, total) / total * 100
            if self.num_workers > 1:
                per_worker = total // self.num_workers
                bar: Text | ProgressBar = _segmented_bar(self.worker_attempts, per_worker, 48)
            else:
                bar = ProgressBar(total=total, completed=min(self.attempts, total), width=48)
            table.add_row("progress", bar, f"{pct:.1f}%")
        if total is not None:
            table.add_row("attempts", f"{self.attempts:,} / {total:,}")
        else:
            table.add_row("attempts", f"{self.attempts:,}")
        table.add_row("shinies", str(self.shinies))
        table.add_row("rate", f"{rate:0.1f}/s")
        table.add_row("elapsed", f"{elapsed:0.1f}s")
        table.add_row("cumulative chance", f"{prob:.1%}")
        if self.last_dvs is not None:
            a, d, sp, sc = self.last_dvs
            table.add_row("last DVs", f"atk={a} def={d} spd={sp} spc={sc}")
        if self.last_species is not None:
            table.add_row("last species", f"0x{self.last_species:02X}")
        return table


@contextmanager
def live_progress(
    console: Console | None = None,
    refresh_per_second: float = 4,
    *,
    total_attempts: int | None = None,
    num_workers: int = 1,
) -> Iterator[tuple[Progress, "_Updater"]]:
    progress = Progress(total_attempts=total_attempts, num_workers=num_workers)
    console = console or Console()
    with Live(progress.render(), console=console, refresh_per_second=refresh_per_second) as live:
        yield progress, _Updater(progress, live)


class _Updater:
    def __init__(self, progress: Progress, live: Live) -> None:
        self._progress = progress
        self._live = live

    def push(self) -> None:
        self._live.update(self._progress.render())
