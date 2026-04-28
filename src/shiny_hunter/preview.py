"""Shiny preview pipeline: replay → convert → inject → screenshot."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import config as cfg_mod
from . import macro, trace
from .crystal import inject_party_slot
from .delays import seed_offset
from .emulator import Emulator
from .gen1_party import read_party_slot
from .gen2_convert import convert
from .polling import run_until_species


def generate_preview(
    *,
    trace_path: Path,
    gen1_rom: Path,
    macro_path: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_png: Path,
) -> Path:
    tr = trace.load(trace_path)
    cfg = cfg_mod.by_sha1(tr.rom_sha1)
    if cfg is None:
        raise ValueError(f"unknown ROM in trace (sha1={tr.rom_sha1})")

    state_path = Path(tr.state_path)
    state_bytes = state_path.read_bytes()

    gen1_mon = _replay_and_read_party(
        cfg=cfg,
        rom_path=gen1_rom,
        state_bytes=state_bytes,
        macro_path=macro_path,
        master_seed=tr.master_seed,
        target_attempt=tr.attempt,
    )

    gen2_mon = convert(gen1_mon)

    crystal_macro_obj = macro.load(crystal_macro)

    with Emulator(crystal_rom, headless=True) as emu:
        emu.load_state(crystal_state.read_bytes())
        inject_party_slot(emu, gen2_mon, slot=1)
        crystal_macro_obj.run(emu)
        emu.tick(60)
        _screenshot(emu, out_png)

    return out_png


def _replay_and_read_party(
    *,
    cfg,
    rom_path: Path,
    state_bytes: bytes,
    macro_path: Path,
    master_seed: int,
    target_attempt: int,
):
    delay = (seed_offset(master_seed) + target_attempt - 1) % (1 << 16)
    hunt_macro = macro.load(macro_path)

    with Emulator(rom_path, headless=True) as emu:
        emu.load_state(state_bytes)
        if delay:
            emu.tick(delay)
        run_until_species(
            emu, hunt_macro,
            species_addr=cfg.party_species_addr,
            dv_addr=cfg.party_dv_addr,
        )
        return read_party_slot(emu, cfg, slot=0)


def _screenshot(emu: Emulator, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    screen = emu._pyboy.screen.ndarray
    img = Image.fromarray(screen)
    img.save(out_path)
