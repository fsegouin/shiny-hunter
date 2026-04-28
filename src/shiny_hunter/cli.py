"""shiny-hunt CLI."""
from __future__ import annotations

import os
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import config as cfg_mod
from . import hunter, macro, pokemon, recorder, trace
from .delays import DEFAULT_DELAY_WINDOW
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
    "--out",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Where to write the save-state file (e.g. states/red_us_eevee.state).",
)
def bootstrap(rom: Path, out: Path) -> None:
    """Open a windowed PyBoy. Play to just before the DV roll, then close the window to save."""
    out.parent.mkdir(parents=True, exist_ok=True)

    click.echo(f"Bootstrap: {rom} -> {out}")
    click.echo("Play to just before the DV roll, then close the window.")
    emu = Emulator(rom, headless=False)
    try:
        while emu.tick(1, render=True):
            pass
        emu.save_state(out)
        click.echo(f"saved state to {out}")
    finally:
        emu.stop(save=False)


def _verify_windowed(cfg: GameConfig, rom: Path, state_path: Path, macro_path: Path):
    state_bytes = state_path.read_bytes()
    hunt_macro = macro.load(macro_path)

    from .polling import run_until_species

    with Emulator(rom, headless=False, realtime=True) as emu:
        emu.load_state(state_bytes)
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=cfg.party_species_addr,
            dv_addr=cfg.party_dv_addr,
        )

        click.echo("Macro complete — inspect the game state. Close the PyBoy window to continue.")
        while emu.tick(1, render=True):
            pass

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
@click.option(
    "--workers",
    "num_workers",
    type=int,
    default=None,
    help="Number of parallel workers (default: cpu_count - 1). Use 1 for single-threaded.",
)
@click.option(
    "--delay-window",
    type=int,
    default=DEFAULT_DELAY_WINDOW,
    show_default=True,
    help="Number of no-repeat frame delays to search before declaring the window exhausted.",
)
@click.option(
    "--start-delay",
    type=int,
    default=None,
    help="Start scanning from this specific frame delay (e.g. from a previous --continue-after-shiny run).",
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
    num_workers: int | None,
    delay_window: int,
    start_delay: int | None,
) -> None:
    """Hunt for a shiny Pokémon."""
    cfg = _resolve_config(rom, game, region)
    state_bytes = state_path.read_bytes()
    master_seed = seed if seed is not None else time.time_ns()

    total_attempts = min(max_attempts, delay_window)
    parts = [
        f"hunting on {cfg.game}/{cfg.region}, seed={master_seed}",
        f"max={total_attempts:,}, delay_window={delay_window:,}, headless={headless}",
    ]
    if start_delay is not None:
        parts.append(f"start_delay={start_delay:,}")
    click.echo(", ".join(parts))

    if num_workers == 1:
        with live_progress(total_attempts=total_attempts) as (progress, updater):
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
                delay_window=delay_window,
                start_delay=start_delay,
            )

        click.echo(
            f"done: {result.attempts:,} attempts, {result.shinies_found} shiny in "
            f"{result.elapsed_s:0.1f}s ({result.attempts / max(result.elapsed_s, 1e-6):0.1f}/s)"
        )
    else:
        from .workers import hunt_parallel
        from .dv import decode_dvs

        actual_workers = num_workers if num_workers is not None else max(1, (os.cpu_count() or 2) - 1)

        out_dir.mkdir(parents=True, exist_ok=True)
        console = Console()

        with live_progress(total_attempts=total_attempts, num_workers=actual_workers, console=console) as (progress, updater):
            def on_worker_progress(worker_id: int, attempts: int) -> None:
                progress.worker_attempts[worker_id] = attempts

            def on_progress(total: int, species: int, shiny_count: int, dvs: tuple) -> None:
                progress.attempts = total
                progress.last_species = species
                progress.last_dvs = dvs
                progress.shinies = shiny_count
                updater.push()

            def on_shiny(res) -> None:
                name = pokemon.species_name(res.species)
                dvs = decode_dvs(res.dvs_raw[0], res.dvs_raw[1])
                state_name = f"{name}_{cfg.region}_{res.delay:06d}.state"
                trace_name = f"{name}_{cfg.region}_{res.delay:06d}.trace.json"
                (out_dir / state_name).write_bytes(res.state_bytes)
                trace.write(
                    out_dir / trace_name,
                    rom_path=rom,
                    state_bytes=state_bytes,
                    game=cfg.game,
                    region=cfg.region,
                    state_path=str(state_path),
                    master_seed=res.master_seed,
                    attempt=res.attempt,
                    delay=res.delay,
                    species=res.species,
                    species_name=name,
                    dvs=dvs,
                )
                console.print(
                    f"[bold green]shiny![/] {name} — delay={res.delay:,} "
                    f"ATK={dvs.atk} DEF={dvs.def_} SPD={dvs.spd} SPC={dvs.spc} HP={dvs.hp} "
                    f"(worker {res.worker_id})"
                )

            result = hunt_parallel(
                rom_path=rom,
                state_bytes=state_bytes,
                macro_path=macro_path,
                species_addr=cfg.party_species_addr,
                dv_addr=cfg.party_dv_addr,
                master_seed=master_seed,
                max_attempts=max_attempts,
                num_workers=num_workers,
                on_progress=on_progress,
                on_worker_progress=on_worker_progress,
                on_shiny=on_shiny,
                delay_window=delay_window,
                start_delay=start_delay,
                stop_after_first=not continue_after_shiny,
            )

        click.echo(
            f"done: {result.total_attempts:,} attempts, {len(result.shinies)} shiny in "
            f"{result.elapsed_s:0.1f}s ({result.total_attempts / max(result.elapsed_s, 1e-6):0.1f}/s)"
        )

        if result.shinies and len(result.shinies) > 1:
            ranked = sorted(
                result.shinies,
                key=lambda r: (
                    (r.dvs_raw[0] >> 4) & 0xF,
                    ((r.dvs_raw[0] >> 4) & 1) << 3,
                ),
                reverse=True,
            )
            best = ranked[0]
            best_dvs = decode_dvs(best.dvs_raw[0], best.dvs_raw[1])
            click.echo(f"\nfound {len(ranked)} shiny delay(s):")
            for i, res in enumerate(ranked):
                dvs = decode_dvs(res.dvs_raw[0], res.dvs_raw[1])
                name = pokemon.species_name(res.species)
                marker = "  <<< best" if i == 0 else ""
                click.echo(
                    f"  delay={res.delay:>6,}  {name} (0x{res.species:02X})  "
                    f"ATK={dvs.atk} DEF={dvs.def_} SPD={dvs.spd} "
                    f"SPC={dvs.spc} HP={dvs.hp}{marker}"
                )
            click.echo(
                f"\nbest: delay {best.delay:,} — ATK={best_dvs.atk}, HP={best_dvs.hp}"
            )
            click.echo(f"use:  shiny-hunt run --start-delay {best.delay} ...")


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
    "--state",
    "state_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Save-state to load (.state).",
)
def resume(rom: Path, state_path: Path) -> None:
    """Load a save-state and play in a windowed emulator."""
    click.echo(f"Resuming from {state_path}")
    emu = Emulator(rom, headless=False)
    try:
        emu.load_state(state_path.read_bytes())
        while emu.tick(1, render=True):
            pass
    finally:
        emu.stop(save=True)


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
    rom_sha = sha1_of_file(rom)
    cfg = cfg_mod.by_sha1(rom_sha)
    if cfg is None and game and region:
        cfg = cfg_mod.by_key(game, region)

    label = f"{cfg.game}/{cfg.region}" if cfg else rom.name
    click.echo(f"Recording on {label}; close the PyBoy window to stop.")
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


