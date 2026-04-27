"""Live progress reporting via rich."""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from rich.console import Console
from rich.live import Live
from rich.table import Table


class Progress:
    def __init__(self) -> None:
        self._start = time.monotonic()
        self.attempts = 0
        self.shinies = 0
        self.last_dvs: tuple[int, int, int, int] | None = None
        self.last_species: int | None = None

    def render(self) -> Table:
        elapsed = max(time.monotonic() - self._start, 1e-6)
        rate = self.attempts / elapsed
        eta = (8192 / rate) if rate > 0 else float("inf")
        table = Table.grid(padding=(0, 2))
        table.add_row("attempts", f"{self.attempts:,}")
        table.add_row("shinies", str(self.shinies))
        table.add_row("rate", f"{rate:0.1f}/s")
        table.add_row("elapsed", f"{elapsed:0.1f}s")
        table.add_row("avg eta (1/8192)", f"{eta:0.0f}s" if eta != float("inf") else "—")
        if self.last_dvs is not None:
            a, d, sp, sc = self.last_dvs
            table.add_row("last DVs", f"atk={a} def={d} spd={sp} spc={sc}")
        if self.last_species is not None:
            table.add_row("last species", f"0x{self.last_species:02X}")
        return table


@contextmanager
def live_progress(console: Console | None = None, refresh_per_second: float = 4) -> Iterator[tuple[Progress, "_Updater"]]:
    progress = Progress()
    console = console or Console()
    with Live(progress.render(), console=console, refresh_per_second=refresh_per_second) as live:
        yield progress, _Updater(progress, live)


class _Updater:
    def __init__(self, progress: Progress, live: Live) -> None:
        self._progress = progress
        self._live = live

    def push(self) -> None:
        self._live.update(self._progress.render())
