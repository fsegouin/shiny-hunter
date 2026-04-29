# Static Encounter Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--mode static` to the `run` and `verify` commands so the shiny hunter can target overworld static encounters (Snorlax, legendaries) by reading enemy battle RAM instead of party RAM.

**Architecture:** Add `enemy_dv_addr` and `enemy_species_addr` fields to `GameConfig`. A `--mode starter|static` CLI flag selects which address pair to pass to the existing hunt loop — no changes to core hunting, polling, or persistence logic. Preview auto-generation is skipped in static mode since the Pokémon isn't in the party yet.

**Tech Stack:** Python, Click CLI, PyBoy emulator, pytest

---

### Task 1: Add enemy address fields to GameConfig

**Files:**
- Modify: `src/shiny_hunter/config.py:13-33`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_enemy_dv_addr_in_wram_range():
    for c in cfg_mod.all_configs():
        assert 0xC000 <= c.enemy_dv_addr <= 0xDFFF


def test_enemy_species_addr_in_wram_range():
    for c in cfg_mod.all_configs():
        assert 0xC000 <= c.enemy_species_addr <= 0xDFFF
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_enemy_dv_addr_in_wram_range tests/test_config.py::test_enemy_species_addr_in_wram_range -v`
Expected: FAIL with `AttributeError: ... has no attribute 'enemy_dv_addr'`

- [ ] **Step 3: Add fields to GameConfig**

In `src/shiny_hunter/config.py`, add two fields to `GameConfig` after `party_species_addr`:

```python
enemy_dv_addr: int                     # wEnemyMonDVs (in-battle)
enemy_species_addr: int                # wEnemyMonSpecies (in-battle)
```

- [ ] **Step 4: Run test to verify it fails with a different error**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — existing game configs don't provide the new required fields yet.

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/config.py tests/test_config.py
git commit -m "Add enemy_dv_addr and enemy_species_addr fields to GameConfig"
```

---

### Task 2: Add enemy addresses to all game configs

**Files:**
- Modify: `src/shiny_hunter/games/red_us.py`
- Modify: `src/shiny_hunter/games/blue_us.py`
- Modify: `src/shiny_hunter/games/yellow_us.py`
- Modify: `src/shiny_hunter/games/red_jp.py`
- Modify: `src/shiny_hunter/games/blue_jp.py`
- Modify: `src/shiny_hunter/games/green_jp.py`
- Modify: `src/shiny_hunter/games/yellow_jp.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Add enemy addresses to Red US**

In `src/shiny_hunter/games/red_us.py`, add to the `GameConfig` constructor after `party_species_addr`:

```python
    enemy_dv_addr=0xCFD8,
    enemy_species_addr=0xCFCC,
```

- [ ] **Step 2: Add enemy addresses to Blue US**

In `src/shiny_hunter/games/blue_us.py`, add the same addresses (Red/Blue US share RAM layout):

```python
    enemy_dv_addr=0xCFD8,
    enemy_species_addr=0xCFCC,
```

- [ ] **Step 3: Add enemy addresses to Yellow US**

In `src/shiny_hunter/games/yellow_us.py`, add (Yellow shifts -1 byte):

```python
    enemy_dv_addr=0xCFD7,
    enemy_species_addr=0xCFCB,
```

- [ ] **Step 4: Add enemy addresses to Red JP**

In `src/shiny_hunter/games/red_jp.py`, add:

```python
    enemy_dv_addr=0xCFBF,
    enemy_species_addr=0xCFB3,
```

- [ ] **Step 5: Add enemy addresses to Blue JP**

In `src/shiny_hunter/games/blue_jp.py`, add the same JP addresses:

```python
    enemy_dv_addr=0xCFBF,
    enemy_species_addr=0xCFB3,
```

- [ ] **Step 6: Add enemy addresses to Green JP**

In `src/shiny_hunter/games/green_jp.py`, add the same JP addresses:

```python
    enemy_dv_addr=0xCFBF,
    enemy_species_addr=0xCFB3,
