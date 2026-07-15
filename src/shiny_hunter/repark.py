"""Re-park a hunt checkpoint as close to the DV roll as possible.

Every frame between the save-state and the decisive input is re-emulated on
every attempt, so a checkpoint parked at the start of a long dialog chain
(e.g. Crystal rolls the starter's DVs ~800 frames after the YES confirm,
when GivePokemon runs mid-dialog) wastes most of each attempt.

`repark()` replays the macro once to find the earliest frame where the
species + DVs are readable, then walks backwards through the macro's press
events: park just before a press, rebase the remaining events into a new
short macro, and probe a few delays. The park point is valid when the
probes produce *differing* DVs (jitter still reaches the roll) — if they
all match, the roll already happened before the press, so back off to the
previous one.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import GameConfig
from .emulator import Emulator
from .macro import Event, EventMacro
from .polling import run_until_species, wram_bank_readable

# Frames between the new checkpoint and the first rebased event, so the
# first attempt (delay 0) still has room for the press to register.
_LEAD_FRAMES = 2
_PROBE_DELAYS = (0, 7, 23)


@dataclass(frozen=True)
class ReparkResult:
    state_bytes: bytes
    macro: EventMacro
    park_frame: int          # frame of the original macro the state is parked at
    species_frame: int       # earliest readable frame in the original macro
    frames_saved: int        # per-attempt frames no longer emulated


def _readable(emu, species_addr: int, dv_addr: int, guard: bool) -> bool:
    if guard and not wram_bank_readable(emu):
        return False
    species = emu.read_byte(species_addr)
    if species in (0x00, 0xFF):  # 0xFF = party species-list terminator
        return False
    raw = emu.read_bytes(dv_addr, 2)
    return raw[0] != 0 or raw[1] != 0


def _find_species_frame(
    rom_path: Path, state_bytes: bytes, macro: EventMacro,
    species_addr: int, dv_addr: int, guard: bool,
) -> int:
    with Emulator(rom_path, headless=True) as emu:
        emu.load_state(state_bytes)
        cur = 0
        for ev in macro.events:
            while cur < ev.frame:
                emu.tick(1)
                cur += 1
                if _readable(emu, species_addr, dv_addr, guard):
                    return cur
            if ev.kind == "press":
                emu.button_press(ev.button)
            else:
                emu.button_release(ev.button)
        for _ in range(1200):
            emu.tick(1)
            cur += 1
            if _readable(emu, species_addr, dv_addr, guard):
                return cur
    raise ValueError("species never became readable while replaying the macro")


def _state_at(rom_path: Path, state_bytes: bytes, macro: EventMacro, frame: int) -> bytes:
    """Replay the macro up to (and including) `frame`, return the state."""
    with Emulator(rom_path, headless=True) as emu:
        emu.load_state(state_bytes)
        cur = 0
        for ev in macro.events:
            if ev.frame > frame:
                break
            if ev.frame > cur:
                emu.tick(ev.frame - cur)
                cur = ev.frame
            if ev.kind == "press":
                emu.button_press(ev.button)
            else:
                emu.button_release(ev.button)
        if frame > cur:
            emu.tick(frame - cur)
        return emu.save_state_bytes()


def _rebased_macro(macro: EventMacro, park_frame: int, name: str) -> EventMacro:
    events = tuple(
        Event(frame=ev.frame - park_frame + _LEAD_FRAMES, kind=ev.kind, button=ev.button)
        for ev in macro.events
        if ev.frame > park_frame
    )
    total = max(macro.total_frames - park_frame + _LEAD_FRAMES, events[-1].frame if events else 0)
    return EventMacro(
        name=name, events=events, total_frames=total,
        rom_sha1=macro.rom_sha1, from_state=macro.from_state,
    )


def _probe(
    rom_path: Path, state_bytes: bytes, macro: EventMacro,
    species_addr: int, dv_addr: int, guard: bool,
) -> tuple[str, list[tuple[int, tuple[int, int, int, int]]]]:
    """Run a few delays from the candidate state.

    Returns (verdict, rolls) where verdict is one of:
      "ok"          — DVs vary across delays, so the roll is still ahead
      "unreadable"  — a probe produced no mon (the macro failed from here)
      "identical"   — every probe rolled the same DVs (the roll already
                      happened before this park point)
    """
    rolls = []
    for delay in _PROBE_DELAYS:
        with Emulator(rom_path, headless=True) as emu:
            emu.load_state(state_bytes)
            if delay:
                emu.tick(delay)
            species, dvs, _ = run_until_species(
                emu, macro, species_addr=species_addr, dv_addr=dv_addr,
                guard_wram_bank=guard,
            )
        if species in (0x00, 0xFF):
            return "unreadable", rolls
        rolls.append((species, (dvs.atk, dvs.def_, dvs.spd, dvs.spc)))
    distinct = {r[1] for r in rolls}
    return ("ok" if len(distinct) > 1 else "identical"), rolls


def repark(
    *,
    rom_path: Path,
    state_bytes: bytes,
    macro: EventMacro,
    cfg: GameConfig,
    species_addr: int,
    dv_addr: int,
    on_progress: Callable[[str], None] | None = None,
) -> ReparkResult:
    guard = cfg.generation == 2
    say = on_progress or (lambda msg: None)

    species_frame = _find_species_frame(
        rom_path, state_bytes, macro, species_addr, dv_addr, guard,
    )
    say(f"species readable at frame {species_frame} of the original macro")

    press_frames = sorted(
        {ev.frame for ev in macro.events if ev.kind == "press" and ev.frame < species_frame},
        reverse=True,
    )
    if not press_frames:
        raise ValueError("no press events before the species frame — nothing to repark")

    last_verdict = "identical"
    for press_frame in press_frames:
        park_frame = press_frame - 1
        say(f"trying park point at frame {park_frame} (before press at {press_frame})...")
        candidate_state = _state_at(rom_path, state_bytes, macro, park_frame)
        candidate_macro = _rebased_macro(macro, park_frame, macro.name)
        verdict, rolls = _probe(
            rom_path, candidate_state, candidate_macro, species_addr, dv_addr, guard,
        )
        if verdict == "ok":
            say(f"park point valid — probe DVs vary: {[r[1] for r in rolls]}")
            return ReparkResult(
                state_bytes=candidate_state,
                macro=candidate_macro,
                park_frame=park_frame,
                species_frame=species_frame,
                frames_saved=park_frame,
            )
        last_verdict = verdict
        if verdict == "unreadable":
            say("probe produced no Pokémon from this park point — backing off")
        else:
            say("probe DVs identical (roll is before this press) — backing off")

    if last_verdict == "unreadable":
        raise ValueError(
            "no valid park point found: the macro never produced a Pokémon from "
            "any park point. The macro may not reach the DV roll."
        )
    raise ValueError(
        "no valid park point found: every probe produced identical DVs. "
        "The checkpoint may already sit after the DV roll."
    )
