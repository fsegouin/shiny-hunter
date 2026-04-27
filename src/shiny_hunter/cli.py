"""shiny-hunt CLI."""
from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import config as cfg_mod
from . import hunter, trace
from .config import GameConfig
from .emulator import Emulator
from .progress import live_progress
from .trace import sha1_of_file


def _resolve_config(rom: Path, game: str | None, region: str | None) -> GameConfig:
    sha = sha1_of_file(rom)
    found = cfg_mod.by_sha1(sha)
    if game is not None and region is not None:
        forced = cfg_mod.by_key(game, region)
        if forced is None:
            raise click.ClickException(f"unknown (game, region) = ({game!r}, {region!r})")
        if found is not None and forced.rom_sha1 != sha:
            click.echo(
                f"warning: --game/--region override does not match ROM SHA-1 (rom={sha[:12]}, "
                f"forced={forced.rom_sha1[:12]})",
                err=True,
            )
        return forced
    if found is None:
        raise click.ClickException(
            f"unknown ROM (sha1={sha}). Use `shiny-hunt list-games` to see registered "
            f"configurations, or pass --game and --region to force a config."
        )
    return found


def _state_path(cfg: GameConfig, starter: str) -> Path:
    return Path("states") / f"{cfg.game}_{cfg.region}_{starter}.state"


@click.group()
def main() -> None:
    """Automatic Gen 1 shiny hunter."""


@main.command("list-games")
def list_games() -> None:
    """Print the registered (game, region, sha1) entries."""
    table = Table(title="Registered Pokémon Gen 1 ROMs")
    table.add_column("game")
    table.add_column("region")
    table.add_column("sha1")
    table.add_column("starters")
    for c in cfg_mod.all_configs():
        names = ", ".join(sorted(c.starters.values()))
        table.add_row(c.game, c.region, c.rom_sha1, names)
    Console().print(table)


