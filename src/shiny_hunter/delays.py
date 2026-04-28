"""Frame-delay scheduling for deterministic hunt attempts."""
from __future__ import annotations

DEFAULT_DELAY_WINDOW = 1 << 16


def seed_offset(master_seed: int, delay_window: int = DEFAULT_DELAY_WINDOW) -> int:
    if delay_window < 1:
        raise ValueError("delay_window must be >= 1")
    return master_seed % delay_window


def delay_for_attempt(
    master_seed: int,
    attempt: int,
    delay_window: int = DEFAULT_DELAY_WINDOW,
) -> int:
    """Return the no-replacement frame delay for a 1-based attempt index."""
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    return (seed_offset(master_seed, delay_window) + attempt - 1) % delay_window


def attempt_cap(max_attempts: int, delay_window: int = DEFAULT_DELAY_WINDOW) -> int:
    if max_attempts < 0:
        raise ValueError("max_attempts must be >= 0")
    if delay_window < 1:
        raise ValueError("delay_window must be >= 1")
    return min(max_attempts, delay_window)
