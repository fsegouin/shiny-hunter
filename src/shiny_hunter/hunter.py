"""Main shiny-hunting loop: load state -> jitter -> A-press -> read DVs -> repeat."""
from __future__ import annotations

import io
import random
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable

from . import macro, trace
from .config import GameConfig
from .dv import DVs, decode_dvs, is_shiny
from .emulator import Emulator

JITTER_RANGE = 256  # ≈4 s of frames


@dataclass
class HuntResult:
    attempts: int
    shinies_found: int
    elapsed_s: float


def _macro_path(filename: str) -> Path:
    return Path(str(resources.files("shiny_hunter").joinpath("macros", filename)))


def _read_dvs(emu: Emulator, addr: int) -> DVs:
    bytes_ = emu.read_bytes(addr, 2)
    return decode_dvs(bytes_[0], bytes_[1])


def hunt(
    *,
    cfg: GameConfig,
    rom_path: Path,
    state_bytes: bytes,
    out_dir: Path,
    starter: str,
    master_seed: int,
    max_attempts: int,
    headless: bool = True,
    on_attempt: Callable[[int, int, DVs, bool], None] | None = None,
    stop_on_first_shiny: bool = True,
) -> HuntResult:
    """Run the reset loop until `max_attempts` or the first shiny.

    Args:
        cfg: per-(game, region) config.
        rom_path: path to the user's ROM (used for trace SHA-1 reference).
        state_bytes: the bootstrap save-state bytes (read once, replayed each attempt).
        out_dir: where to write `<starter>_<region>_<n>.sav` and `.trace.json`.
        starter: which starter we expect to receive (used for output filenames).
        master_seed: seed for the per-attempt jitter RNG.
        max_attempts: hard upper bound on resets.
        on_attempt: optional callback `(attempt, species, dvs, shiny)` for progress UIs.
        stop_on_first_shiny: break the loop after the first shiny found.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(master_seed)
    starter_macro = macro.load(_macro_path(cfg.starter_macro))
    save_macro = macro.load(_macro_path(cfg.save_macro))

    shinies = 0
    t0 = time.monotonic()
    n = 0

    with Emulator(rom_path, headless=headless) as emu:
        while n < max_attempts:
            n += 1
            delay = rng.randint(0, JITTER_RANGE)
            emu.load_state(state_bytes)
            if delay:
                emu.tick(delay)
            starter_macro.run(emu)
            emu.tick(cfg.post_macro_settle_frames)

            species = emu.read_byte(cfg.party_species_addr)
            dvs = _read_dvs(emu, cfg.party_dv_addr)
            shiny = is_shiny(dvs)
            if on_attempt is not None:
                on_attempt(n, species, dvs, shiny)

            if shiny:
                shinies += 1
                _persist_shiny(
                    emu=emu,
                    cfg=cfg,
                    rom_path=rom_path,
                    state_bytes=state_bytes,
                    out_dir=out_dir,
                    starter=starter,
                    master_seed=master_seed,
                    attempt=n,
                    delay=delay,
                    species=species,
                    dvs=dvs,
                    save_macro=save_macro,
                )
                if stop_on_first_shiny:
                    break

    return HuntResult(attempts=n, shinies_found=shinies, elapsed_s=time.monotonic() - t0)


def _persist_shiny(
    *,
    emu: Emulator,
    cfg: GameConfig,
    rom_path: Path,
    state_bytes: bytes,
    out_dir: Path,
    starter: str,
    master_seed: int,
    attempt: int,
    delay: int,
    species: int,
    dvs: DVs,
    save_macro: macro.Macro,
) -> None:
    """On shiny: trigger an in-game SAVE, then dump SRAM and write trace."""
    species_name = cfg.starters.get(species, f"species_0x{species:02X}")
    # The starter is in WRAM but not yet committed to SRAM. Run the in-game
    # save macro so the .sav we dump contains the new party member.
    save_macro.run(emu)
    emu.tick(cfg.post_macro_settle_frames)

    sram = emu.dump_sram(cfg.sram_size)
    sav_name = f"{species_name}_{cfg.region}_{attempt:06d}.sav"
    trace_name = f"{species_name}_{cfg.region}_{attempt:06d}.trace.json"
    (out_dir / sav_name).write_bytes(sram)
    trace.write(
        out_dir / trace_name,
        rom_path=rom_path,
        state_bytes=state_bytes,
        game=cfg.game,
        region=cfg.region,
        starter=starter,
        master_seed=master_seed,
        attempt=attempt,
        delay=delay,
        species=species,
        species_name=species_name,
        dvs=dvs,
    )


def replay_attempt(
    *,
    cfg: GameConfig,
    rom_path: Path,
    state_bytes: bytes,
    master_seed: int,
    target_attempt: int,
    headless: bool = True,
) -> tuple[int, DVs]:
    """Re-derive (species, DVs) for a specific attempt index.

    Skips through (target_attempt - 1) RNG draws, then runs one full attempt.
    """
    if target_attempt < 1:
        raise ValueError("target_attempt must be >= 1")
    rng = random.Random(master_seed)
    for _ in range(target_attempt - 1):
        rng.randint(0, JITTER_RANGE)
    delay = rng.randint(0, JITTER_RANGE)

    starter_macro = macro.load(_macro_path(cfg.starter_macro))
    with Emulator(rom_path, headless=headless) as emu:
        emu.load_state(state_bytes)
        if delay:
            emu.tick(delay)
        starter_macro.run(emu)
        emu.tick(cfg.post_macro_settle_frames)
        species = emu.read_byte(cfg.party_species_addr)
        dvs = _read_dvs(emu, cfg.party_dv_addr)
    return species, dvs
