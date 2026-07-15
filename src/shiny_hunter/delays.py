"""Frame-delay scheduling for deterministic hunt attempts."""
from __future__ import annotations

DEFAULT_DELAY_WINDOW = 1 << 16

# Save a full snapshot every N delays; intermediate delays are reached by
# load(base) + tick(offset). Optimal N ≈ sqrt(2 * save_cost / frame_cost);
# with ~20 ms saves and ~0.06 ms frames that's ~25 — rounded up to 32.
RELOAD_BATCH = 32


def seed_offset(master_seed: int, delay_window: int = DEFAULT_DELAY_WINDOW) -> int:
    if delay_window < 1:
        raise ValueError("delay_window must be >= 1")
    return master_seed % delay_window
