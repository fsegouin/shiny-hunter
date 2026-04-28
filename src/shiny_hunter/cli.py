"""shiny-hunt CLI."""
from __future__ import annotations

import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import config as cfg_mod
from . import hunter, macro, pokemon, recorder, trace
from .config import GameConfig
from .dv import decode_dvs
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
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the Game Boy ROM (.gb). Region is auto-detected from the SHA-1.",
)
@click.option(
    "--starter",
    required=True,
    help="Which starter the bootstrap state is parked at (e.g. bulbasaur, charmander, squirtle, pikachu).",
)
@click.option(
    "--game",
    default=None,
    help="Force a game name (red|blue|green|yellow). Only needed when ROM SHA-1 lookup fails.",
)
@click.option(
    "--region",
    default=None,
    help="Force a region (us|jp|eu|de|fr|it|es). Only needed alongside --game.",
)
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


def _verify_windowed(cfg: GameConfig, rom: Path, state_path: Path, macro_path: Path):
    import random

    state_bytes = state_path.read_bytes()
    rng = random.Random(0)
    delay = rng.randint(0, hunter.JITTER_RANGE)

    hunt_macro = macro.load(macro_path)

    with Emulator(rom, headless=False, realtime=True) as emu:
        emu.load_state(state_bytes)
        if delay:
            emu.tick(delay)
        hunt_macro.run(emu)
        emu.tick(cfg.post_macro_settle_frames)

        click.echo("Macro complete — inspect the game state. Close the PyBoy window to continue.")
        while emu.tick(1, render=True):
            pass

        species = emu.read_byte(cfg.party_species_addr)
        raw = emu.read_bytes(cfg.party_dv_addr, 2)
        dvs = decode_dvs(raw[0], raw[1])

    return species, dvs


@main.command()
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the Game Boy ROM (.gb).",
)
@click.option(
    "--state",
    "state_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Save-state file to load (.state).",
)
@click.option(
    "--macro",
    "macro_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Macro to replay (.yaml or .events.json).",
)
@click.option("--game", default=None, help="Force game name; only needed if SHA-1 lookup fails.")
@click.option("--region", default=None, help="Force region; only needed alongside --game.")
@click.option(
    "--window",
    is_flag=True,
    help="Run windowed in real-time; pause after the macro so you can inspect the game state.",
)
def verify(rom: Path, state_path: Path, macro_path: Path, game: str | None, region: str | None, window: bool) -> None:
    """Run one attempt and print species + DVs."""
    cfg = _resolve_config(rom, game, region)

    if window:
        species, dvs = _verify_windowed(cfg, rom, state_path, macro_path)
    else:
        species, dvs = hunter.replay_attempt(
            cfg=cfg,
            rom_path=rom,
            state_bytes=state_path.read_bytes(),
            macro_path=macro_path,
            master_seed=0,
            target_attempt=1,
            headless=True,
        )
    name = pokemon.species_name(species)
    click.echo(f"species: 0x{species:02X} ({name})")
    click.echo(f"DVs:     atk={dvs.atk} def={dvs.def_} spd={dvs.spd} spc={dvs.spc} hp={dvs.hp}")