@main.command()
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Gen 1 ROM (.gb) that produced the shiny.",
)
@click.option(
    "--state",
    "shiny_state",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Saved .state from the shiny find (party already in RAM).",
)
@click.option(
    "--crystal-rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Pokemon Crystal ROM (.gbc).",
)
@click.option(
    "--crystal-state",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Crystal template save-state (.state) with 1 pokemon in party.",
)
@click.option(
    "--crystal-macro",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Crystal macro to navigate to slot 2 stats screen.",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Output PNG path. Defaults to <state_stem>.png alongside the state.",
)
@click.option(
    "--window",
    is_flag=True,
    help="Run Crystal windowed after injection; close the PyBoy window when done debugging.",
)
def preview(
    rom: Path,
    shiny_state: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_path: Path | None,
    window: bool,
) -> None:
    """Generate a Crystal screenshot of a shiny found in Gen 1."""
    from .preview import generate_preview

    if out_path is None:
        out_path = shiny_state.with_suffix(".png")

    click.echo(f"Generating preview for {shiny_state.name}...")
    if window:
        click.echo("Crystal will stay open after the screenshot. Close the PyBoy window to finish.")
    result = generate_preview(
        gen1_rom=rom,
        shiny_state=shiny_state,
        crystal_rom=crystal_rom,
        crystal_state=crystal_state,
        crystal_macro=crystal_macro,
        out_png=out_path,
        window=window,
    )
    click.echo(f"Preview saved to {result}")


if __name__ == "__main__":
    main()
