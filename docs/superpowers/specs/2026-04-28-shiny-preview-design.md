# Shiny Preview via Crystal Screenshot

**Date**: 2026-04-28
**Status**: Design approved

## Goal

When the hunter finds a shiny in Gen 1, let the user see what it looks like in color by injecting it into Pokemon Crystal and capturing a screenshot of the party summary screen. This is a post-hunt CLI command (`shiny-hunt preview`) that takes a trace JSON and produces a PNG.

## Approach

**RAM-based injection**: replay the Gen 1 attempt to read the full party struct from RAM, convert it faithfully using Time Capsule rules, then write the converted pokemon directly into Crystal's WRAM via PyBoy's memory API. No SRAM patching or checksum calculation needed.

## Flow

```
trace.json + Gen 1 ROM + macro
        │
        ▼
  Replay Gen 1 attempt (headless)
        │
        ▼
  Read full party slot 0 from Gen 1 RAM → Gen1Pokemon
        │
        ▼
  Convert via Time Capsule rules → Gen2Pokemon
        │
        ▼
  Boot Crystal in PyBoy (headless), load template .state
        │
        ▼
  Write Gen2Pokemon into Crystal WRAM at party slot 2
        │
        ▼
  Run macro: START → POKEMON → slot 2 → STATS
        │
        ▼
  Screenshot via screen.ndarray → Pillow → PNG
```

## New Modules

### `gen1_party.py` — Gen 1 Party Data Reader

Reads the full 44-byte party struct for slot 0 from RAM after replaying the shiny attempt.

**`Gen1Pokemon` dataclass fields:**
- `species` (1 byte) — Gen 1 internal ID
- `current_hp` (2 bytes, big-endian)
- `level` (1 byte) — box level at offset 0x03
- `status` (1 byte)
- `type1`, `type2` (1 byte each)
- `catch_rate` (1 byte) — becomes held item in Gen 2
- `moves` (4 bytes)
- `ot_id` (2 bytes, big-endian)
- `experience` (3 bytes, big-endian)
- `stat_exp` (5 x 2 bytes: HP, ATK, DEF, SPD, SPC)
- `dvs` (2 bytes: [ATK|DEF][SPD|SPC])
- `pp` (4 bytes, including PP Up bits)
- `party_level` (1 byte) — recalculated level at offset 0x21
- `max_hp` (2 bytes)
- `attack`, `defense`, `speed`, `special` (2 bytes each)
- `ot_name` (11 bytes, 0x50-terminated)
- `nickname` (11 bytes, 0x50-terminated)

**Address derivation from existing GameConfig:**
```
party_count_addr  = party_species_addr - 1
party_struct_base = party_species_addr + 7
ot_names_base     = party_struct_base + (6 * 44)    = +264
nicknames_base    = ot_names_base + (6 * 11)         = +66
```

**Public API:**
```python
def read_party_slot(emu: Emulator, cfg: GameConfig, slot: int = 0) -> Gen1Pokemon
```

### `gen2_convert.py` — Time Capsule Conversion

Converts a `Gen1Pokemon` to a `Gen2Pokemon` using the exact rules from the Time Capsule trade in `pret/pokecrystal engine/link/link.asm`.

**`Gen2Pokemon` dataclass fields** (48-byte party struct):
- `species` (1 byte) — Pokedex number
- `held_item` (1 byte) — converted from catch rate
- `moves` (4 bytes)
- `ot_id` (2 bytes)
- `experience` (3 bytes)
- `stat_exp` (5 x 2 bytes)
- `dvs` (2 bytes)
- `pp` (4 bytes)
- `friendship` (1 byte) — always 70 (0x46)
- `pokerus` (1 byte) — always 0
- `caught_data` (2 bytes) — always 0x0000
- `level` (1 byte)
- `status` (1 byte)
- `unused` (1 byte) — 0x00
- `current_hp` (2 bytes)
- `max_hp` (2 bytes)
- `attack` (2 bytes)
- `defense` (2 bytes)
- `speed` (2 bytes)
- `sp_attack` (2 bytes)
- `sp_defense` (2 bytes)
- `ot_name` (11 bytes)
- `nickname` (11 bytes)

**Conversion rules:**

| Field | Rule |
|---|---|
| Species | Gen 1 internal ID → Pokedex number via `GEN1_TO_POKEDEX` lookup table |
| Held item | Catch rate, remapped through `CATCH_RATE_ITEMS` table |
| Moves, OT ID, Experience, Stat Exp, DVs, PP | Direct copy |
| Friendship | 70 (0x46) |
| Pokerus | 0 |
| Caught data | 0x0000 |
| Level | Direct copy |
| Status, Current HP | Direct copy |
| HP, ATK, DEF, SPD | Recalculated using Gen 2 stat formulas + Gen 2 base stats |
| Sp.Atk, Sp.Def | Computed from Special DV + Special stat exp + Gen 2 base stats |

**Included data tables:**
- `GEN1_TO_POKEDEX`: dict mapping Gen 1 internal index → Pokedex number (151 entries, from `gen1_order.asm`)
- `CATCH_RATE_ITEMS`: dict mapping specific catch rate values → Gen 2 item IDs (12 entries, from `catch_rate_items.asm`)
- `GEN2_BASE_STATS`: dict mapping Pokedex number → (HP, ATK, DEF, SPD, SP_ATK, SP_DEF) for the original 151