@main.command()
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the Game Boy ROM (.gb).",
)
@click.option(
    "--state",
    "state_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Save-state file to reload each attempt (.state).",
)
@click.option(
    "--macro",
    "macro_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Macro to replay each attempt (.yaml or .events.json).",
)
@click.option("--game", default=None, help="Force game name; only needed if SHA-1 lookup fails.")
@click.option("--region", default=None, help="Force region; only needed alongside --game.")
@click.option(
    "--max-attempts",
    type=int,
    default=100_000,
    show_default=True,
    help="Hard upper bound on resets before the hunt aborts.",
)
@click.option("--seed", type=int, default=None, help="Master RNG seed; default uses time_ns().")
@click.option(
    "--out",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("shinies"),
    show_default=True,
    help="Directory where .sav and .trace.json files are written when a shiny is found.",
)
@click.option(
    "--headless/--window",
    default=True,
    show_default=True,
    help="Run without a visible PyBoy window (fastest), or show one for debugging.",
)
@click.option(
    "--continue-after-shiny",
    is_flag=True,
    help="Keep hunting after the first shiny is found (default: stop).",
)
def run(
    rom: Path,
    state_path: Path,
    macro_path: Path,
    game: str | None,
    region: str | None,
    max_attempts: int,
    seed: int | None,
    out_dir: Path,
    headless: bool,
    continue_after_shiny: bool,
) -> None:
    """Hunt for a shiny Pokémon."""
    cfg = _resolve_config(rom, game, region)
    state_bytes = state_path.read_bytes()
    master_seed = seed if seed is not None else time.time_ns()

    click.echo(
        f"hunting on {cfg.game}/{cfg.region}, seed={master_seed}, "
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
            state_path=str(state_path),
            macro_path=macro_path,
            out_dir=out_dir,
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
@click.option(
    "--trace",
    "trace_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the .trace.json sidecar written when the shiny was found.",
)
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Same ROM that produced the trace; SHA-1 is verified against the trace.",
)
@click.option(
    "--macro",
    "macro_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Same macro used during the hunt (.yaml or .events.json).",
)
def replay(trace_path: Path, rom: Path, macro_path: Path) -> None:
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

    state = Path(tr.state_path)
    if not state.exists():
        raise click.ClickException(f"no state file at {state}")
    state_bytes = state.read_bytes()
    if trace.sha1_of_bytes(state_bytes) != tr.state_sha1:
        raise click.ClickException(
            f"state SHA-1 mismatch: trace expects {tr.state_sha1}, got {trace.sha1_of_bytes(state_bytes)}"
        )

    species, dvs = hunter.replay_attempt(
        cfg=cfg,
        rom_path=rom,
        state_bytes=state_bytes,
        macro_path=macro_path,
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


@main.command()
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the Game Boy ROM (.gb).",
)
@click.option(
    "--from-state",
    "from_state",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="PyBoy save-state to load before recording (typically a bootstrap state).",
)
@click.option(
    "--out",
    "out_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Where to write the recorded event-log JSON (typical: macros/<name>.events.json).",
)
@click.option(
    "--max-frames",
    type=int,
    default=None,
    help="Hard cap on recorded frames; default is unlimited (until you close the window).",
)
@click.option("--game", default=None, help="Force game name; only needed if SHA-1 lookup fails.")
@click.option("--region", default=None, help="Force region; only needed alongside --game.")
def record(
    rom: Path,
    from_state: Path,
    out_path: Path,
    max_frames: int | None,
    game: str | None,
    region: str | None,
) -> None:
    """Record a frame-indexed input macro by playing in a PyBoy window.

    Loads --from-state, opens a window, and logs every press/release with
    its frame index. Close the window when you're done; the JSON is
    written to --out and replays deterministically against the same
    starting state.
    """
    cfg = _resolve_config(rom, game, region)
    rom_sha = sha1_of_file(rom)

    click.echo(f"Recording on {cfg.game}/{cfg.region}; close the PyBoy window to stop.")
    click.echo(f"  rom        = {rom}")
    click.echo(f"  from_state = {from_state}")
    click.echo(f"  out        = {out_path}")

    emu = Emulator(rom, headless=False)
    try:
        emu.load_state(from_state)
        macro = recorder.record(
            emu,
            name=out_path.name,
            rom_sha1=rom_sha,
            from_state=str(from_state),
            max_frames=max_frames,
        )
    finally:
        emu.stop(save=False)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    recorder.write(macro, out_path)
    click.echo(
        f"wrote {out_path}: {len(macro.events)} events over {macro.total_frames} frames"
    )


if __name__ == "__main__":
    main()
