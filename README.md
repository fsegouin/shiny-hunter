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

## How the RNG works (Gen 1) and why frame jitter matters

Gen 1's RNG state is two HRAM bytes, `hRandomAdd` and `hRandomSub`. They
are perturbed by the Game Boy's hardware divider register `rDIV` at
`$FF04`, which auto-increments at **16384 Hz** (once every 256 CPU
cycles) and is impossible for game code to pause. The `Random` routine
(verbatim from [`pret/pokered`](https://github.com/pret/pokered/blob/master/engine/math/random.asm)):

```asm
Random_::
    ldh a, [rDIV]
    ld  b, a
    ldh a, [hRandomAdd]
    adc b
    ldh [hRandomAdd], a
    ldh a, [rDIV]
    ld  b, a
    ldh a, [hRandomSub]
    sbc b
    ldh [hRandomSub], a
    ret
```

Each call mixes the *current* `rDIV` value into both running totals. The
public `Random` wrapper returns `hRandomAdd` to the caller. Because
`rDIV` advances on its own real-time clock, two calls separated by a
slightly different number of CPU cycles will read different `rDIV`
values and produce different results.

### How DVs are rolled

When you accept a starter from Oak, the game eventually runs `AddPartyMon`,
which calls `Random` **twice** to fill the two DV bytes (see
[`engine/pokemon/add_mon.asm`](https://github.com/pret/pokered/blob/master/engine/pokemon/add_mon.asm)):

```asm
call Random            ; 1st call -> spd/spc byte (high nybble = Spd, low = Spc)
ld   b, a
call Random            ; 2nd call -> atk/def byte (high nybble = Atk, low = Def)
...
ld   [hli], a          ; store atk/def at wPartyMon1DVs + 0
ld   [hl],  b          ;                spd/spc at wPartyMon1DVs + 1
```

So the four DV nybbles (Atk, Def, Spd, Spc) come from two consecutive
`Random` calls, both of which depend on `rDIV` at the moment they
execute. HP DV is derived from the LSBs of the other four — it isn't
rolled separately.

### Why frame jitter changes the outcome

PyBoy is fully deterministic: same ROM + same starting save-state +
same input sequence ⇒ bit-identical output. That includes `rDIV`. So
without jitter, every soft-reset would re-roll the same DVs forever.

The hunter loop gets variation by inserting `pyboy.tick(delay)` between
`load_state(...)` and the A-press macro, where `delay ∈ [0, 256)` comes
from a seeded `random.Random`. Each emulated frame is 70224 CPU cycles,
during which `rDIV` increments ~274 times. Different `delay` values
mean `Random` runs with a different `rDIV` at the precise instant of
each call — which in turn shifts `hRandomAdd`/`hRandomSub` and,
ultimately, the two DV bytes. Empirically a few hundred frames of
jitter range covers the full DV space.

This is exactly the same physical phenomenon that makes manual
soft-resetting work on real hardware: a human can't press A on the same
CPU cycle twice, so `rDIV` is different at each press. We just simulate
that variability on purpose.

### Is Gen 2 RNG the same?

For *our* use case, **Gen 2's RNG is never invoked**. We're not catching
the Pokémon in Gen 2 — we're catching it in Gen 1 and transferring via
the Time Capsule. Shininess in Gen 2 is checked as a **static predicate
over the existing DVs**: Def/Spd/Spc DV all equal 10, Atk DV is in
`{2, 3, 6, 7, 10, 11, 14, 15}`. No roll happens at transfer time.

For native Gen 2 hunting (e.g., shiny hunting Totodile in Crystal),
Gold/Silver/Crystal use a very similar mechanism: an `hRandomAdd`
/`hRandomSub` pair mixed with `rDIV` on every call. It's the same
fundamental design, with minor differences in mixing constants and in
*where* the RNG is consulted during encounter generation. So if we
later extend this tool to hunt natively in Gen 2, the same "inject
frame jitter before the decisive A-press" trick applies.

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
