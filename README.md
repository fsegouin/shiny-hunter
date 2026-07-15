# shiny-hunter

![Shiny Charmander in Red](https://github.com/fsegouin/shiny-hunter/blob/c22a92786f2d036054ac260f2f59c867ebcd5a7b/demo.gif)

Automatic Gen 1 & 2 shiny hunter for Pokémon Red, Blue, Green (JP), Yellow,
Gold, Silver, and Crystal (US and JP).
Runs PyBoy headlessly, soft-resets the game thousands of times per minute, and
saves a `.state` file the moment a Pokémon's DVs satisfy the shiny condition
(the Gen 2 transfer-shiny rule for Gen 1 games; the native shiny rule — the
same DV predicate — for Gen 2 games). Works for any Pokémon — starters, gifts,
wild encounters — as long as
you can create a save-state checkpoint before the DV roll and a macro that
triggers it. On a decent computer, this process can take between 30 seconds to 10 minutes,
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
window without finding a shiny, see the troubleshooting note below.

This is exactly the same physical phenomenon that makes manual
soft-resetting work on real hardware: a human can't press A on the same
CPU cycle twice, so `rDIV` is different at each press. We just simulate
that variability on purpose.

### Is Gen 2 RNG the same?

For a Gen 1 hunt, **Gen 2's RNG is never invoked**. We're not catching
the Pokémon in Gen 2 — we're catching it in Gen 1 and transferring via
the Time Capsule. Shininess in Gen 2 is checked as a **static predicate
over the existing DVs**: Def/Spd/Spc DV all equal 10, Atk DV is in
`{2, 3, 6, 7, 10, 11, 14, 15}`. No roll happens at transfer time.

Native Gen 2 hunting (e.g., shiny hunting Totodile in Crystal) **is also
supported**, and it works because Gold/Silver/Crystal use a very similar
mechanism: an `hRandomAdd`/`hRandomSub` pair mixed with `rDIV` on every
call. It's the same fundamental design, with minor differences in mixing
constants and in *where* the RNG is consulted during encounter
generation. The same "inject frame jitter before the decisive A-press"
trick applies unchanged, and the shiny predicate is identical — in Gen 2
it's simply the game's own rule rather than a transfer condition, so the
shiny is visible in-game the moment you find it (no Time Capsule needed).

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
python -m venv .venv
source .venv/bin/activate # bash/zsh
source .venv/bin/activate.fish # fish
```

## Install

```bash
pip install -e .[dev]
```

Requires Python ≥ 3.11. PyBoy is pulled in as a dependency from a fork
([fsegouin/PyBoy@shiny-hunter-deps](https://github.com/fsegouin/PyBoy/tree/shiny-hunter-deps)),
an integration branch merging `fix/mbc30-support` (MBC30 support for JP Crystal
plus a serial transfer-completion fix) and `feat/rtc-lock` (`rtc_lock` —
required for deterministic Gen 2 hunts, see Caveats). Both are pending upstream
PRs.

## Bring your own ROM

Place a legally-dumped ROM in `roms/`. Supported (game, region, SHA-1):

```bash
shiny-hunt list-games
```

If your ROM's SHA-1 isn't registered, the bot refuses to run. To add a new
language/region, drop a new file in `src/shiny_hunter/games/` mirroring
`red_us.py` and re-install.

## Onboarding flow

Five steps: checkpoint, record, verify, re-park (optional), hunt. Works for any Pokémon whose DV roll
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

Pass `--from-state` to start from an existing save-state instead of power-on —
handy for nudging a checkpoint a little closer to the DV roll by hand (for the
automated version, see step 4):

```bash
shiny-hunt bootstrap \
  --rom roms/red.gb \
  --from-state states/red_us_eevee.state \
  --out states/red_us_eevee2.state
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

### 4. Re-park the checkpoint (optional, but ~10–20x faster)

Every frame between your checkpoint and the DV roll is re-emulated on
*every* attempt — and the roll often happens much later than you'd guess
(Crystal rolls the starter ~800 frames *after* the YES confirm, mid-dialog
inside GivePokemon; you can't practically park there by hand). `repark`
finds the roll by replaying your macro, saves a new state just before the
decisive press, writes a short rebased macro, and verifies that frame
jitter still varies the DVs from the new park point:

```bash
shiny-hunt repark \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --out-state states/red_us_eevee_parked.state \
  --out-macro macros/red_us_eevee_parked.events.json
# species readable at frame 823 of the original macro
# trying park point at frame 819 (before press at 820)...
# park point valid — probe DVs vary
# per-attempt emulation: ~823 -> ~4 frames
```

Measured on a Crystal (JP) starter hunt this took the total rate from
~220 to ~2,200 attempts/s — a full 65,536-delay sweep in ~30 seconds.
Note the parked state is a **new checkpoint**: shiny delays found from the
old one don't carry over (the delay window is per-checkpoint).

### 5. Hunt

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee_parked.state \
  --macro macros/red_us_eevee_parked.events.json \
  --headless
# Scans frame delays sequentially across all cores.
# Stops at the first shiny and saves (filename embeds a short hash of the
# checkpoint state, so hunts from different checkpoints never collide):
#   shinies/eevee_us_1a2b3c_042000.state       — resume with `shiny-hunt resume`
#   shinies/eevee_us_1a2b3c_042000.trace.json  — for `shiny-hunt replay`
```

Use `--continue-after-shiny` to scan the entire delay window and find
every shiny delay. Each shiny is reported live as it's found, and a
ranked summary (by ATK DV, highest first) is printed at the end:

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee_parked.state \
  --macro macros/red_us_eevee_parked.events.json \
  --continue-after-shiny --headless
# Example output:
#   shiny! EEVEE — delay=42,000 ATK=15 DEF=10 SPD=10 SPC=10 HP=8 (worker 3)
#   shiny! EEVEE — delay=13,712 ATK=14 DEF=10 SPD=10 SPC=10 HP=0 (worker 1)
#   ...
#   found 8 shiny delay(s):
#     delay=42,000  EEVEE  ATK=15 ... HP=8  <<< best
#     ...
#   best: delay 42,000 — ATK=15, HP=8
```

All shinies are saved as they're found, so you can use
`shiny-hunt resume --state shinies/<best>.state` to load the one you want.

If the run exhausts the entire delay window without finding a shiny,
first check the basics: run `shiny-hunt verify` twice with different
`--seed` values and confirm the DVs change between runs. If they don't,
the checkpoint is past the DV roll — create a new one. If `verify`
shows `species=unknown`, the macro stopped too early — re-record it.

If the checkpoint and macro are sound, try expanding the search with
`--delay-window 131072` (or higher). The default window of 65,536
frames gives ~8 expected shinies at 1/8192 odds, but the mapping from
frame delay to DVs isn't perfectly uniform — some windows have unlucky
clustering. A larger window explores genuinely new delays and can
surface shinies the smaller window missed.

Other useful flags:

| Flag | Description |
|------|-------------|
| `--continue-after-shiny` | Scan the full window; report all shinies with ranked DV summary |
| `--seed N` | Deterministic master RNG seed (default: `time_ns()`) |
| `--max-attempts N` | Hard cap on resets (default: 100,000) |
| `--workers N` | Parallel worker count (default: cpu_count - 1; use 1 for single-threaded) |
| `--delay-window N` | Number of no-repeat frame delays to search (default: 65,536) |
| `--window` | Show a PyBoy window instead of running headless |
| `--out DIR` | Output directory for `.state` + `.trace.json` (default: `shinies/`) |
| `--monitor` | Show a live tkinter grid of all worker screens with a DV overlay |
| `--record FILE` | Record the monitor grid to an animated GIF (implies `--monitor`). Stops 2 s after the first shiny |
| `--mode starter\|static` | Hunt mode: `starter` reads party DVs, `static` reads enemy battle DVs (default: `starter`) |
| `--crystal-rom FILE` | Crystal ROM (`.gbc`) for auto-generating shiny preview PNGs (default: `roms/crystal.gbc`) |
| `--crystal-state FILE` | Crystal template save-state for preview generation (default: `states/crystal_template.state`) |
| `--crystal-macro FILE` | Crystal macro for preview generation (default: `macros/crystal_preview.events.json`) |

### 6. Monitor the hunt

Pass `--monitor` to open a live tkinter window that tiles every worker's
screen in a grid. Each tile shows the Game Boy framebuffer overlaid with
the current species, DVs, and Crystal's shiny sparkle icon when a shiny is
found. Requires tkinter (`sudo pacman -S tk` on Arch, `sudo apt install
python3-tk` on Debian/Ubuntu).

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --monitor
```

Add `--record shinies/hunt.gif` to save the session as an animated GIF
(implies `--monitor`). Recording stops automatically 2 seconds after the
first shiny is found.

```bash
shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_eevee.state \
  --macro macros/red_us_eevee.events.json \
  --record shinies/hunt.gif
```

### 7. Replay a found shiny

The trace pins ROM SHA-1, state SHA-1, master seed, and attempt index. With
the same ROM, state, and macro, the run is deterministic:

```bash
shiny-hunt replay \
  --rom roms/red.gb \
  --macro macros/red_us_eevee.events.json \
  --trace shinies/eevee_us_1a2b3c_042000.trace.json
```

### 8. Resume a found shiny

```bash
shiny-hunt resume --rom roms/red.gb --state shinies/eevee_us_1a2b3c_042000.state
# Opens PyBoy windowed. Save in-game, check stats, keep playing.
```

### 9. Generate a Crystal shiny preview

If you have a Pokémon Crystal ROM, you can generate a screenshot showing
what the shiny looks like in Gen 2 — complete with the Crystal sprite and
colour palette. The `preview` command injects the Gen 1 DVs into a Crystal
save-state, runs a macro to reach the stats screen, and captures the
framebuffer as a PNG.

Place the Crystal assets at their default locations and the flags become
optional:

| Asset | Default path |
|-------|-------------|
| Crystal ROM | `roms/crystal.gbc` |
| Template save-state | `states/crystal_template.state` |
| Stats-screen macro | `macros/crystal_preview.events.json` |

```bash
shiny-hunt preview \
  --rom roms/red.gb \
  --state shinies/eevee_us_1a2b3c_042000.state
# Writes shinies/eevee_us_1a2b3c_042000.png
```

When Crystal assets are present at the default paths, `shiny-hunt run`
automatically generates a preview PNG alongside each shiny find — no
extra flags needed. You can override any path with `--crystal-rom`,
`--crystal-state`, or `--crystal-macro` if your files live elsewhere.

### Hunting static encounters

For Pokémon whose DVs are rolled in battle (legendaries, Snorlax, etc.)
rather than added to the party directly, use `--mode static`. This reads
the enemy battle DVs instead of the party slot:

```bash
shiny-hunt verify \
  --rom roms/red.gb \
  --state states/red_us_mewtwo.state \
  --macro macros/red_us_mewtwo.events.json \
  --mode static

shiny-hunt run \
  --rom roms/red.gb \
  --state states/red_us_mewtwo.state \
  --macro macros/red_us_mewtwo.events.json \
  --mode static --headless
```

## Project layout

```
src/shiny_hunter/
  cli.py             entry point (run | bootstrap | verify | replay | record | repark | preview | resume | list-games)
  hunter.py          main reset loop + replay
  emulator.py        PyBoy 2.x wrapper (banked SRAM dump, save/load state from bytes)
  recorder.py        windowed-mode joypad polling -> event-log macro
  dv.py              decode_dvs(), is_shiny()  — pure
  pokemon.py         species index -> name (Gen 1 internal index / Gen 2 dex number)
  macro.py           YAML step macros + JSON event-log macros
  config.py          GameConfig + ROM-hash registry
  polling.py         early-exit species polling (run_until_species)
  repark.py          move a checkpoint next to the DV roll + rebase its macro
  workers.py         parallel hunt workers (multiprocessing)
  delays.py          frame-delay scheduling (seed_offset)
  trace.py           per-attempt JSON traces (schema v2)
  progress.py        rich Live counter
  monitor.py         live tkinter grid with DV overlay + GIF recording
  crystal.py         Crystal ROM DV injection for preview screenshots
  preview.py         Crystal shiny preview PNG generation
  gbfont.py          Pokémon Red bitmap font renderer for the monitor overlay
  gen1_party.py      Gen 1 party structure helpers
  gen2_party.py      Gen 2 party structure helpers (raw 48-byte struct reads)
  gen2_convert.py    Gen 1 → Gen 2 data conversion
  gen2_data.py       Gen 2 Pokémon data tables (species, names, base stats)
  games/             per-(game, region) configs (red_us, gold_us, crystal_jp, ...)
  macros/            per-(game, region) starter + save macros (.yaml)
  data/              bundled assets (Pokémon Red font, shiny icon)
```

## Caveats

- **Gen 1 JP RAM offsets are best-effort.** `red_jp.py`, `blue_jp.py`,
  `green_jp.py`, and `yellow_jp.py` ship with addresses derived from
  pret/pokered's JP build target. Verify against the disassembly's symbol file
  before running long sessions, or read the value at the supposed
  `party_dv_addr` and confirm it changes across attempts.
- **Gen 2 addresses are verified.** US Gold/Silver/Crystal addresses come from
  pret's build-verified symbol files; JP addresses were cross-checked against
  the retail dumps by opcode-literal frequency analysis (see the docstrings in
  `games/gold_jp.py` and `games/crystal_jp.py`). Only the JP Rev 1
  Gold/Silver dumps are registered — Rev 0's WRAM layout is unverified.
- **Gen 2 shinies are native.** No Time Capsule transfer is needed: the DV
  predicate is the game's own shiny rule, so the found Pokémon is shiny
  in its own game.
- **Gen 2 needs a frozen RTC for determinism.** Gold/Silver/Crystal poll the
  MBC3 real-time clock constantly, and stock PyBoy derives the RTC from the
  host wall clock — so the same (state, delay) attempt can roll different DVs
  depending on when you run it. The pinned PyBoy fork adds `rtc_lock`, which
  this tool always enables: the in-game clock freezes, and every delay→DV
  mapping becomes reproducible forever.
- **Delay numbers are per-checkpoint.** A shiny's delay is only meaningful
  relative to the exact `.state` it was found from — that's why output
  filenames embed a short hash of the bootstrap state. A new checkpoint (even
  one frame later) gives a completely fresh 65,536-roll window, which is also
  the way to keep hunting for a better spread (ATK 15 / HP 8 is the ceiling).
- **Slow hunts?** Run `shiny-hunt repark` (onboarding step 4) — it moves the
  checkpoint to within a few frames of the DV roll and typically speeds
  attempts up ~10–20x.
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
