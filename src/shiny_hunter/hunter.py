"""Main shiny-hunting loop: load state -> jitter -> A-press -> read DVs -> repeat."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Callable

from . import macro, pokemon, trace
from .config import GameConfig
from .dv import DVs, is_shiny
from .emulator import Emulator
from .polling import run_until_species

JITTER_RANGE = 256  # ≈4 s of frames


@dataclass
class HuntResult:
    attempts: int
    shinies_found: int
    elapsed_s: float


def _macro_path(filename: str) -> Path:
    return Path(str(resources.files("shiny_hunter").joinpath("macros", filename)))


def hunt(
    *,
    cfg: GameConfig,
    rom_path: Path,
    state_bytes: bytes,
    state_path: str,
    macro_path: Path,
    out_dir: Path,
    master_seed: int,
    max_attempts: int,
    headless: bool = True,
    on_attempt: Callable[[int, int, DVs, bool], None] | None = None,
    stop_on_first_shiny: bool = True,
) -> HuntResult:
    """Run the reset loop until `max_attempts` or the first shiny."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(master_seed)
    hunt_macro = macro.load(macro_path)
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
            species, dvs, _ = run_until_species(
                emu, hunt_macro,
                species_addr=cfg.party_species_addr,
                dv_addr=cfg.party_dv_addr,
            )
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
                    state_path=state_path,
                    out_dir=out_dir,
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
    state_path: str,
    out_dir: Path,
    master_seed: int,
    attempt: int,
    delay: int,
    species: int,
    dvs: DVs,
    save_macro: macro.Macro | macro.EventMacro,
) -> None:
    """On shiny: trigger an in-game SAVE, then dump SRAM and write trace."""
    name = pokemon.species_name(species)
    save_macro.run(emu)
    emu.tick(cfg.post_macro_settle_frames)

    sram = emu.dump_sram(cfg.sram_size)
    sav_name = f"{name}_{cfg.region}_{attempt:06d}.sav"
    trace_name = f"{name}_{cfg.region}_{attempt:06d}.trace.json"
    (out_dir / sav_name).write_bytes(sram)
    trace.write(
        out_dir / trace_name,
        rom_path=rom_path,
        state_bytes=state_bytes,
        game=cfg.game,
        region=cfg.region,
        state_path=state_path,
        master_seed=master_seed,
        attempt=attempt,
        delay=delay,
        species=species,
        species_name=name,
        dvs=dvs,
    )


def replay_attempt(
    *,
    cfg: GameConfig,
    rom_path: Path,
    state_bytes: bytes,
    macro_path: Path,
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

    hunt_macro = macro.load(macro_path)
    with Emulator(rom_path, headless=headless) as emu:
        emu.load_state(state_bytes)
        if delay:
            emu.tick(delay)
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=cfg.party_species_addr,
            dv_addr=cfg.party_dv_addr,
        )
    return species, dvs