```

- [ ] **Step 7: Add enemy addresses to Yellow JP**

In `src/shiny_hunter/games/yellow_jp.py`, add (Yellow JP shifts -1 from JP Red/Blue):

```python
    enemy_dv_addr=0xCFBE,
    enemy_species_addr=0xCFB2,
```

- [ ] **Step 8: Run all config tests**

Run: `pytest tests/test_config.py -v`
Expected: ALL PASS — including the two new enemy address range tests from Task 1.

- [ ] **Step 9: Commit**

```bash
git add src/shiny_hunter/games/
git commit -m "Add enemy DV and species addresses to all game configs"
```

---

### Task 3: Add --mode flag to verify command

**Files:**
- Modify: `src/shiny_hunter/cli.py:91-158` (verify command + _verify_windowed)
- Modify: `src/shiny_hunter/hunter.py:141-170` (replay_attempt)
- Test: `tests/test_cli_help.py` (existing CLI help tests should still pass)

- [ ] **Step 1: Add species_addr/dv_addr parameters to replay_attempt**

In `src/shiny_hunter/hunter.py`, update `replay_attempt` to accept optional address overrides:

```python
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
    species_addr: int | None = None,
    dv_addr: int | None = None,
) -> tuple[int, DVs]:
    """Re-derive (species, DVs) for a specific attempt index.

    Uses the same no-replacement delay schedule as the hunt loop.
    """
    if target_attempt < 1:
        raise ValueError("target_attempt must be >= 1")
    delay = (seed_offset(master_seed, delay_window) + target_attempt - 1) % delay_window

    hunt_macro = macro.load(macro_path)
    with Emulator(rom_path, headless=headless) as emu:
        emu.load_state(state_bytes)
        if delay:
            emu.tick(delay)
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=species_addr if species_addr is not None else cfg.party_species_addr,
            dv_addr=dv_addr if dv_addr is not None else cfg.party_dv_addr,
        )
    return species, dvs
```

- [ ] **Step 2: Update _verify_windowed to accept address overrides**

In `src/shiny_hunter/cli.py`, update `_verify_windowed`:

```python
def _verify_windowed(cfg: GameConfig, rom: Path, state_path: Path, macro_path: Path,
                     species_addr: int, dv_addr: int):
    state_bytes = state_path.read_bytes()
    hunt_macro = macro.load(macro_path)

    from .polling import run_until_species

    with Emulator(rom, headless=False, realtime=True) as emu:
        emu.load_state(state_bytes)
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=species_addr,
            dv_addr=dv_addr,
        )

        click.echo("Macro complete — inspect the game state. Close the PyBoy window to continue.")
        while emu.tick(1, render=True):
            pass

    return species, dvs