@main.command()
@click.option("--rom", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--starter", required=True, help="Which starter the bootstrap state is parked at.")
@click.option("--game", default=None)
@click.option("--region", default=None)
def bootstrap(rom: Path, starter: str, game: str | None, region: str | None) -> None:
    """Open a windowed PyBoy. Play to the 'YES' prompt; close the window to save the state."""
    cfg = _resolve_config(rom, game, region)
    if starter not in {s.lower() for s in cfg.starters.values()}:
        raise click.ClickException(
            f"starter {starter!r} not valid for {cfg.game}/{cfg.region}; "
            f"valid: {sorted(cfg.starters.values())}"
        )
    state_dir = Path("states")
    state_dir.mkdir(exist_ok=True)
    out = _state_path(cfg, starter)

    click.echo(f"Bootstrap: {cfg.game}/{cfg.region} -> {out}")
    click.echo("Play to the 'Do you want this Pokémon?' YES prompt, then close the window.")
    emu = Emulator(rom, headless=False)
    try:
        while emu.tick(1, render=True):
            pass
        emu.save_state(out)
        click.echo(f"saved state to {out}")
    finally:
        emu.stop(save=False)


@main.command()
@click.option("--rom", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--starter", required=True)
@click.option("--game", default=None)
@click.option("--region", default=None)
def verify(rom: Path, starter: str, game: str | None, region: str | None) -> None:
    """Run one attempt against the bootstrap state and print species + DVs."""
    cfg = _resolve_config(rom, game, region)
    state = _state_path(cfg, starter)
    if not state.exists():
        raise click.ClickException(f"no bootstrap state at {state}; run `shiny-hunt bootstrap` first")

    species, dvs = hunter.replay_attempt(
        cfg=cfg,
        rom_path=rom,
        state_bytes=state.read_bytes(),
        master_seed=0,
        target_attempt=1,
        headless=True,
    )
    species_name = cfg.starters.get(species, f"unknown(0x{species:02X})")
    click.echo(f"species: 0x{species:02X} ({species_name})")
    click.echo(f"DVs:     atk={dvs.atk} def={dvs.def_} spd={dvs.spd} spc={dvs.spc} hp={dvs.hp}")
    if species_name not in cfg.starters.values():
        click.echo("warning: species byte does not match a known starter — increase the macro's "
                   "final 'after' or recheck the bootstrap checkpoint.", err=True)


@main.command()
@click.option("--rom", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--starter", required=True)
@click.option("--game", default=None)
@click.option("--region", default=None)
@click.option("--max-attempts", type=int, default=100_000, show_default=True)
@click.option("--seed", type=int, default=None, help="Master RNG seed; default uses time_ns().")
@click.option("--out", "out_dir", type=click.Path(file_okay=False, path_type=Path), default=Path("shinies"))
@click.option("--headless/--window", default=True)
@click.option("--continue-after-shiny", is_flag=True)
def run(
    rom: Path,
    starter: str,
    game: str | None,
    region: str | None,
    max_attempts: int,
    seed: int | None,
    out_dir: Path,
    headless: bool,
    continue_after_shiny: bool,
) -> None:
    """Hunt for a shiny starter."""
    cfg = _resolve_config(rom, game, region)
    state = _state_path(cfg, starter)
    if not state.exists():
        raise click.ClickException(f"no bootstrap state at {state}; run `shiny-hunt bootstrap` first")
    state_bytes = state.read_bytes()
    master_seed = seed if seed is not None else time.time_ns()

    click.echo(
        f"hunting {starter} on {cfg.game}/{cfg.region}, seed={master_seed}, "
        f"max={max_attempts:,}, headless={headless}"
    )

    with live_progress() as (progress, updater):
        def on_attempt(n: int, species: int, dvs, shiny: bool) -> None:
            progress.attempts = n
            progress.last_dvs = (dvs.atk, dvs.def_, dvs.spd, dvs.spc)
            progress.last_species = species
            if shiny:
                progress.shinies += 1
            updater.push()

        result = hunter.hunt(
            cfg=cfg,
            rom_path=rom,
            state_bytes=state_bytes,
            out_dir=out_dir,
            starter=starter,
            master_seed=master_seed,
            max_attempts=max_attempts,
            headless=headless,
            on_attempt=on_attempt,
            stop_on_first_shiny=not continue_after_shiny,
        )

    click.echo(
        f"done: {result.attempts:,} attempts, {result.shinies_found} shiny in "
        f"{result.elapsed_s:0.1f}s ({result.attempts / max(result.elapsed_s, 1e-6):0.1f}/s)"
    )


@main.command()
@click.option("--trace", "trace_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--rom", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
def replay(trace_path: Path, rom: Path) -> None:
    """Reproduce the (species, DVs) of a previously found shiny from its trace."""
    tr = trace.load(trace_path)
    rom_sha = sha1_of_file(rom)
    if rom_sha != tr.rom_sha1:
        raise click.ClickException(
            f"ROM SHA-1 mismatch: trace expects {tr.rom_sha1}, got {rom_sha}"
        )
    cfg = cfg_mod.by_sha1(tr.rom_sha1)
    if cfg is None:
        raise click.ClickException(f"unknown ROM in trace (sha1={tr.rom_sha1})")

    state = _state_path(cfg, tr.starter)
    if not state.exists():
        raise click.ClickException(f"no bootstrap state at {state}")
    state_bytes = state.read_bytes()
    if trace.sha1_of_bytes(state_bytes) != tr.state_sha1:
        raise click.ClickException(
            f"state SHA-1 mismatch: trace expects {tr.state_sha1}, got {trace.sha1_of_bytes(state_bytes)}"
        )

    species, dvs = hunter.replay_attempt(
        cfg=cfg,
        rom_path=rom,
        state_bytes=state_bytes,
        master_seed=tr.master_seed,
        target_attempt=tr.attempt,
        headless=True,
    )
    expected = tr.dvs
    actual = dvs.as_dict()
    match = (species == tr.species and all(actual[k] == expected[k] for k in ("atk", "def", "spd", "spc")))
    click.echo(f"replayed attempt {tr.attempt}: species=0x{species:02X} DVs={actual}")
    click.echo(f"expected: species=0x{tr.species:02X} DVs={expected}")
    if not match:
        raise click.ClickException("replay mismatch — emulator state is not deterministic w.r.t. trace")
    click.echo("OK: replay matches trace")


if __name__ == "__main__":
    main()
