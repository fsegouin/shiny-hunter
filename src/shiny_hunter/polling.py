"""Early-exit species polling for the hunt loop.

Instead of waiting a fixed number of frames after the macro finishes,
poll RAM frame-by-frame until the species byte becomes non-zero.
This typically cuts ~60% of wasted idle frames.
"""
from __future__ import annotations

from .dv import DVs, decode_dvs
from .macro import EventMacro, Macro

SVBK_ADDR = 0xFF70


def wram_bank_readable(emu) -> bool:
    """True when SVBK maps WRAM bank 1 at $D000-$DFFF.

    CGB games remap $D000-$DFFF via SVBK ($FF70); party/enemy data lives in
    bank 1, so reads taken while another bank is mapped return garbage.
    SVBK values 0 and 1 both select bank 1.
    """
    return (emu.read_byte(SVBK_ADDR) & 0x07) <= 1


def run_until_species(
    emu,
    macro: Macro | EventMacro,
    *,
    species_addr: int,
    dv_addr: int,
    hard_cap: int = 1200,
    guard_wram_bank: bool = False,
) -> tuple[int, DVs, int]:
    """Run macro, polling for the species to appear in RAM.

    Returns (species, dvs, total_frames_ticked).
    If species doesn't appear within hard_cap polling frames after the
    macro, returns (0, decode_dvs(0, 0), total_frames_ticked).

    Recorded macros usually contain trailing inputs (nickname dialogs,
    etc.) long after the DV roll. When the target slot starts out empty,
    we poll *during* the macro and exit the moment species + DVs are
    readable — the leftover events are irrelevant since the hunt loop
    reloads state right after. If the slot starts non-zero (e.g. a static
    hunt checkpointed mid-battle with stale enemy data), mid-macro
    polling would latch that stale data, so we fall back to polling only
    after the macro completes.

    `guard_wram_bank` must be set for CGB games (Gen 2): party/enemy data
    lives in WRAM bank 1, but the game temporarily maps other banks via
    SVBK ($FF70) — e.g. battle animations use bank 5 — so a poll landing
    on such a frame would read garbage at $D000-$DFFF. Skip those frames.
    (SVBK values 0 and 1 both map bank 1.)
    """
    # 0xFF is the party species-list terminator: an empty party reads 0xFF
    # at wPartySpecies[0]. Gen 1 glitch hunts can legitimately yield 0xFF as
    # a species, so the post-macro poll accepts it there; Gen 2 never wants
    # it, and mid-macro reads must never latch it in either generation.
    accept_ff_after_macro = not guard_wram_bank

    def read_mon(accept_ff: bool) -> tuple[int, DVs] | None:
        if guard_wram_bank and not wram_bank_readable(emu):
            return None
        species = emu.read_byte(species_addr)
        if species == 0 or (species == 0xFF and not accept_ff):
            return None
        raw = emu.read_bytes(dv_addr, 2)
        if raw[0] == 0 and raw[1] == 0:
            return None
        return species, decode_dvs(raw[0], raw[1])

    bank_readable = not guard_wram_bank or wram_bank_readable(emu)
    slot_empty = bank_readable and read_mon(accept_ff_after_macro) is None
    on_frame = (lambda: read_mon(False)) if slot_empty else None

    if isinstance(macro, Macro):
        frames, found = _run_macro_except_last_after(emu, macro, on_frame)
    elif isinstance(macro, EventMacro):
        frames, found = _run_event_macro_events_only(emu, macro, on_frame)
    else:
        raise TypeError(f"Unsupported macro type: {type(macro)}")

    if found is not None:
        return found[0], found[1], frames

    for _ in range(hard_cap):
        emu.tick(1)
        frames += 1
        mon = read_mon(accept_ff_after_macro)
        if mon is not None:
            return mon[0], mon[1], frames

    return 0, decode_dvs(0, 0), frames


def _tick_polling(emu, frames: int, on_frame) -> tuple[int, tuple[int, DVs] | None]:
    """Tick `frames` frames, checking on_frame after each. Returns
    (frames_ticked, result) — stops early when on_frame hits."""
    if on_frame is None:
        emu.tick(frames)
        return frames, None
    for i in range(frames):
        emu.tick(1)
        found = on_frame()
        if found is not None:
            return i + 1, found
    return frames, None


def _run_macro_except_last_after(
    emu, macro: Macro, on_frame=None,
) -> tuple[int, tuple[int, DVs] | None]:
    """Run all Macro steps normally except skip the last step's 'after' wait.
    Returns (total frames ticked, early poll result or None)."""
    frames = 0
    steps = macro.steps
    for i, step in enumerate(steps):
        if step.button is not None:
            emu.button(step.button, step.hold)
            n, found = _tick_polling(emu, step.hold, on_frame)
            frames += n
            if found is not None:
                return frames, found
        is_last = i == len(steps) - 1
        if not is_last and step.after:
            n, found = _tick_polling(emu, step.after, on_frame)
            frames += n
            if found is not None:
                return frames, found
    return frames, None


def _run_event_macro_events_only(
    emu, macro: EventMacro, on_frame=None,
) -> tuple[int, tuple[int, DVs] | None]:
    """Replay all events at their frame indices, ignoring total_frames.
    Returns (total frames ticked, early poll result or None)."""
    cur = 0
    for ev in macro.events:
        if ev.frame > cur:
            n, found = _tick_polling(emu, ev.frame - cur, on_frame)
            cur += n
            if found is not None:
                return cur, found
        if ev.kind == "press":
            emu.button_press(ev.button)
        else:
            emu.button_release(ev.button)
    return cur, None