**Gen 2 stat formula** (integer math, same as Gen 1 except Special splits):
```
stat_exp_bonus = floor(sqrt(stat_exp)) // 4
stat = ((base + DV) * 2 + stat_exp_bonus) * level // 100 + 5
HP   = ((base + DV) * 2 + stat_exp_bonus) * level // 100 + level + 10
```

**Public API:**
```python
def convert(mon: Gen1Pokemon) -> Gen2Pokemon
```

### `crystal.py` — Crystal WRAM Addresses + Party Injection

Crystal WRAM party addresses (English Crystal, from `pret/pokecrystal ram/wram.asm`):
```
wPartyCount     = TBD (verify from pokecrystal disassembly)
wPartySpecies   = wPartyCount + 1
wPartyMon1      = wPartySpecies + 7
wPartyMon2      = wPartyMon1 + 48
wPartyMonOT     = wPartyMon1 + (6 * 48)
wPartyMonNick   = wPartyMonOT + (6 * 11)
```

These need verification against the pokecrystal disassembly during implementation.

**Public API:**
```python
def inject_party_slot(
    emu: Emulator,
    mon: Gen2Pokemon,
    slot: int = 1,  # 0-indexed; slot 1 = second pokemon
) -> None
```

This function:
1. Reads current party count, sets it to max(count, slot + 1)
2. Writes species into the species list at `slot`, maintains 0xFF terminator
3. Writes the 48-byte struct at the correct offset
4. Writes OT name and nickname at their block offsets

### `preview.py` — Orchestrator

Ties together the full pipeline.

**Public API:**
```python
def generate_preview(
    *,
    trace_path: Path,
    gen1_rom: Path,
    macro_path: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_png: Path,
) -> Path
```

Steps:
1. Load trace JSON, resolve Gen 1 GameConfig from ROM SHA-1
2. Replay the Gen 1 attempt headlessly using `replay_attempt` logic, but extended to read the full party struct via `gen1_party.read_party_slot()`
3. Convert via `gen2_convert.convert()`
4. Boot Crystal in headless PyBoy, load the template `.state`
5. Inject the converted pokemon at party slot 2 via `crystal.inject_party_slot()`
6. Run the Crystal macro (navigates to slot 2 summary screen)
7. Grab `screen.ndarray`, save as PNG via Pillow
8. Return the output path

### `emulator.py` — New Methods

Add `write_byte` and `write_bytes` to the existing Emulator class:

```python
def write_byte(self, addr: int, value: int) -> None:
    self._pyboy.memory[addr] = value

def write_bytes(self, addr: int, data: bytes) -> None:
    for i, b in enumerate(data):
        self._pyboy.memory[addr + i] = b
```

### CLI Addition (`cli.py`)

New command:

```
shiny-hunt preview \
  --trace <trace.json> \
  --rom <gen1.gb> \
  --macro <gen1_macro.yaml> \
  --crystal-rom <crystal.gbc> \
  --crystal-state <crystal_template.state> \
  --crystal-macro <crystal_preview.events.json> \
  --out <output.png>       # optional, defaults to <trace_stem>.png
```

All flags except `--out` are required.

### Crystal Macro

A macro recorded once using `shiny-hunt record` against the Crystal ROM + template state. The sequence from the template state (player standing in-game):

**START → POKEMON → ↓ (move to slot 2) → A (select) → STATS (or SUMMARY)**

This gets to the party summary screen showing the shiny sprite in color. After a settle period (enough frames for the screen to fully render), the screenshot is captured.

## Template State Bootstrap

The user prepares the Crystal template state once:

1. Boot Crystal via `shiny-hunt bootstrap --rom crystal.gbc --out states/crystal_template.state`
2. Play until you have 1 pokemon in the party and are standing somewhere convenient
3. Close the window (state is saved)

Alternatively, the user can use any existing Crystal save file, import it by booting Crystal with that save, and saving a PyBoy state.

## What's NOT In Scope

- Automated template state creation (manual bootstrap)
- Japanese Crystal support (English only)
- Inline preview during hunt (post-hunt only)
- Terminal inline image display (PNG file only)
- Batch preview of multiple traces (run the command multiple times)

## Testing Strategy

- **`gen1_party.py`**: Unit tests with known RAM bytes → verify parsed fields
- **`gen2_convert.py`**: Unit tests with known Gen 1 data → verify converted Gen 2 fields match expected Time Capsule output. Test edge cases: catch rate remapping table entries, MissingNo. species (should error), stat calculation spot-checks
- **`crystal.py`**: Unit tests that write to a mock emulator and verify the correct addresses/bytes
- **`preview.py`**: Integration test requiring both ROMs (mark `needs_rom`), end-to-end trace → PNG
- Data tables (`GEN1_TO_POKEDEX`, `CATCH_RATE_ITEMS`, `GEN2_BASE_STATS`): Spot-check a handful of entries against known values from Bulbapedia
