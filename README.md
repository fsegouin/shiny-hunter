# shiny-hunter

![Shiny Charmander in Red](https://github.com/fsegouin/shiny-hunter/blob/c22a92786f2d036054ac260f2f59c867ebcd5a7b/demo.gif)

Automatic Gen 1 shiny hunter for Pokémon Red, Blue, Green (JP), and Yellow.
Runs PyBoy headlessly, soft-resets the game thousands of times per minute, and
saves a `.state` file the moment a Pokémon's DVs satisfy the Gen 2 transfer-shiny
condition. Works for any Pokémon — starters, gifts, wild encounters — as long as
you can create a save-state checkpoint before the DV roll and a macro that
triggers it. On a decent computer, this process can take between 5 to 15 minutes,
depending on if you want to keep searching for better DVs or if you settle
for the first one found.

## How it works

Gen 1 has no shiny mechanic in-game, but a Pokémon's DVs (Determinant Values)
decide its shininess when transferred to Gen 2 via the Time Capsule. The rule:

```
Def DV == 10  AND  Spd DV == 10  AND  Spc DV == 10
AND  Atk DV ∈ {2, 3, 6, 7, 10, 11, 14, 15}
```

Odds: ~1 / 8192 per roll.

The hunter loop:

1. Loads a PyBoy save-state parked just before the action that triggers
   the DV roll.
2. Advances a deterministic no-repeat frame delay from a seeded
   65,536-frame window. PyBoy is fully deterministic, so this *injected*
   jitter is what diverges DIV/`hRandomAdd`/`hRandomSub` between attempts.
3. Runs a user-supplied macro that triggers the DV roll and waits for the
   Pokémon to appear in the party.
4. Reads the party DV bytes from WRAM. If shiny, saves the state to `/shinies`
   and writes a `.trace.json` sidecar so the run can be replayed exactly.
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

When a Pokémon is added to the party, the game runs `AddPartyMon`,
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
`load_state(...)` and the A-press macro, where `delay` comes from a
seeded no-repeat walk over a 65,536-frame window. Each emulated frame is
70224 CPU cycles, during which `rDIV` increments ~274 times. Different
`delay` values mean `Random` runs with a different `rDIV` at the precise
instant of each call — which in turn shifts `hRandomAdd`/`hRandomSub`
and, ultimately, the two DV bytes.

Use `shiny-hunt run --continue-after-shiny` to scan the entire delay
window for a given state/macro pair. It runs the emulator for each
delay, reports every shiny found live (ranked by DV quality at the
end), and saves state+trace files for each. If the run exhausts the
window without finding a shiny, that state/macro combo cannot produce
one — re-record the macro or create a new checkpoint.

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

## This sounds like a lot of faff for something you could have hacked?

Agree. But where's the fun in doing so? The Pokemon obtained here is
100% legit, generated by the game itself, and will always pass legit checks.
Let's just say this is speeding up the reset process _a bit_ :)

## Can I do this on retail?

Most other "retail" RNG tricks such as the ones used in Gen 3 games
use a Linear Congruential RNG with a known seed. You can predict the entire
sequence from the seed, count frames from a known landmark, and hit your target.
The state is internal and marches forward predictably.

Gen 1 is fundamentally different — there is no PRNG. The game reads
the DIV register (0xFF04), a hardware timer that increments every 256 T-cycles
regardless of CPU activity. hRandomAdd and hRandomSub are updated every VBlank from DIV.
When GivePokemon calls Random() twice for the DV bytes, it's reading values derived
from this hardware timer. There's no seed, no sequence, no state to predict from a formula
— just "what does the oscillator happen to read right now". Hence the need to brute force
the DIV value until we find a shiny.

## Setup

```bash
python -mv venv .venv
source .venv/bin/activate # bash/zsh
source .venv/bin/activate.fish # fish
```

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

Three steps: checkpoint, record, hunt. Works for any Pokémon whose DV roll
you can park in front of — starters, gifts (Eevee, Lapras, Hitmonlee/chan),
legendaries, or any static encounter.

### 1. Create a save-state checkpoint

Play in a windowed emulator to just before the action that triggers the DV
roll, then close the window.

```bash
shiny-hunt bootstrap \
  --rom roms/red.gb \
  --out states/red_us_eevee.state
# PyBoy window opens. Play to just before the DV roll.
# Close the window — state is saved.
```

### 2. Record a macro

Record the button sequence that triggers the DV roll and waits for the
Pokémon to appear in the party. The macro is a frame-indexed JSON log of
press/release events.

```bash
shiny-hunt record \
  --rom roms/red.gb \
  --from-state states/red_us_eevee.state \
  --out macros/red_us_eevee.events.json
# PyBoy window opens with the checkpoint loaded.
# Press the buttons to trigger the encounter and advance dialog.
# Close the window when done — the JSON is written.
```

### 3. Verify the macro

Check that the macro lands in a state where the Pokémon's DVs are readable.

```bash
shiny-hunt verify \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json
# Prints species + DVs. If species is "unknown", the macro stopped too
# early — re-record with more frames after the last button press.
```

Use `--window` to watch the macro replay in real-time and visually inspect the
game state before the DV check:

```bash
shiny-hunt verify \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --window
# Plays the macro at 60 fps, then pauses. Close the window to see DVs.
```

### 4. Hunt

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --headless
# Scans frame delays sequentially across all cores.
# Stops at the first shiny and saves:
#   shinies/eevee_us_delay042000.state       — resume with `shiny-hunt resume`
#   shinies/eevee_us_delay042000.trace.json  — for `shiny-hunt replay`
```

Use `--continue-after-shiny` to scan the entire delay window and find
every shiny delay. Each shiny is reported live as it's found, and a
ranked summary (by ATK DV, highest first) is printed at the end:

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --continue-after-shiny --headless
# Example output:
#   shiny! EEVEE — delay=42,000 ATK=15 DEF=10 SPD=10 SPC=10 HP=8 (worker 3)
#   shiny! EEVEE — delay=13,712 ATK=14 DEF=10 SPD=10 SPC=10 HP=0 (worker 1)
#   ...
#   found 8 shiny delay(s):
#     delay=42,000  EEVEE  ATK=15 ... HP=8  <<< best
#     ...
#   best: delay 42,000 — ATK=15, HP=8
#   use:  shiny-hunt run --start-delay 42000 ...
```

Once you know the best delay, use `--start-delay` to jump straight to it:

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --start-delay 42000 --headless
# Hits the shiny on the first attempt.
```

If the run exhausts the entire delay window without finding a shiny, that
state/macro pair cannot produce one — re-record the macro or create a new
checkpoint.

Other useful flags:

| Flag | Description |
|------|-------------|
| `--start-delay N` | Start at a specific frame delay (e.g. from a previous `--continue-after-shiny` run) |
| `--continue-after-shiny` | Scan the full window; report all shinies with ranked DV summary |
| `--seed N` | Deterministic master RNG seed (default: `time_ns()`) |
| `--max-attempts N` | Hard cap on resets (default: 100,000) |
| `--workers N` | Parallel worker count (default: cpu_count - 1; use 1 for single-threaded) |
| `--delay-window N` | Number of no-repeat frame delays to search (default: 65,536) |
| `--window` | Show a PyBoy window instead of running headless |
| `--out DIR` | Output directory for `.state` + `.trace.json` (default: `shinies/`) |

### 5. Replay a found shiny

The trace pins ROM SHA-1, state SHA-1, master seed, and attempt index. With
the same ROM, state, and macro, the run is deterministic:

```bash
shiny-hunt replay \
  --rom roms/red.gb \
  --macro macros/red_us_eevee.events.json \
  --trace shinies/eevee_us_000042.trace.json
```

### 6. Resume a found shiny

```bash
shiny-hunt resume --rom roms/red.gb --state shinies/eevee_us_004200.state
# Opens PyBoy windowed. Save in-game, check stats, keep playing.
```

## Project layout

```
src/shiny_hunter/
  cli.py             entry point (run | bootstrap | verify | replay | record | list-games)
  hunter.py          main reset loop + replay
  emulator.py        PyBoy 2.x wrapper (banked SRAM dump, save/load state from bytes)
  recorder.py        windowed-mode joypad polling -> event-log macro
  dv.py              decode_dvs(), is_shiny()  — pure
  pokemon.py         Gen 1 internal species index -> name (all 151)
  macro.py           YAML step macros + JSON event-log macros
  config.py          GameConfig + ROM-hash registry
  polling.py         early-exit species polling (run_until_species)
  workers.py         parallel hunt workers (multiprocessing)
  delays.py          frame-delay scheduling (seed_offset)
  trace.py           per-attempt JSON traces (schema v2)
  progress.py        rich Live counter
  games/             per-(game, region) configs (red_us, red_jp, blue_us, ...)
  macros/            per-(game, region) save macros (.yaml)
```

## Caveats

- **JP RAM offsets are best-effort.** `red_jp.py`, `blue_jp.py`, `green_jp.py`,
  and `yellow_jp.py` ship with addresses derived from pret/pokered's JP build
  target. Verify against the disassembly's symbol file before running long
  sessions, or read the value at the supposed `party_dv_addr` and confirm it
  changes across attempts.
- **Macro tuning.** If `verify` reports `species=unknown`, the macro stopped
  too early — re-record with more frames after the last button press.
  For gift pokemons, it is usually safe to stop the macro after you have either
  nicknamed or said NO to giving the Pokemon a nickname.
- **Checkpoint placement.** The save-state must be captured *before* the DV
  roll. The "YES" prompt to picking a gift Pokemon is well before.
  If a checkpoint mistakenly sits past the roll, every attempt returns the same
  DVs — `verify` (run twice with different seeds) catches this immediately.
- **Output portability.** The `.state` written when a shiny is found is a
  PyBoy-specific save-state. Use `shiny-hunt resume` to load it, save
  in-game, exit Pyboy then export the `.ram` file for use on other emulators
  or real hardware via flashcart.

## License

MIT.
