"""Shiny preview pipeline: load state → read party → convert → inject → screenshot.

Gen 1 sources go through the Time Capsule conversion (`gen2_convert`);
Gen 2 sources already hold a native 48-byte party struct, which is
injected into the Crystal preview ROM verbatim.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import config as cfg_mod
from . import gen1_party, gen2_party
from . import macro
from .crystal import inject_party_slot, inject_party_slot_bytes
from .emulator import Emulator
from .gen2_convert import convert
from .polling import wram_bank_readable
from .trace import sha1_of_file

# Frames to wait for SVBK to map WRAM bank 1 before reading a Gen 2 party.
_BANK_WAIT_CAP = 120


def generate_preview(
    *,
    hunt_rom: Path,
    shiny_state: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_png: Path,
    window: bool = False,
) -> Path:
    cfg = cfg_mod.by_sha1(sha1_of_file(hunt_rom))
    if cfg is None:
        raise ValueError(f"unknown ROM: {hunt_rom}")

    with Emulator(hunt_rom, headless=True) as emu:
        emu.load_state(shiny_state.read_bytes())
        emu.tick(60)
        if cfg.generation == 2:
            # The settle ticks above land on an arbitrary frame, and CGB
            # games map other WRAM banks over $D000-$DFFF (animations use
            # bank 5) — so wait for bank 1 before reading the party.
            for _ in range(_BANK_WAIT_CAP):
                if wram_bank_readable(emu):
                    break
                emu.tick(1)
            else:
                raise ValueError("WRAM bank 1 never mapped; cannot read Gen 2 party")
            gen2_raw = gen2_party.read_party_slot(emu, cfg, slot=0)
            gen2_mon = None
        else:
            gen1_mon = gen1_party.read_party_slot(emu, cfg, slot=0)
            gen2_mon = convert(gen1_mon)
            gen2_raw = None

    crystal_macro_obj = macro.load(crystal_macro)

    with Emulator(crystal_rom, headless=not window, realtime=window) as emu:
        emu.load_state(crystal_state.read_bytes())
        if gen2_mon is not None:
            inject_party_slot(emu, gen2_mon, slot=1)
        else:
            inject_party_slot_bytes(
                emu,
                struct_bytes=gen2_raw.struct_bytes,
                species=gen2_raw.species,
                ot_name=gen2_raw.ot_name,
                nickname=gen2_raw.nickname,
                slot=1,
            )
        crystal_macro_obj.run(emu)
        emu.tick(60, render=True)
        _screenshot(emu, out_png)
        if window:
            while emu.tick(1, render=True):
                pass

    return out_png


def _screenshot(emu: Emulator, out_path: Path, *, scale: int = 4) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    screen = emu.screen_ndarray()
    img = Image.fromarray(screen)
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(out_path)
