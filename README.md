# shiny-hunter

Automatic Gen 1 shiny hunter for Pokémon Red, Blue, Green (JP), and Yellow.
Runs PyBoy headlessly, soft-resets the game thousands of times per minute, and
saves a `.sav` file the moment a Pokémon's DVs satisfy the Gen 2 transfer-shiny
condition.

## How it works

Gen 1 has no shiny mechanic in-game, but a Pokémon's DVs (Determinant Values)
decide its shininess when transferred to Gen 2 via the Time Capsule. The rule:

```
Def DV == 10  AND  Spd DV == 10  AND  Spc DV == 10
AND  Atk DV ∈ {2, 3, 6, 7, 10, 11, 14, 15}
```

Odds: ~1 / 8192 per roll.

The hunter loop:

1. Loads a PyBoy save-state parked one frame before the A-press that triggers
   the DV roll (the "Do you want this Pokémon?" → YES prompt).
2. Advances a randomized number of frames (`tick(delay)`) drawn from a
   seeded RNG. PyBoy is fully deterministic, so this *injected* jitter is
   what diverges DIV/`hRandomAdd`/`hRandomSub` between attempts.
3. Runs a per-region macro: A → "YES" → settle until party is formed.
4. Reads the party DV bytes from WRAM. If shiny, runs the in-game SAVE
   macro to commit to SRAM, dumps the SRAM, and writes a `.trace.json`
   sidecar so the run can be replayed exactly.
5. Otherwise, loop.

## Install

```bash
pip install -e .[dev]
```

Requires Python ≥ 3.11. PyBoy 2.7+ is pulled in as a dependency.

## Bring your own ROM

Place a legally-dumped ROM in `roms/`. Supported (game, region, SHA-1):

```bash
shiny-hunt list-games
```

If your ROM's SHA-1 isn't registered, the bot refuses to run. To add a new
language/region, drop a new file in `src/shiny_hunter/games/` mirroring
`red_us.py` and re-install.

## Onboarding flow

For each starter, you record a save-state once. Then you let the hunter run.

```bash
# 1. Record a save-state at the YES prompt for one Poké Ball.
shiny-hunt bootstrap --rom roms/red.gb --starter bulbasaur
# (PyBoy window opens. Play to the "Do you want this Pokémon?" YES prompt.
#  Close the window — the state is saved to states/red_us_bulbasaur.state.)

# 2. (Optional) Replace the hand-tuned YAML macro with a recorded one.
shiny-hunt record \
  --rom roms/red.gb \
  --from-state states/red_us_bulbasaur.state \
  --out src/shiny_hunter/macros/red_us_starter.events.json
# (PyBoy window opens with the bootstrap state already loaded. Press the
#  buttons to confirm the starter and advance dialog through party-add.
#  Close the window to write the JSON. Then point the GameConfig's
#  starter_macro at the .events.json filename instead of the .yaml.)

# 3. Sanity-check that the macro lands in a party-formed state.
shiny-hunt verify --rom roms/red.gb --starter bulbasaur
# Prints species + DVs. If species is 0 or unknown, your macro stopped
# too early — re-record (or extend the YAML's final `after`).

# 4. Hunt.
shiny-hunt run --rom roms/red.gb --starter bulbasaur --headless
# When a shiny is found, writes:
#   shinies/bulbasaur_us_<NNNNNN>.sav        — battery save (Time-Capsule-able)
#   shinies/bulbasaur_us_<NNNNNN>.trace.json — for `shiny-hunt replay`
```

Repeat for `--starter charmander` / `--starter squirtle` (and
`--starter pikachu` on Yellow).

## Replay a found shiny

The trace pins ROM SHA-1, state SHA-1, master seed, and attempt index. With
the same ROM + state, the run is deterministic:

```bash
shiny-hunt replay --rom roms/red.gb --trace shinies/bulbasaur_us_000042.trace.json
```

## Project layout

```
src/shiny_hunter/
  cli.py             entry point (run | bootstrap | verify | replay | record | list-games)
  hunter.py          main reset loop + replay
  emulator.py        PyBoy 2.x wrapper (banked SRAM dump, save/load state from bytes)
  recorder.py        windowed-mode joypad polling -> event-log macro
  dv.py              decode_dvs(), is_shiny()  — pure
  macro.py           YAML step macros + JSON event-log macros
  config.py          GameConfig + ROM-hash registry
  trace.py           per-attempt JSON traces
  progress.py        rich Live counter
  games/             per-(game, region) configs (red_us, red_jp, blue_us, ...)
  macros/            per-(game, region) starter + save macros (.yaml or .events.json)
```

## Caveats

- **JP RAM offsets are best-effort.** `red_jp.py`, `blue_jp.py`, `green_jp.py`,
  and `yellow_jp.py` ship with addresses derived from pret/pokered's JP build
  target. Verify against the disassembly's symbol file before running long
  sessions, or read the value at the supposed `party_dv_addr` and confirm it
  changes across attempts.
- **Macro tuning.** The default `after` durations work for typical text-speed
  settings. If `verify` reports `species=0`, the final settle frame budget is
  too low — bump `after` on the last step of the starter macro.
- **Checkpoint placement.** The save-state must be captured *before* the DV
  roll. The "YES" prompt is well before. If a checkpoint mistakenly sits past
  the roll, every attempt returns the same DVs — `verify` (run twice with
  different seeds) catches this immediately.
- **Output portability.** The `.sav` written when a shiny is found is a real
  battery-RAM dump and works on any GB/GBC emulator or real hardware via
  flashcart. The internal save-states (`.state`) are PyBoy-specific and
  shouldn't be used for transfer.

## License

MIT.