```

- [ ] **Step 3: Add --mode flag to verify command**

In `src/shiny_hunter/cli.py`, add the `--mode` option to the `verify` command decorator and update the function:

Add this option after the `--window` option:

```python
@click.option(
    "--mode",
    type=click.Choice(["starter", "static"]),
    default="starter",
    show_default=True,
    help="Hunt mode: 'starter' reads party DVs, 'static' reads enemy battle DVs.",
)
```

Update the `verify` function signature to include `mode: str` and add address selection logic at the top of the function body:

```python
def verify(rom: Path, state_path: Path, macro_path: Path, game: str | None, region: str | None, window: bool, mode: str) -> None:
    """Run one attempt and print species + DVs."""
    cfg = _resolve_config(rom, game, region)

    if mode == "static":
        species_addr = cfg.enemy_species_addr
        dv_addr = cfg.enemy_dv_addr
    else:
        species_addr = cfg.party_species_addr
        dv_addr = cfg.party_dv_addr

    if window:
        species, dvs = _verify_windowed(cfg, rom, state_path, macro_path, species_addr, dv_addr)
    else:
        species, dvs = hunter.replay_attempt(
            cfg=cfg,
            rom_path=rom,
            state_bytes=state_path.read_bytes(),
            macro_path=macro_path,
            master_seed=0,
            target_attempt=1,
            headless=True,
            species_addr=species_addr,
            dv_addr=dv_addr,
        )
    name = pokemon.species_name(species)
    click.echo(f"species: 0x{species:02X} ({name})")
    click.echo(f"DVs:     atk={dvs.atk} def={dvs.def_} spd={dvs.spd} spc={dvs.spc} hp={dvs.hp}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 5: Verify CLI help**

Run: `python -m shiny_hunter.cli verify --help`
Expected: `--mode` option appears with `[starter|static]` choices.

- [ ] **Step 6: Commit**

```bash
git add src/shiny_hunter/hunter.py src/shiny_hunter/cli.py
git commit -m "Add --mode starter|static flag to verify command"
```

---

### Task 4: Add --mode flag to run command

**Files:**
- Modify: `src/shiny_hunter/cli.py:258-416` (run command)

- [ ] **Step 1: Add --mode option to run command**

In `src/shiny_hunter/cli.py`, add the `--mode` option to the `run` command decorator, after the `--start-delay` option and before the `--crystal-rom` option:

```python
@click.option(
    "--mode",
    type=click.Choice(["starter", "static"]),
    default="starter",
    show_default=True,
    help="Hunt mode: 'starter' reads party DVs, 'static' reads enemy battle DVs.",
)
```

- [ ] **Step 2: Update run function signature**

Add `mode: str` parameter to the `run` function signature (after `start_delay`):

```python
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
    mode: str,
    crystal_rom: Path | None,
    crystal_state: Path | None,
    crystal_macro: Path | None,
) -> None:
```

- [ ] **Step 3: Add address selection and skip preview in static mode**

At the top of the `run` function body, after `preview_cb = _make_preview_callback(...)`, add:

```python
    if mode == "static":
        species_addr = cfg.enemy_species_addr
        dv_addr = cfg.enemy_dv_addr
        preview_cb = None
    else:
        species_addr = cfg.party_species_addr
        dv_addr = cfg.party_dv_addr
```

- [ ] **Step 4: Wire addresses into single-threaded hunt path**

Update the `hunter.hunt()` call in the single-threaded path (`if num_workers == 1:`) to pass the selected addresses. Currently `hunt()` reads addresses from `cfg` internally — it uses `cfg.party_species_addr` and `cfg.party_dv_addr`. We need to add `species_addr` and `dv_addr` parameters to `hunt()`.

In `src/shiny_hunter/hunter.py`, update `hunt()` signature to add optional overrides:

```python
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
    on_shiny: Callable[[Path], None] | None = None,
    stop_on_first_shiny: bool = True,
    delay_window: int = DEFAULT_DELAY_WINDOW,
    start_delay: int | None = None,
    species_addr: int | None = None,
    dv_addr: int | None = None,
) -> HuntResult:
```

And update the `run_until_species` call inside `hunt()` to use them:

```python
        species, dvs, _ = run_until_species(
            emu, hunt_macro,
            species_addr=species_addr if species_addr is not None else cfg.party_species_addr,
            dv_addr=dv_addr if dv_addr is not None else cfg.party_dv_addr,
        )
```

Then in `cli.py`, pass the addresses to `hunt()`:

```python
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
                on_shiny=preview_cb,
                stop_on_first_shiny=not continue_after_shiny,
                delay_window=delay_window,
                start_delay=start_delay,
                species_addr=species_addr,
                dv_addr=dv_addr,
            )
```

- [ ] **Step 5: Wire addresses into parallel hunt path**

Update the `hunt_parallel()` call in the parallel path to use the selected addresses. Replace `cfg.party_species_addr` and `cfg.party_dv_addr`:

```python
            result = hunt_parallel(
                rom_path=rom,
                state_bytes=state_bytes,
                macro_path=macro_path,
                species_addr=species_addr,
                dv_addr=dv_addr,
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
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Verify CLI help**

Run: `python -m shiny_hunter.cli run --help`
Expected: `--mode` option appears with `[starter|static]` choices.

- [ ] **Step 8: Commit**

```bash
git add src/shiny_hunter/hunter.py src/shiny_hunter/cli.py
git commit -m "Add --mode starter|static flag to run command"
```
