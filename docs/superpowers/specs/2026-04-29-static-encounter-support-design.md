# Static Encounter Shiny Hunting

## Summary

Add support for shiny hunting overworld static encounters (Snorlax, legendaries, etc.) alongside the existing starter/gift flow. The key difference: static encounter DVs are rolled at battle start and live in enemy battle RAM, not in the party. The user checkpoints before the battle trigger, the macro starts the battle, and the tool reads enemy DVs immediately. If shiny, the battle state is saved and the user catches manually.

## Motivation

The current hunt loop only reads party DVs after the macro runs — this works for starters and gifts where the Pokémon joins the party directly. Static encounters enter a battle instead, and DVs are set in `wEnemyMonDVs` the moment the battle begins. Supporting this opens up all legendary and overworld encounters.

## Design

### GameConfig: add enemy addresses

Add two fields to `GameConfig`:

- `enemy_dv_addr: int` — `wEnemyMonDVs`
- `enemy_species_addr: int` — `wEnemyMonSpecies`

Addresses per ROM:

| Version | `enemy_species_addr` | `enemy_dv_addr` |
|---|---|---|
| Red/Blue US | `0xCFCC` | `0xCFD8` |
| Yellow US | `0xCFCB` | `0xCFD7` |
| Red/Blue/Green JP | `0xCFB3` | `0xCFBF` |
| Yellow JP | `0xCFB2` | `0xCFBE` |

JP addresses are best-effort from pret/pokered disassembly (same caveat as existing party addresses).

### CLI: `--mode` flag on `run`

Add `--mode` to the `run` command with two values:

- `starter` (default) — current behavior, reads `cfg.party_species_addr` / `cfg.party_dv_addr`
- `static` — reads `cfg.enemy_species_addr` / `cfg.enemy_dv_addr`

The flag controls which address pair is passed to the hunt loop. No other flags change.

### Hunt loop: address selection only

`hunt()` and `run_until_species()` already accept arbitrary `species_addr` and `dv_addr` parameters. The only change is in the CLI layer, which selects the right addresses based on `--mode`. The core hunt loop, delay scheduling, and persistence logic are unchanged.

The parallel hunt path (`hunt_parallel`) also takes `species_addr` and `dv_addr` as parameters — the CLI passes the mode-selected addresses through.

### Preview: skip in static mode

In static mode the Pokémon is in enemy battle RAM, not the party. `generate_preview()` reads party slot 0, so it would read the wrong data. Preview auto-generation is skipped in static mode. The user can run `shiny-hunt preview` manually after catching.

### Verify command

The `verify` command should also accept `--mode` so the user can test their static encounter macro.

### What stays the same

- `_persist_shiny` — saves state + trace, works as-is (the saved state captures the full emulator state including battle RAM)
- `delays.py` — frame jitter is mode-agnostic
- `run_until_species` / polling — already generic, just needs enemy addresses
- Trace format — no new fields (mode is implicit from the addresses used)
- Macro system — user records a macro that triggers the battle, same tooling

## Files changed

1. `src/shiny_hunter/config.py` — add `enemy_dv_addr` and `enemy_species_addr` to `GameConfig`
2. `src/shiny_hunter/games/*.py` (all 8) — add enemy addresses to each config
3. `src/shiny_hunter/cli.py` — add `--mode` flag to `run` and `verify`, select addresses, skip preview in static mode
4. `tests/test_config.py` — update to include new fields

## User workflow (static encounter)

1. `shiny-hunt bootstrap --rom red.gb --out states/snorlax.state` — play to just before interacting with Snorlax, close window
2. `shiny-hunt record --rom red.gb --from-state states/snorlax.state --out macros/snorlax.events.json` — record pressing A to talk to Snorlax and trigger the battle, close window
3. `shiny-hunt verify --rom red.gb --state states/snorlax.state --macro macros/snorlax.events.json --mode static` — confirm enemy DVs are read correctly
4. `shiny-hunt run --rom red.gb --state states/snorlax.state --macro macros/snorlax.events.json --mode static --continue-after-shiny` — hunt, find best shiny
5. `shiny-hunt resume --rom red.gb --state shinies/Snorlax_us_012345.state` — load shiny battle state, catch manually
