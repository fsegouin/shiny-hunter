"""Shiny preview pipeline: load state → read party → convert → inject → screenshot."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import config as cfg_mod
from . import macro
from .crystal import inject_party_slot
from .emulator import Emulator
from .gen1_party import read_party_slot
from .gen2_convert import convert
from .trace import sha1_of_file


def generate_preview(
    *,
    gen1_rom: Path,
    shiny_state: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_png: Path,
    window: bool = False,
) -> Path:
    cfg = cfg_mod.by_sha1(sha1_of_file(gen1_rom))
    if cfg is None:
        raise ValueError(f"unknown ROM: {gen1_rom}")

    with Emulator(gen1_rom, headless=True) as emu:
        emu.load_state(shiny_state.read_bytes())
        emu.tick(60)
        gen1_mon = read_party_slot(emu, cfg, slot=0)

    gen2_mon = convert(gen1_mon)

    crystal_macro_obj = macro.load(crystal_macro)

    with Emulator(crystal_rom, headless=not window, realtime=window) as emu:
        emu.load_state(crystal_state.read_bytes())
        inject_party_slot(emu, gen2_mon, slot=1)
        crystal_macro_obj.run(emu)
        emu.tick(60, render=True)
        _screenshot(emu, out_png)
        if window:
            while emu.tick(1, render=True):
                pass

    return out_png


def _screenshot(emu: Emulator, out_path: Path, *, scale: int = 4) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    screen = emu._pyboy.screen.ndarray
    img = Image.fromarray(screen)
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale), Image.NEAREST)
    img.save(out_path)
