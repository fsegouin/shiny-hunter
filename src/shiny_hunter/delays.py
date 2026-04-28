"""Frame-delay scheduling for deterministic hunt attempts."""
from __future__ import annotations

DEFAULT_DELAY_WINDOW = 1 << 16


def seed_offset(master_seed: int, delay_window: int = DEFAULT_DELAY_WINDOW) -> int:
    if delay_window < 1:
        raise ValueError("delay_window must be >= 1")
    return master_seed % delay_window
