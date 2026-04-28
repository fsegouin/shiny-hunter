"""Early-exit species polling for the hunt loop.

Instead of waiting a fixed number of frames after the macro finishes,
poll RAM frame-by-frame until the species byte becomes non-zero.
This typically cuts ~60% of wasted idle frames.
"""
from __future__ import annotations

from typing import Union

from .dv import DVs, decode_dvs
from .macro import EventMacro, Macro


def run_until_species(
    emu,
    macro: Union[Macro, EventMacro],
    *,
    species_addr: int,
    dv_addr: int,
    hard_cap: int = 1200,
) -> tuple[int, DVs, int]:
    """Run macro then poll until species appears in RAM.

    Returns (species, dvs, total_frames_ticked).
    If species doesn't appear within hard_cap polling frames, returns
    (0, decode_dvs(0, 0), total_frames_ticked).
    """
    if isinstance(macro, Macro):
        frames = _run_macro_except_last_after(emu, macro)
    elif isinstance(macro, EventMacro):
        frames = _run_event_macro_events_only(emu, macro)
    else:
        raise TypeError(f"Unsupported macro type: {type(macro)}")

    for _ in range(hard_cap):
        emu.tick(1)
        frames += 1
        species = emu.read_byte(species_addr)
        if species != 0:
            raw = emu.read_bytes(dv_addr, 2)
            if raw[0] != 0 or raw[1] != 0:
                dvs = decode_dvs(raw[0], raw[1])
                return species, dvs, frames

    return 0, decode_dvs(0, 0), frames


def _run_macro_except_last_after(emu, macro: Macro) -> int:
    """Run all Macro steps normally except skip the last step's 'after' wait.
    Returns total frames ticked."""
    frames = 0
    steps = macro.steps
    for i, step in enumerate(steps):
        if step.button is not None:
            emu.button(step.button, step.hold)
            emu.tick(step.hold)
            frames += step.hold
        is_last = i == len(steps) - 1
        if not is_last and step.after:
            emu.tick(step.after)
            frames += step.after
    return frames


def _run_event_macro_events_only(emu, macro: EventMacro) -> int:
    """Replay all events at their frame indices, ignoring total_frames.
    Returns total frames ticked."""
    cur = 0
    for ev in macro.events:
        if ev.frame > cur:
            emu.tick(ev.frame - cur)
            cur = ev.frame
        if ev.kind == "press":
            emu.button_press(ev.button)
        else:
            emu.button_release(ev.button)
    return cur
