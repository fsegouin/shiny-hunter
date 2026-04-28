"""Main shiny-hunting loop: load state -> jitter -> A-press -> read DVs -> repeat."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import macro, pokemon, trace
from .config import GameConfig
from .delays import DEFAULT_DELAY_WINDOW, attempt_cap, delay_for_attempt, seed_offset
from .dv import DVs, is_shiny
from .emulator import Emulator
from .polling import run_until_species


@dataclass
class HuntResult:
    attempts: int
    shinies_found: int
    elapsed_s: float


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
    delay_window: int = DEFAULT_DELAY_WINDOW,
    start_delay: int | None = None,
) -> HuntResult:
    """Run the reset loop until `max_attempts` or the first shiny."""
    out_dir.mkdir(parents=True, exist_ok=True)
    hunt_macro = macro.load(macro_path)
    max_attempts = attempt_cap(max_attempts, delay_window)
    effective_seed = start_delay if start_delay is not None else master_seed

    shinies = 0
    t0 = time.monotonic()
    n = 0

    with Emulator(rom_path, headless=headless) as emu:
        current_delay = seed_offset(effective_seed, delay_window)
        emu.load_state(state_bytes)
        if current_delay:
            emu.tick(current_delay)

        while n < max_attempts:
            n += 1
            delay = current_delay
            pre_macro_state = emu.save_state_bytes()
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
                    master_seed=effective_seed,
                    attempt=n,
                    delay=delay,
                    species=species,
                    dvs=dvs,
                )
                if stop_on_first_shiny:
                    break

            if n < max_attempts:
                current_delay = (current_delay + 1) % delay_window
                if current_delay == 0:
                    emu.load_state(state_bytes)
                else:
                    emu.load_state(pre_macro_state)
                    emu.tick(1)

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
) -> None:
    """On shiny: save emulator state + write trace."""
    name = pokemon.species_name(species)
    state_name = f"{name}_{cfg.region}_{attempt:06d}.state"
    trace_name = f"{name}_{cfg.region}_{attempt:06d}.trace.json"

    emu.save_state(out_dir / state_name)

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
    delay_window: int = DEFAULT_DELAY_WINDOW,
) -> tuple[int, DVs]:
    """Re-derive (species, DVs) for a specific attempt index.

    Uses the same no-replacement delay schedule as the hunt loop.
    """
    if target_attempt < 1:
        raise ValueError("target_attempt must be >= 1")
    delay = delay_for_attempt(master_seed, target_attempt, delay_window)

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
