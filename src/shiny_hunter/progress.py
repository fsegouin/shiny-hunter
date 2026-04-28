"""Live progress reporting via rich."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.live import Live
from rich.progress_bar import ProgressBar
from rich.table import Table


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
        eta = (8192 / rate) if rate > 0 else float("inf")
        prob = 1 - (8191 / 8192) ** self.attempts if self.attempts > 0 else 0.0
        total = self.total_attempts if self.total_attempts and self.total_attempts > 0 else None
        table = Table.grid(padding=(0, 2))
        if total is not None:
            table.add_row(
                "progress",
                ProgressBar(
                    total=total,
                    completed=min(self.attempts, total),
                    width=32,
                ),
            )
        if total is not None:
            table.add_row("attempts", f"{self.attempts:,} / {total:,}")
        else:
            table.add_row("attempts", f"{self.attempts:,}")
        if self.num_workers > 1:
            per_worker = total // self.num_workers if total else None
            for i, wa in enumerate(self.worker_attempts):
                if per_worker:
                    bar = ProgressBar(total=per_worker, completed=min(wa, per_worker), width=20)
                    table.add_row(f"  worker {i}", bar)
                else:
                    table.add_row(f"  worker {i}", f"{wa:,}")
        table.add_row("shinies", str(self.shinies))
        table.add_row("rate", f"{rate:0.1f}/s")
        table.add_row("elapsed", f"{elapsed:0.1f}s")
        table.add_row("cumulative chance", f"{prob:.1%}")
        table.add_row("avg eta (1/8192)", f"{eta:0.0f}s" if eta != float("inf") else "—")
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
