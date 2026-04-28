# Shiny Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `shiny-hunt preview` CLI command that replays a Gen 1 shiny trace, converts the pokemon to Gen 2 format via Time Capsule rules, injects it into Crystal's WRAM, and screenshots the party summary screen as a PNG.

**Architecture:** Five new modules (`gen1_party`, `gen2_convert`, `gen2_data`, `crystal`, `preview`) plus additions to `emulator.py` and `cli.py`. Pure data modules (gen1_party, gen2_convert, gen2_data) have no emulator dependency and are fully unit-testable with fake data. The crystal module writes to RAM via the emulator. The preview module orchestrates the full pipeline.

**Tech Stack:** Python 3.11+, PyBoy 2.x, Pillow (already a dependency), pytest

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `src/shiny_hunter/emulator.py` | Modify | Add `write_byte`, `write_bytes` methods |
| `src/shiny_hunter/gen1_party.py` | Create | `Gen1Pokemon` dataclass + `read_party_slot()` |
| `src/shiny_hunter/gen2_data.py` | Create | Static data tables: `GEN1_TO_POKEDEX`, `CATCH_RATE_ITEMS`, `GEN2_BASE_STATS` |
| `src/shiny_hunter/gen2_convert.py` | Create | `Gen2Pokemon` dataclass + `convert()` function |
| `src/shiny_hunter/crystal.py` | Create | Crystal WRAM addresses + `inject_party_slot()` |
| `src/shiny_hunter/preview.py` | Create | `generate_preview()` orchestrator |
| `src/shiny_hunter/cli.py` | Modify | Add `preview` command |
| `tests/test_gen1_party.py` | Create | Unit tests for Gen1Pokemon parsing |
| `tests/test_gen2_convert.py` | Create | Unit tests for Time Capsule conversion |
| `tests/test_gen2_data.py` | Create | Spot-check data tables |
| `tests/test_crystal.py` | Create | Unit tests for WRAM injection |
| `tests/test_preview.py` | Create | Integration test (needs_rom) |

---

### Task 1: Add `write_byte` and `write_bytes` to Emulator

**Files:**
- Modify: `src/shiny_hunter/emulator.py:72-78`
- Test: `tests/test_polling.py` (extend `_FakeEmulator`)

- [ ] **Step 1: Add `write_byte` and `write_bytes` to `emulator.py`**

In `src/shiny_hunter/emulator.py`, add after the `read_bytes` method (after line 78):

```python
def write_byte(self, addr: int, value: int) -> None:
    self._pyboy.memory[addr] = value

def write_bytes(self, addr: int, data: bytes) -> None:
    for i, b in enumerate(data):
        self._pyboy.memory[addr + i] = b
```

- [ ] **Step 2: Run existing tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/shiny_hunter/emulator.py
git commit -m "Add write_byte and write_bytes to Emulator"
```

---

### Task 2: Gen 1 Party Data Reader (`gen1_party.py`)

**Files:**
- Create: `src/shiny_hunter/gen1_party.py`
- Create: `tests/test_gen1_party.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gen1_party.py`:

```python
"""Tests for Gen 1 party data reader."""
from __future__ import annotations

from shiny_hunter.gen1_party import Gen1Pokemon, read_party_slot


SPECIES_ADDR = 0xD164
DV_ADDR = 0xD186
PARTY_STRUCT_BASE = SPECIES_ADDR + 7  # 0xD16B
OT_NAMES_BASE = PARTY_STRUCT_BASE + (6 * 44)  # 0xD273
NICKNAMES_BASE = OT_NAMES_BASE + (6 * 11)  # 0xD2B5


def _make_gen1_struct() -> bytes:
    """Build a known 44-byte Gen 1 party struct for Bulbasaur."""
    data = bytearray(44)
    data[0x00] = 0x99        # species: Bulbasaur internal ID
    data[0x01] = 0x00        # current HP high
    data[0x02] = 0x14        # current HP low = 20
    data[0x03] = 5           # level (box)
    data[0x04] = 0           # status
    data[0x05] = 0x16        # type1 (grass)
    data[0x06] = 0x03        # type2 (poison)
    data[0x07] = 45          # catch rate
    data[0x08] = 0x21        # move1: Tackle (0x21 = 33)
    data[0x09] = 0x2D        # move2: Growl (0x2D = 45)
    data[0x0A] = 0x00        # move3: none
    data[0x0B] = 0x00        # move4: none
    data[0x0C] = 0x00        # OT ID high
    data[0x0D] = 0x01        # OT ID low = 1
    data[0x0E] = 0x00        # exp high
    data[0x0F] = 0x00        # exp mid
    data[0x10] = 0x7D        # exp low = 125
    # stat exp: all zeros (5 x 2 bytes at 0x11-0x1A)
    data[0x1B] = 0xAA        # DVs: ATK=10, DEF=10
    data[0x1C] = 0xAA        # DVs: SPD=10, SPC=10
    data[0x1D] = 35          # move1 PP
    data[0x1E] = 40          # move2 PP
    data[0x1F] = 0           # move3 PP
    data[0x20] = 0           # move4 PP
    # party-only fields (0x21-0x2B)
    data[0x21] = 5           # party level
    data[0x22] = 0x00        # max HP high
    data[0x23] = 0x14        # max HP low = 20
    data[0x24] = 0x00        # attack high
    data[0x25] = 0x0B        # attack low = 11
    data[0x26] = 0x00        # defense high
    data[0x27] = 0x0B        # defense low = 11
    data[0x28] = 0x00        # speed high
    data[0x29] = 0x0B        # speed low = 11
    data[0x2A] = 0x00        # special high
    data[0x2B] = 0x0C        # special low = 12
    return bytes(data)


def _bulbasaur_ot_name() -> bytes:
    """OT name 'RED' in Gen 1 text encoding + 0x50 terminator, padded to 11."""
    name = bytearray(11)
    name[0] = 0x91  # R
    name[1] = 0x84  # E
    name[2] = 0x83  # D
    name[3] = 0x50  # terminator
    for i in range(4, 11):
        name[i] = 0x00
    return bytes(name)


def _bulbasaur_nickname() -> bytes:
    """Nickname 'BULBASAUR' in Gen 1 text encoding + 0x50 terminator."""
    name = bytearray(11)
    chars = [0x81, 0x94, 0x8B, 0x81, 0x80, 0x92, 0x80, 0x94, 0x91]  # BULBASAUR
    for i, c in enumerate(chars):
        name[i] = c
    name[9] = 0x50  # terminator
    name[10] = 0x00
    return bytes(name)


class _FakeEmu:
    def __init__(self, struct_bytes: bytes, ot_name: bytes, nickname: bytes):
        self._mem: dict[int, int] = {}
        # Write struct bytes at party struct base (slot 0)
        for i, b in enumerate(struct_bytes):
            self._mem[PARTY_STRUCT_BASE + i] = b
        # Write OT name at OT names base (slot 0)
        for i, b in enumerate(ot_name):
            self._mem[OT_NAMES_BASE + i] = b
        # Write nickname at nicknames base (slot 0)
        for i, b in enumerate(nickname):
            self._mem[NICKNAMES_BASE + i] = b

    def read_byte(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def read_bytes(self, addr: int, length: int) -> bytes:
        return bytes(self._mem.get(addr + i, 0) for i in range(length))


class _FakeConfig:
    party_species_addr = SPECIES_ADDR
    party_dv_addr = DV_ADDR


def test_read_party_slot_bulbasaur():
    struct_bytes = _make_gen1_struct()
    ot_name = _bulbasaur_ot_name()
    nickname = _bulbasaur_nickname()
    emu = _FakeEmu(struct_bytes, ot_name, nickname)
    cfg = _FakeConfig()

    mon = read_party_slot(emu, cfg, slot=0)

    assert mon.species == 0x99
    assert mon.current_hp == 20
    assert mon.level == 5
    assert mon.status == 0
    assert mon.type1 == 0x16
    assert mon.type2 == 0x03
    assert mon.catch_rate == 45
    assert mon.moves == (0x21, 0x2D, 0x00, 0x00)
    assert mon.ot_id == 1
    assert mon.experience == 125
    assert mon.stat_exp == (0, 0, 0, 0, 0)
    assert mon.dvs == (0xAA, 0xAA)
    assert mon.pp == (35, 40, 0, 0)
    assert mon.party_level == 5
    assert mon.max_hp == 20
    assert mon.attack == 11
    assert mon.defense == 11
    assert mon.speed == 11
    assert mon.special == 12
    assert mon.ot_name == ot_name
    assert mon.nickname == nickname


def test_read_party_slot_1():
    """Reading slot 1 uses the correct offsets."""
    struct_bytes = _make_gen1_struct()
    ot_name = _bulbasaur_ot_name()
    nickname = _bulbasaur_nickname()

    mem: dict[int, int] = {}
    slot1_struct = PARTY_STRUCT_BASE + 44
    slot1_ot = OT_NAMES_BASE + 11
    slot1_nick = NICKNAMES_BASE + 11
    for i, b in enumerate(struct_bytes):
        mem[slot1_struct + i] = b
    for i, b in enumerate(ot_name):
        mem[slot1_ot + i] = b
    for i, b in enumerate(nickname):
        mem[slot1_nick + i] = b

    class _SlotEmu:
        def read_byte(self, addr: int) -> int:
            return mem.get(addr, 0)
        def read_bytes(self, addr: int, length: int) -> bytes:
            return bytes(mem.get(addr + i, 0) for i in range(length))

    cfg = _FakeConfig()
    mon = read_party_slot(_SlotEmu(), cfg, slot=1)
    assert mon.species == 0x99
    assert mon.current_hp == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gen1_party.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shiny_hunter.gen1_party'`

- [ ] **Step 3: Write implementation**

Create `src/shiny_hunter/gen1_party.py`:

```python
"""Gen 1 party data reader — reads the full 44-byte party struct from RAM."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gen1Pokemon:
    species: int
    current_hp: int
    level: int
    status: int
    type1: int
    type2: int
    catch_rate: int
    moves: tuple[int, int, int, int]
    ot_id: int
    experience: int
    stat_exp: tuple[int, int, int, int, int]  # HP, ATK, DEF, SPD, SPC
    dvs: tuple[int, int]  # raw bytes: [ATK|DEF], [SPD|SPC]
    pp: tuple[int, int, int, int]
    party_level: int
    max_hp: int
    attack: int
    defense: int
    speed: int
    special: int
    ot_name: bytes  # 11 bytes, 0x50-terminated
    nickname: bytes  # 11 bytes, 0x50-terminated


def _u16(hi: int, lo: int) -> int:
    return (hi << 8) | lo


def _u24(hi: int, mid: int, lo: int) -> int:
    return (hi << 16) | (mid << 8) | lo


def read_party_slot(emu, cfg, slot: int = 0) -> Gen1Pokemon:
    party_struct_base = cfg.party_species_addr + 7
    ot_names_base = party_struct_base + (6 * 44)
    nicknames_base = ot_names_base + (6 * 11)

    struct_addr = party_struct_base + (slot * 44)
    d = emu.read_bytes(struct_addr, 44)

    ot_addr = ot_names_base + (slot * 11)
    ot_name = emu.read_bytes(ot_addr, 11)

    nick_addr = nicknames_base + (slot * 11)
    nickname = emu.read_bytes(nick_addr, 11)

    return Gen1Pokemon(
        species=d[0x00],
        current_hp=_u16(d[0x01], d[0x02]),
        level=d[0x03],
        status=d[0x04],
        type1=d[0x05],
        type2=d[0x06],
        catch_rate=d[0x07],
        moves=(d[0x08], d[0x09], d[0x0A], d[0x0B]),
        ot_id=_u16(d[0x0C], d[0x0D]),
        experience=_u24(d[0x0E], d[0x0F], d[0x10]),
        stat_exp=(
            _u16(d[0x11], d[0x12]),
            _u16(d[0x13], d[0x14]),
            _u16(d[0x15], d[0x16]),
            _u16(d[0x17], d[0x18]),
            _u16(d[0x19], d[0x1A]),
        ),
        dvs=(d[0x1B], d[0x1C]),
        pp=(d[0x1D], d[0x1E], d[0x1F], d[0x20]),
        party_level=d[0x21],
        max_hp=_u16(d[0x22], d[0x23]),
        attack=_u16(d[0x24], d[0x25]),
        defense=_u16(d[0x26], d[0x27]),
        speed=_u16(d[0x28], d[0x29]),
        special=_u16(d[0x2A], d[0x2B]),
        ot_name=bytes(ot_name),
        nickname=bytes(nickname),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gen1_party.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/gen1_party.py tests/test_gen1_party.py
git commit -m "Add Gen 1 party data reader"
```

---

### Task 3: Gen 2 Static Data Tables (`gen2_data.py`)

**Files:**
- Create: `src/shiny_hunter/gen2_data.py`
- Create: `tests/test_gen2_data.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gen2_data.py`:

```python
"""Spot-check Gen 2 data tables against known values."""
from shiny_hunter.gen2_data import GEN1_TO_POKEDEX, CATCH_RATE_ITEMS, GEN2_BASE_STATS


def test_gen1_to_pokedex_bulbasaur():
    assert GEN1_TO_POKEDEX[0x99] == 1


def test_gen1_to_pokedex_charmander():
    assert GEN1_TO_POKEDEX[0xB0] == 4


def test_gen1_to_pokedex_squirtle():
    assert GEN1_TO_POKEDEX[0xB1] == 7


def test_gen1_to_pokedex_pikachu():
    assert GEN1_TO_POKEDEX[0x54] == 25


def test_gen1_to_pokedex_mewtwo():
    assert GEN1_TO_POKEDEX[0x83] == 150


def test_gen1_to_pokedex_mew():
    assert GEN1_TO_POKEDEX[0x15] == 151


def test_gen1_to_pokedex_eevee():
    assert GEN1_TO_POKEDEX[0x66] == 133


def test_gen1_to_pokedex_covers_151():
    pokedex_nums = set(GEN1_TO_POKEDEX.values())
    assert pokedex_nums == set(range(1, 152))


def test_catch_rate_items_berry_mappings():
    assert CATCH_RATE_ITEMS[90] == 0x2D   # BERRY
    assert CATCH_RATE_ITEMS[100] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[120] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[135] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[190] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[195] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[220] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[250] == 0x2D  # BERRY
    assert CATCH_RATE_ITEMS[255] == 0x2D  # BERRY


def test_catch_rate_items_special():
    assert CATCH_RATE_ITEMS[25] == 0xAC   # LEFTOVERS
    assert CATCH_RATE_ITEMS[45] == 0x2E   # BITTER_BERRY
    assert CATCH_RATE_ITEMS[50] == 0x53   # GOLD_BERRY


def test_catch_rate_items_count():
    assert len(CATCH_RATE_ITEMS) == 12


def test_base_stats_bulbasaur():
    hp, atk, def_, spd, sp_atk, sp_def = GEN2_BASE_STATS[1]
    assert (hp, atk, def_, spd, sp_atk, sp_def) == (45, 49, 49, 45, 65, 65)


def test_base_stats_pikachu():
    hp, atk, def_, spd, sp_atk, sp_def = GEN2_BASE_STATS[25]
    assert (hp, atk, def_, spd, sp_atk, sp_def) == (35, 55, 30, 90, 50, 40)


def test_base_stats_mewtwo():
    hp, atk, def_, spd, sp_atk, sp_def = GEN2_BASE_STATS[150]
    assert (hp, atk, def_, spd, sp_atk, sp_def) == (106, 110, 90, 130, 154, 90)


def test_base_stats_covers_151():
    assert set(GEN2_BASE_STATS.keys()) == set(range(1, 152))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gen2_data.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shiny_hunter.gen2_data'`

- [ ] **Step 3: Write implementation**

Create `src/shiny_hunter/gen2_data.py`:

```python
"""Static data tables for Gen 1 → Gen 2 conversion.

All data sourced from pret/pokecrystal disassembly:
  - GEN1_TO_POKEDEX: data/pokemon/gen1_order.asm
  - CATCH_RATE_ITEMS: data/items/catch_rate_items.asm
  - GEN2_BASE_STATS: data/pokemon/base_stats/*.asm
"""
from __future__ import annotations

# Gen 1 internal species index → Pokedex number (151 entries).
GEN1_TO_POKEDEX: dict[int, int] = {
    0x01: 112,  # Rhydon
    0x02: 115,  # Kangaskhan
    0x03: 32,   # Nidoran♂
    0x04: 35,   # Clefairy
    0x05: 21,   # Spearow
    0x06: 100,  # Voltorb
    0x07: 34,   # Nidoking
    0x08: 80,   # Slowbro
    0x09: 2,    # Ivysaur
    0x0A: 103,  # Exeggutor
    0x0B: 108,  # Lickitung
    0x0C: 102,  # Exeggcute
    0x0D: 88,   # Grimer
    0x0E: 94,   # Gengar
    0x0F: 29,   # Nidoran♀
    0x10: 31,   # Nidoqueen
    0x11: 104,  # Cubone
    0x12: 111,  # Rhyhorn
    0x13: 131,  # Lapras
    0x14: 59,   # Arcanine
    0x15: 151,  # Mew
    0x16: 130,  # Gyarados
    0x17: 90,   # Shellder
    0x18: 72,   # Tentacool
    0x19: 92,   # Gastly
    0x1A: 123,  # Scyther
    0x1B: 120,  # Staryu
    0x1C: 9,    # Blastoise
    0x1D: 127,  # Pinsir
    0x1E: 114,  # Tangela
    0x21: 58,   # Growlithe
    0x22: 95,   # Onix
    0x23: 22,   # Fearow
    0x24: 16,   # Pidgey
    0x25: 79,   # Slowpoke
    0x26: 64,   # Kadabra
    0x27: 75,   # Graveler
    0x28: 113,  # Chansey
    0x29: 67,   # Machoke
    0x2A: 122,  # Mr. Mime
    0x2B: 106,  # Hitmonlee
    0x2C: 107,  # Hitmonchan
    0x2D: 24,   # Arbok
    0x2E: 47,   # Parasect
    0x2F: 54,   # Psyduck
    0x30: 96,   # Drowzee
    0x31: 76,   # Golem
    0x33: 126,  # Magmar
    0x35: 125,  # Electabuzz
    0x36: 82,   # Magneton
    0x37: 109,  # Koffing
    0x39: 56,   # Mankey
    0x3A: 86,   # Seel
    0x3B: 50,   # Diglett
    0x3C: 128,  # Tauros
    0x40: 83,   # Farfetch'd
    0x41: 48,   # Venonat
    0x42: 149,  # Dragonite
    0x46: 84,   # Doduo
    0x47: 60,   # Poliwag
    0x48: 124,  # Jynx
    0x49: 146,  # Moltres
    0x4A: 144,  # Articuno
    0x4B: 145,  # Zapdos
    0x4C: 132,  # Ditto
    0x4D: 52,   # Meowth
    0x4E: 98,   # Krabby
    0x52: 37,   # Vulpix
    0x53: 38,   # Ninetales
    0x54: 25,   # Pikachu
    0x55: 26,   # Raichu
    0x58: 147,  # Dratini
    0x59: 148,  # Dragonair
    0x5A: 140,  # Kabuto
    0x5B: 141,  # Kabutops
    0x5C: 116,  # Horsea
    0x5D: 117,  # Seadra
    0x60: 27,   # Sandshrew
    0x61: 28,   # Sandslash
    0x62: 138,  # Omanyte
    0x63: 139,  # Omastar
    0x64: 39,   # Jigglypuff
    0x65: 40,   # Wigglytuff
    0x66: 133,  # Eevee
    0x67: 136,  # Flareon
    0x68: 135,  # Jolteon
    0x69: 134,  # Vaporeon
    0x6A: 66,   # Machop
    0x6B: 41,   # Zubat
    0x6C: 23,   # Ekans
    0x6D: 46,   # Paras
    0x6E: 61,   # Poliwhirl
    0x6F: 62,   # Poliwrath
    0x70: 13,   # Weedle
    0x71: 14,   # Kakuna
    0x72: 15,   # Beedrill
    0x74: 85,   # Dodrio
    0x75: 57,   # Primeape
    0x76: 51,   # Dugtrio
    0x77: 49,   # Venomoth
    0x78: 87,   # Dewgong
    0x7B: 10,   # Caterpie
    0x7C: 11,   # Metapod
    0x7D: 12,   # Butterfree
    0x7E: 68,   # Machamp
    0x80: 55,   # Golduck
    0x81: 97,   # Hypno
    0x82: 42,   # Golbat
    0x83: 150,  # Mewtwo
    0x84: 143,  # Snorlax
    0x85: 129,  # Magikarp
    0x88: 89,   # Muk
    0x8A: 99,   # Kingler
    0x8B: 91,   # Cloyster
    0x8D: 101,  # Electrode
    0x8E: 36,   # Clefable
    0x8F: 110,  # Weezing
    0x90: 53,   # Persian
    0x91: 105,  # Marowak
    0x93: 93,   # Haunter
    0x94: 63,   # Abra
    0x95: 65,   # Alakazam
    0x96: 17,   # Pidgeotto
    0x97: 18,   # Pidgeot
    0x98: 121,  # Starmie
    0x99: 1,    # Bulbasaur
    0x9A: 3,    # Venusaur
    0x9B: 73,   # Tentacruel
    0x9D: 118,  # Goldeen
    0x9E: 119,  # Seaking
    0xA3: 77,   # Ponyta
    0xA4: 78,   # Rapidash
    0xA5: 19,   # Rattata
    0xA6: 20,   # Raticate
    0xA7: 33,   # Nidorino
    0xA8: 30,   # Nidorina
    0xA9: 74,   # Geodude
    0xAA: 137,  # Porygon
    0xAB: 142,  # Aerodactyl
    0xAD: 81,   # Magnemite
    0xB0: 4,    # Charmander
    0xB1: 7,    # Squirtle
    0xB2: 5,    # Charmeleon
    0xB3: 8,    # Wartortle
    0xB4: 6,    # Charizard
    0xB9: 43,   # Oddish
    0xBA: 44,   # Gloom
    0xBB: 45,   # Vileplume
    0xBC: 69,   # Bellsprout
    0xBD: 70,   # Weepinbell
    0xBE: 71,   # Victreebel
}


# Catch rate values that get remapped to specific items during Time Capsule transfer.
# From pret/pokecrystal data/items/catch_rate_items.asm.
# Item IDs: BERRY=0x2D, BITTER_BERRY=0x2E, GOLD_BERRY=0x53, LEFTOVERS=0xAC
CATCH_RATE_ITEMS: dict[int, int] = {
    25:  0xAC,  # LEFTOVERS
    45:  0x2E,  # BITTER_BERRY
    50:  0x53,  # GOLD_BERRY
    90:  0x2D,  # BERRY
    100: 0x2D,  # BERRY
    120: 0x2D,  # BERRY
    135: 0x2D,  # BERRY
    190: 0x2D,  # BERRY
    195: 0x2D,  # BERRY
    220: 0x2D,  # BERRY
    250: 0x2D,  # BERRY
    255: 0x2D,  # BERRY
}


# Gen 2 base stats for the original 151 Pokemon, indexed by Pokedex number.
# Tuple order: (HP, ATK, DEF, SPD, SP_ATK, SP_DEF)
# From pret/pokecrystal data/pokemon/base_stats/.
GEN2_BASE_STATS: dict[int, tuple[int, int, int, int, int, int]] = {
    1:   (45, 49, 49, 45, 65, 65),      # Bulbasaur
    2:   (60, 62, 63, 60, 80, 80),      # Ivysaur
    3:   (80, 82, 83, 80, 100, 100),    # Venusaur
    4:   (39, 52, 43, 65, 60, 50),      # Charmander
    5:   (58, 64, 58, 80, 80, 65),      # Charmeleon
    6:   (78, 84, 78, 100, 109, 85),    # Charizard
    7:   (44, 48, 65, 43, 50, 64),      # Squirtle
    8:   (59, 63, 80, 58, 65, 80),      # Wartortle
    9:   (79, 83, 100, 78, 85, 105),    # Blastoise
    10:  (45, 30, 35, 45, 20, 20),      # Caterpie
    11:  (50, 20, 55, 30, 25, 25),      # Metapod
    12:  (60, 45, 50, 70, 80, 80),      # Butterfree
    13:  (40, 35, 30, 50, 20, 20),      # Weedle
    14:  (45, 25, 50, 35, 25, 25),      # Kakuna
    15:  (65, 80, 40, 75, 45, 80),      # Beedrill
    16:  (40, 45, 40, 56, 35, 35),      # Pidgey
    17:  (63, 60, 55, 71, 50, 50),      # Pidgeotto
    18:  (83, 80, 75, 91, 70, 70),      # Pidgeot
    19:  (30, 56, 35, 72, 25, 35),      # Rattata
    20:  (55, 81, 60, 97, 50, 70),      # Raticate
    21:  (40, 60, 30, 70, 31, 31),      # Spearow
    22:  (65, 90, 65, 100, 61, 61),     # Fearow
    23:  (35, 60, 44, 55, 40, 54),      # Ekans
    24:  (60, 85, 69, 80, 65, 79),      # Arbok
    25:  (35, 55, 30, 90, 50, 40),      # Pikachu
    26:  (60, 90, 55, 100, 90, 80),     # Raichu
    27:  (50, 75, 85, 40, 20, 30),      # Sandshrew
    28:  (75, 100, 110, 65, 45, 55),    # Sandslash
    29:  (55, 47, 52, 41, 40, 40),      # Nidoran♀
    30:  (70, 62, 67, 56, 55, 55),      # Nidorina
    31:  (90, 82, 87, 76, 75, 85),      # Nidoqueen
    32:  (46, 57, 40, 50, 40, 40),      # Nidoran♂
    33:  (61, 72, 57, 65, 55, 55),      # Nidorino
    34:  (81, 92, 77, 85, 85, 75),      # Nidoking
    35:  (70, 45, 48, 35, 60, 65),      # Clefairy
    36:  (95, 70, 73, 60, 85, 90),      # Clefable
    37:  (38, 41, 40, 65, 50, 65),      # Vulpix
    38:  (73, 76, 75, 100, 81, 100),    # Ninetales
    39:  (115, 45, 20, 20, 45, 25),     # Jigglypuff
    40:  (140, 70, 45, 45, 75, 50),     # Wigglytuff
    41:  (40, 45, 35, 55, 30, 40),      # Zubat
    42:  (75, 80, 70, 90, 65, 75),      # Golbat
    43:  (45, 50, 55, 30, 75, 65),      # Oddish
    44:  (60, 65, 70, 40, 85, 75),      # Gloom
    45:  (75, 80, 85, 50, 100, 90),     # Vileplume
    46:  (35, 70, 55, 25, 45, 55),      # Paras
    47:  (60, 95, 80, 30, 60, 80),      # Parasect
    48:  (60, 55, 50, 45, 40, 55),      # Venonat
    49:  (70, 65, 60, 90, 90, 75),      # Venomoth
    50:  (10, 55, 25, 95, 35, 45),      # Diglett
    51:  (35, 80, 50, 120, 50, 70),     # Dugtrio
    52:  (40, 45, 35, 90, 40, 40),      # Meowth
    53:  (65, 70, 60, 115, 65, 65),     # Persian
    54:  (50, 52, 48, 55, 65, 50),      # Psyduck
    55:  (80, 82, 78, 85, 95, 80),      # Golduck
    56:  (40, 80, 35, 70, 35, 45),      # Mankey
    57:  (65, 105, 60, 95, 60, 70),     # Primeape
    58:  (55, 70, 45, 60, 70, 50),      # Growlithe
    59:  (90, 110, 80, 95, 100, 80),    # Arcanine
    60:  (40, 50, 40, 90, 40, 40),      # Poliwag
    61:  (65, 65, 65, 90, 50, 50),      # Poliwhirl
    62:  (90, 85, 95, 70, 70, 90),      # Poliwrath
    63:  (25, 20, 15, 90, 105, 55),     # Abra
    64:  (40, 35, 30, 105, 120, 70),    # Kadabra
    65:  (55, 50, 45, 120, 135, 85),    # Alakazam
    66:  (70, 80, 50, 35, 35, 35),      # Machop
    67:  (80, 100, 70, 45, 50, 60),     # Machoke
    68:  (90, 130, 80, 55, 65, 85),     # Machamp
    69:  (50, 75, 35, 40, 70, 30),      # Bellsprout
    70:  (65, 90, 50, 55, 85, 45),      # Weepinbell
    71:  (80, 105, 65, 70, 100, 60),    # Victreebel
    72:  (40, 40, 35, 70, 50, 100),     # Tentacool
    73:  (80, 70, 65, 100, 80, 120),    # Tentacruel
    74:  (40, 80, 100, 20, 30, 30),     # Geodude
    75:  (55, 95, 115, 35, 45, 45),     # Graveler
    76:  (80, 110, 130, 45, 55, 65),    # Golem
    77:  (50, 85, 55, 90, 65, 65),      # Ponyta
    78:  (65, 100, 70, 105, 80, 80),    # Rapidash
    79:  (90, 65, 65, 15, 40, 40),      # Slowpoke
    80:  (95, 75, 110, 30, 100, 80),    # Slowbro
    81:  (25, 35, 70, 45, 95, 55),      # Magnemite
    82:  (50, 60, 95, 70, 120, 70),     # Magneton
    83:  (52, 65, 55, 60, 58, 62),      # Farfetch'd
    84:  (35, 85, 45, 75, 35, 35),      # Doduo
    85:  (60, 110, 70, 100, 60, 60),    # Dodrio
    86:  (65, 45, 55, 45, 45, 70),      # Seel
    87:  (90, 70, 80, 70, 70, 95),      # Dewgong
    88:  (80, 80, 50, 25, 40, 50),      # Grimer
    89:  (105, 105, 75, 50, 65, 100),   # Muk
    90:  (30, 65, 100, 40, 45, 25),     # Shellder
    91:  (50, 95, 180, 70, 85, 45),     # Cloyster
    92:  (30, 35, 30, 80, 100, 35),     # Gastly
    93:  (45, 50, 45, 95, 115, 55),     # Haunter
    94:  (60, 65, 60, 110, 130, 75),    # Gengar
    95:  (35, 45, 160, 70, 30, 45),     # Onix
    96:  (60, 48, 45, 42, 43, 90),      # Drowzee
    97:  (85, 73, 70, 67, 73, 115),     # Hypno
    98:  (30, 105, 90, 50, 25, 25),     # Krabby
    99:  (55, 130, 115, 75, 50, 50),    # Kingler
    100: (40, 30, 50, 100, 55, 55),     # Voltorb
    101: (60, 50, 70, 140, 80, 80),     # Electrode
    102: (60, 40, 80, 40, 60, 45),      # Exeggcute
    103: (95, 95, 85, 55, 125, 65),     # Exeggutor
    104: (50, 50, 95, 35, 40, 50),      # Cubone
    105: (60, 80, 110, 45, 50, 80),     # Marowak
    106: (50, 120, 53, 87, 35, 110),    # Hitmonlee
    107: (50, 105, 79, 76, 35, 110),    # Hitmonchan
    108: (90, 55, 75, 30, 60, 75),      # Lickitung
    109: (40, 65, 95, 35, 60, 45),      # Koffing
    110: (65, 90, 120, 60, 85, 70),     # Weezing
    111: (80, 85, 95, 25, 30, 30),      # Rhyhorn
    112: (105, 130, 120, 40, 45, 45),   # Rhydon
    113: (250, 5, 5, 50, 35, 105),      # Chansey
    114: (65, 55, 115, 60, 100, 40),    # Tangela
    115: (105, 95, 80, 90, 40, 80),     # Kangaskhan
    116: (30, 40, 70, 60, 70, 25),      # Horsea
    117: (55, 65, 95, 85, 95, 45),      # Seadra
    118: (45, 67, 60, 63, 35, 50),      # Goldeen
    119: (80, 92, 65, 68, 65, 80),      # Seaking
    120: (30, 45, 55, 85, 70, 55),      # Staryu
    121: (60, 75, 85, 115, 100, 85),    # Starmie
    122: (40, 45, 65, 90, 100, 120),    # Mr. Mime
    123: (70, 110, 80, 105, 55, 80),    # Scyther
    124: (65, 50, 35, 95, 115, 95),     # Jynx
    125: (65, 83, 57, 105, 95, 85),     # Electabuzz
    126: (65, 95, 57, 93, 100, 85),     # Magmar
    127: (65, 125, 100, 85, 55, 70),    # Pinsir
    128: (75, 100, 95, 110, 40, 70),    # Tauros
    129: (20, 10, 55, 80, 15, 20),      # Magikarp
    130: (95, 125, 79, 81, 60, 100),    # Gyarados
    131: (130, 85, 80, 60, 85, 95),     # Lapras
    132: (48, 48, 48, 48, 48, 48),      # Ditto
    133: (55, 55, 50, 55, 45, 65),      # Eevee
    134: (130, 65, 60, 65, 110, 95),    # Vaporeon
    135: (65, 65, 60, 130, 110, 95),    # Jolteon
    136: (65, 130, 60, 65, 95, 110),    # Flareon
    137: (65, 60, 70, 40, 85, 75),      # Porygon
    138: (35, 40, 100, 35, 90, 55),     # Omanyte
    139: (70, 60, 125, 55, 115, 70),    # Omastar
    140: (30, 80, 90, 55, 55, 45),      # Kabuto
    141: (60, 115, 105, 80, 65, 70),    # Kabutops
    142: (80, 105, 65, 130, 60, 75),    # Aerodactyl
    143: (160, 110, 65, 30, 65, 110),   # Snorlax
    144: (90, 85, 100, 85, 95, 125),    # Articuno
    145: (90, 90, 85, 100, 125, 90),    # Zapdos
    146: (90, 100, 90, 90, 125, 85),    # Moltres
    147: (41, 64, 45, 50, 50, 50),      # Dratini
    148: (61, 84, 65, 70, 70, 70),      # Dragonair
    149: (91, 134, 95, 80, 100, 100),   # Dragonite
    150: (106, 110, 90, 130, 154, 90),  # Mewtwo
    151: (100, 100, 100, 100, 100, 100),# Mew
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gen2_data.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/gen2_data.py tests/test_gen2_data.py
git commit -m "Add Gen 2 static data tables for Time Capsule conversion"
```

---

### Task 4: Gen 1 → Gen 2 Converter (`gen2_convert.py`)

**Files:**
- Create: `src/shiny_hunter/gen2_convert.py`
- Create: `tests/test_gen2_convert.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_gen2_convert.py`:

```python
"""Tests for Gen 1 → Gen 2 Time Capsule conversion."""
from __future__ import annotations

import math

from shiny_hunter.gen1_party import Gen1Pokemon
from shiny_hunter.gen2_convert import Gen2Pokemon, convert, calc_stat, calc_hp


def _make_bulbasaur() -> Gen1Pokemon:
    return Gen1Pokemon(
        species=0x99,
        current_hp=20,
        level=5,
        status=0,
        type1=0x16,
        type2=0x03,
        catch_rate=45,
        moves=(0x21, 0x2D, 0x00, 0x00),
        ot_id=1,
        experience=125,
        stat_exp=(0, 0, 0, 0, 0),
        dvs=(0xAA, 0xAA),
        pp=(35, 40, 0, 0),
        party_level=5,
        max_hp=20,
        attack=11,
        defense=11,
        speed=11,
        special=12,
        ot_name=b"\x91\x84\x83\x50\x00\x00\x00\x00\x00\x00\x00",
        nickname=b"\x81\x94\x8B\x81\x80\x92\x80\x94\x91\x50\x00",
    )


def test_species_conversion():
    mon = _make_bulbasaur()
    result = convert(mon)
    assert result.species == 1  # Bulbasaur = Pokedex #1


def test_held_item_catch_rate_remapping():
    mon = _make_bulbasaur()
    assert mon.catch_rate == 45
    result = convert(mon)
    assert result.held_item == 0x2E  # 45 -> BITTER_BERRY


def test_held_item_passthrough():
    mon = Gen1Pokemon(
        species=0x54,  # Pikachu (catch rate 190 in-game, but struct has whatever)
        current_hp=20, level=5, status=0, type1=0, type2=0,
        catch_rate=163,  # not in CATCH_RATE_ITEMS, pass through as-is
        moves=(0x21, 0, 0, 0), ot_id=1, experience=125,
        stat_exp=(0, 0, 0, 0, 0), dvs=(0xAA, 0xAA), pp=(35, 0, 0, 0),
        party_level=5, max_hp=20, attack=11, defense=11, speed=11, special=12,
        ot_name=b"\x50" + b"\x00" * 10, nickname=b"\x50" + b"\x00" * 10,
    )
    result = convert(mon)
    assert result.held_item == 163


def test_direct_copy_fields():
    mon = _make_bulbasaur()
    result = convert(mon)
    assert result.moves == mon.moves
    assert result.ot_id == mon.ot_id
    assert result.experience == mon.experience
    assert result.stat_exp == mon.stat_exp
    assert result.dvs == mon.dvs
    assert result.pp == mon.pp
    assert result.level == mon.level
    assert result.status == mon.status
    assert result.current_hp == mon.current_hp
    assert result.ot_name == mon.ot_name
    assert result.nickname == mon.nickname


def test_default_fields():
    mon = _make_bulbasaur()
    result = convert(mon)
    assert result.friendship == 70
    assert result.pokerus == 0
    assert result.caught_data == (0, 0)


def test_stat_calculation():
    # Bulbasaur: base ATK=49, DV ATK=10, stat_exp=0, level=5
    # stat_exp_bonus = floor(sqrt(0)) // 4 = 0
    # stat = ((49 + 10) * 2 + 0) * 5 // 100 + 5 = 118 * 5 // 100 + 5 = 590 // 100 + 5 = 5 + 5 = 10
    assert calc_stat(base=49, dv=10, stat_exp=0, level=5) == 10


def test_hp_calculation():
    # Bulbasaur: base HP=45, DV HP derived from (ATK=10,DEF=10,SPD=10,SPC=10)
    # HP DV = (10&1)<<3 | (10&1)<<2 | (10&1)<<1 | (10&1) = 0|0|0|0 = 0
    # HP = ((45 + 0) * 2 + 0) * 5 // 100 + 5 + 10 = 90 * 5 // 100 + 15 = 450//100 + 15 = 4 + 15 = 19
    assert calc_hp(base=45, dv=0, stat_exp=0, level=5) == 19


def test_sp_atk_sp_def_split():
    mon = _make_bulbasaur()
    result = convert(mon)
    # Both Sp.Atk and Sp.Def use the Special DV (low nibble of dvs[1]) = 10
    # and the Special stat_exp = 0
    # Bulbasaur base Sp.Atk = 65, Sp.Def = 65
    # ((65 + 10) * 2 + 0) * 5 // 100 + 5 = 150 * 5 // 100 + 5 = 750//100 + 5 = 7 + 5 = 12
    assert result.sp_attack == 12
    assert result.sp_defense == 12


def test_stats_recalculated_with_gen2_base_stats():
    mon = _make_bulbasaur()
    result = convert(mon)
    # ATK: base=49, dv=10, exp=0, lv=5 -> ((49+10)*2)*5//100+5 = 10
    assert result.attack == 10
    # DEF: base=49, dv=10, exp=0, lv=5 -> 10
    assert result.defense == 10
    # SPD: base=45, dv=10, exp=0, lv=5 -> ((45+10)*2)*5//100+5 = 110*5//100+5 = 550//100+5 = 10
    assert result.speed == 10


def test_to_bytes_length():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert len(data) == 48


def test_to_bytes_species_at_offset_0():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert data[0x00] == 1  # Bulbasaur Pokedex #1


def test_to_bytes_held_item_at_offset_1():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert data[0x01] == 0x2E  # BITTER_BERRY


def test_to_bytes_dvs_at_offset_0x15():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert data[0x15] == 0xAA
    assert data[0x16] == 0xAA


def test_to_bytes_friendship_at_offset_0x1b():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert data[0x1B] == 70


def test_to_bytes_level_at_offset_0x1f():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert data[0x1F] == 5


def test_unknown_species_raises():
    mon = Gen1Pokemon(
        species=0x1F,  # MissingNo.
        current_hp=20, level=5, status=0, type1=0, type2=0,
        catch_rate=0, moves=(0, 0, 0, 0), ot_id=1, experience=0,
        stat_exp=(0, 0, 0, 0, 0), dvs=(0, 0), pp=(0, 0, 0, 0),
        party_level=5, max_hp=20, attack=11, defense=11, speed=11, special=12,
        ot_name=b"\x50" + b"\x00" * 10, nickname=b"\x50" + b"\x00" * 10,
    )
    try:
        convert(mon)
        assert False, "should have raised"
    except KeyError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_gen2_convert.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shiny_hunter.gen2_convert'`

- [ ] **Step 3: Write implementation**

Create `src/shiny_hunter/gen2_convert.py`:

```python
"""Gen 1 → Gen 2 conversion using Time Capsule rules.

Faithfully replicates the conversion performed by the Time Capsule trade
in Pokemon Crystal, as documented in pret/pokecrystal engine/link/link.asm.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .gen1_party import Gen1Pokemon
from .gen2_data import CATCH_RATE_ITEMS, GEN1_TO_POKEDEX, GEN2_BASE_STATS


@dataclass(frozen=True)
class Gen2Pokemon:
    species: int
    held_item: int
    moves: tuple[int, int, int, int]
    ot_id: int
    experience: int
    stat_exp: tuple[int, int, int, int, int]
    dvs: tuple[int, int]
    pp: tuple[int, int, int, int]
    friendship: int
    pokerus: int
    caught_data: tuple[int, int]
    level: int
    status: int
    current_hp: int
    max_hp: int
    attack: int
    defense: int
    speed: int
    sp_attack: int
    sp_defense: int
    ot_name: bytes
    nickname: bytes

    def to_struct_bytes(self) -> bytes:
        """Serialize to the 48-byte Gen 2 party struct."""
        d = bytearray(48)
        d[0x00] = self.species
        d[0x01] = self.held_item
        d[0x02] = self.moves[0]
        d[0x03] = self.moves[1]
        d[0x04] = self.moves[2]
        d[0x05] = self.moves[3]
        d[0x06] = (self.ot_id >> 8) & 0xFF
        d[0x07] = self.ot_id & 0xFF
        d[0x08] = (self.experience >> 16) & 0xFF
        d[0x09] = (self.experience >> 8) & 0xFF
        d[0x0A] = self.experience & 0xFF
        _w16(d, 0x0B, self.stat_exp[0])
        _w16(d, 0x0D, self.stat_exp[1])
        _w16(d, 0x0F, self.stat_exp[2])
        _w16(d, 0x11, self.stat_exp[3])
        _w16(d, 0x13, self.stat_exp[4])
        d[0x15] = self.dvs[0]
        d[0x16] = self.dvs[1]
        d[0x17] = self.pp[0]
        d[0x18] = self.pp[1]
        d[0x19] = self.pp[2]
        d[0x1A] = self.pp[3]
        d[0x1B] = self.friendship
        d[0x1C] = self.pokerus
        d[0x1D] = self.caught_data[0]
        d[0x1E] = self.caught_data[1]
        d[0x1F] = self.level
        d[0x20] = self.status
        d[0x21] = 0  # unused
        _w16(d, 0x22, self.current_hp)
        _w16(d, 0x24, self.max_hp)
        _w16(d, 0x26, self.attack)
        _w16(d, 0x28, self.defense)
        _w16(d, 0x2A, self.speed)
        _w16(d, 0x2C, self.sp_attack)
        _w16(d, 0x2E, self.sp_defense)
        return bytes(d)


def _w16(buf: bytearray, offset: int, value: int) -> None:
    buf[offset] = (value >> 8) & 0xFF
    buf[offset + 1] = value & 0xFF


def calc_stat(*, base: int, dv: int, stat_exp: int, level: int) -> int:
    stat_exp_bonus = int(math.sqrt(stat_exp)) // 4
    return ((base + dv) * 2 + stat_exp_bonus) * level // 100 + 5


def calc_hp(*, base: int, dv: int, stat_exp: int, level: int) -> int:
    stat_exp_bonus = int(math.sqrt(stat_exp)) // 4
    return ((base + dv) * 2 + stat_exp_bonus) * level // 100 + level + 10


def convert(mon: Gen1Pokemon) -> Gen2Pokemon:
    pokedex = GEN1_TO_POKEDEX[mon.species]
    held_item = CATCH_RATE_ITEMS.get(mon.catch_rate, mon.catch_rate)
    base = GEN2_BASE_STATS[pokedex]

    atk_dv = (mon.dvs[0] >> 4) & 0xF
    def_dv = mon.dvs[0] & 0xF
    spd_dv = (mon.dvs[1] >> 4) & 0xF
    spc_dv = mon.dvs[1] & 0xF
    hp_dv = ((atk_dv & 1) << 3) | ((def_dv & 1) << 2) | ((spd_dv & 1) << 1) | (spc_dv & 1)

    hp_stat_exp, atk_stat_exp, def_stat_exp, spd_stat_exp, spc_stat_exp = mon.stat_exp

    max_hp = calc_hp(base=base[0], dv=hp_dv, stat_exp=hp_stat_exp, level=mon.level)
    attack = calc_stat(base=base[1], dv=atk_dv, stat_exp=atk_stat_exp, level=mon.level)
    defense = calc_stat(base=base[2], dv=def_dv, stat_exp=def_stat_exp, level=mon.level)
    speed = calc_stat(base=base[3], dv=spd_dv, stat_exp=spd_stat_exp, level=mon.level)
    sp_attack = calc_stat(base=base[4], dv=spc_dv, stat_exp=spc_stat_exp, level=mon.level)
    sp_defense = calc_stat(base=base[5], dv=spc_dv, stat_exp=spc_stat_exp, level=mon.level)

    return Gen2Pokemon(
        species=pokedex,
        held_item=held_item,
        moves=mon.moves,
        ot_id=mon.ot_id,
        experience=mon.experience,
        stat_exp=mon.stat_exp,
        dvs=mon.dvs,
        pp=mon.pp,
        friendship=70,
        pokerus=0,
        caught_data=(0, 0),
        level=mon.level,
        status=mon.status,
        current_hp=mon.current_hp,
        max_hp=max_hp,
        attack=attack,
        defense=defense,
        speed=speed,
        sp_attack=sp_attack,
        sp_defense=sp_defense,
        ot_name=mon.ot_name,
        nickname=mon.nickname,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_gen2_convert.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/gen2_convert.py tests/test_gen2_convert.py
git commit -m "Add Gen 1 to Gen 2 Time Capsule converter"
```

---

### Task 5: Crystal WRAM Injection (`crystal.py`)

**Files:**
- Create: `src/shiny_hunter/crystal.py`
- Create: `tests/test_crystal.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_crystal.py`:

```python
"""Tests for Crystal WRAM party injection."""
from __future__ import annotations

from shiny_hunter.crystal import (
    PARTY_COUNT_ADDR,
    PARTY_SPECIES_ADDR,
    PARTY_MON1_ADDR,
    PARTY_OT_ADDR,
    PARTY_NICK_ADDR,
    inject_party_slot,
)
from shiny_hunter.gen2_convert import Gen2Pokemon


class _FakeEmu:
    def __init__(self):
        self._mem: dict[int, int] = {}

    def read_byte(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def write_byte(self, addr: int, value: int) -> None:
        self._mem[addr] = value

    def write_bytes(self, addr: int, data: bytes) -> None:
        for i, b in enumerate(data):
            self._mem[addr + i] = b


def _make_gen2_mon() -> Gen2Pokemon:
    return Gen2Pokemon(
        species=1,  # Bulbasaur
        held_item=0x2E,
        moves=(0x21, 0x2D, 0, 0),
        ot_id=1,
        experience=125,
        stat_exp=(0, 0, 0, 0, 0),
        dvs=(0xAA, 0xAA),
        pp=(35, 40, 0, 0),
        friendship=70,
        pokerus=0,
        caught_data=(0, 0),
        level=5,
        status=0,
        current_hp=19,
        max_hp=19,
        attack=10,
        defense=10,
        speed=10,
        sp_attack=12,
        sp_defense=12,
        ot_name=b"\x91\x84\x83\x50\x00\x00\x00\x00\x00\x00\x00",
        nickname=b"\x81\x94\x8B\x81\x80\x92\x80\x94\x91\x50\x00",
    )


def test_inject_sets_party_count():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 1
    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)
    assert emu._mem[PARTY_COUNT_ADDR] == 2


def test_inject_writes_species_list():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 1
    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)
    assert emu._mem[PARTY_SPECIES_ADDR + 1] == 1  # Bulbasaur
    assert emu._mem[PARTY_SPECIES_ADDR + 2] == 0xFF  # terminator


def test_inject_writes_struct():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 1
    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)
    struct_addr = PARTY_MON1_ADDR + 48
    assert emu._mem[struct_addr + 0x00] == 1    # species
    assert emu._mem[struct_addr + 0x01] == 0x2E # held item
    assert emu._mem[struct_addr + 0x15] == 0xAA # DV byte 1
    assert emu._mem[struct_addr + 0x1B] == 70   # friendship
    assert emu._mem[struct_addr + 0x1F] == 5    # level


def test_inject_writes_ot_name():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 1
    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)
    ot_addr = PARTY_OT_ADDR + 11
    assert emu._mem[ot_addr] == 0x91  # 'R'


def test_inject_writes_nickname():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 1
    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)
    nick_addr = PARTY_NICK_ADDR + 11
    assert emu._mem[nick_addr] == 0x81  # 'B'


def test_inject_does_not_decrease_party_count():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 3
    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)
    assert emu._mem[PARTY_COUNT_ADDR] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_crystal.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'shiny_hunter.crystal'`

- [ ] **Step 3: Write implementation**

Create `src/shiny_hunter/crystal.py`:

```python
"""Crystal WRAM party addresses and injection.

Addresses from pret/pokecrystal ram/wram.asm (English Crystal).
"""
from __future__ import annotations

from .gen2_convert import Gen2Pokemon

# Crystal (English) WRAM addresses — verify against pokecrystal disassembly.
# These may need adjustment; start with values from wram.asm.
PARTY_COUNT_ADDR   = 0xDCD7
PARTY_SPECIES_ADDR = 0xDCD8  # 7 bytes: 6 slots + 0xFF terminator
PARTY_MON1_ADDR    = 0xDCDF  # 6 * 48 = 288 bytes
PARTY_OT_ADDR      = 0xDDFF  # 6 * 11 = 66 bytes
PARTY_NICK_ADDR    = 0xDE41  # 6 * 11 = 66 bytes

STRUCT_SIZE = 48
NAME_SIZE = 11


def inject_party_slot(emu, mon: Gen2Pokemon, slot: int = 1) -> None:
    current_count = emu.read_byte(PARTY_COUNT_ADDR)
    needed = slot + 1
    if needed > current_count:
        emu.write_byte(PARTY_COUNT_ADDR, needed)

    emu.write_byte(PARTY_SPECIES_ADDR + slot, mon.species)
    emu.write_byte(PARTY_SPECIES_ADDR + slot + 1, 0xFF)

    struct_addr = PARTY_MON1_ADDR + (slot * STRUCT_SIZE)
    emu.write_bytes(struct_addr, mon.to_struct_bytes())

    ot_addr = PARTY_OT_ADDR + (slot * NAME_SIZE)
    emu.write_bytes(ot_addr, mon.ot_name)

    nick_addr = PARTY_NICK_ADDR + (slot * NAME_SIZE)
    emu.write_bytes(nick_addr, mon.nickname)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_crystal.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add src/shiny_hunter/crystal.py tests/test_crystal.py
git commit -m "Add Crystal WRAM party injection"
```

---

### Task 6: Preview Orchestrator (`preview.py`)

**Files:**
- Create: `src/shiny_hunter/preview.py`

This module ties together the pipeline. It cannot be meaningfully unit-tested without ROMs, so we test it in the integration test (Task 8). Here we just create the module.

- [ ] **Step 1: Write implementation**

Create `src/shiny_hunter/preview.py`:

```python
"""Shiny preview pipeline: replay → convert → inject → screenshot."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import config as cfg_mod
from . import macro, trace
from .crystal import inject_party_slot
from .delays import seed_offset
from .emulator import Emulator
from .gen1_party import read_party_slot
from .gen2_convert import convert
from .polling import run_until_species


def generate_preview(
    *,
    trace_path: Path,
    gen1_rom: Path,
    macro_path: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_png: Path,
) -> Path:
    tr = trace.load(trace_path)
    cfg = cfg_mod.by_sha1(tr.rom_sha1)
    if cfg is None:
        raise ValueError(f"unknown ROM in trace (sha1={tr.rom_sha1})")

    state_path = Path(tr.state_path)
    state_bytes = state_path.read_bytes()

    gen1_mon = _replay_and_read_party(
        cfg=cfg,
        rom_path=gen1_rom,
        state_bytes=state_bytes,
        macro_path=macro_path,
        master_seed=tr.master_seed,
        target_attempt=tr.attempt,
    )

    gen2_mon = convert(gen1_mon)

    crystal_macro_obj = macro.load(crystal_macro)

    with Emulator(crystal_rom, headless=True) as emu:
        emu.load_state(crystal_state.read_bytes())
        inject_party_slot(emu, gen2_mon, slot=1)
        crystal_macro_obj.run(emu)
        emu.tick(60)
        _screenshot(emu, out_png)

    return out_png


def _replay_and_read_party(
    *,
    cfg,
    rom_path: Path,
    state_bytes: bytes,
    macro_path: Path,
    master_seed: int,
    target_attempt: int,
):
    delay = (seed_offset(master_seed) + target_attempt - 1) % (1 << 16)
    hunt_macro = macro.load(macro_path)

    with Emulator(rom_path, headless=True) as emu:
        emu.load_state(state_bytes)
        if delay:
            emu.tick(delay)
        run_until_species(
            emu, hunt_macro,
            species_addr=cfg.party_species_addr,
            dv_addr=cfg.party_dv_addr,
        )
        return read_party_slot(emu, cfg, slot=0)


def _screenshot(emu: Emulator, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    screen = emu._pyboy.screen.ndarray
    img = Image.fromarray(screen)
    img.save(out_path)
```

- [ ] **Step 2: Run all tests to verify no regressions**

Run: `pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add src/shiny_hunter/preview.py
git commit -m "Add shiny preview orchestrator"
```

---

### Task 7: CLI `preview` Command

**Files:**
- Modify: `src/shiny_hunter/cli.py`

- [ ] **Step 1: Add the `preview` command to `cli.py`**

Add the following after the `record` command definition (before `if __name__ == "__main__":`):

```python
@main.command()
@click.option(
    "--trace",
    "trace_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to the .trace.json sidecar from a found shiny.",
)
@click.option(
    "--rom",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Gen 1 ROM (.gb) that produced the trace.",
)
@click.option(
    "--macro",
    "macro_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Gen 1 macro used during the hunt (.yaml or .events.json).",
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
    help="Output PNG path. Defaults to <trace_stem>.png alongside the trace.",
)
def preview(
    trace_path: Path,
    rom: Path,
    macro_path: Path,
    crystal_rom: Path,
    crystal_state: Path,
    crystal_macro: Path,
    out_path: Path | None,
) -> None:
    """Generate a Crystal screenshot of a shiny found in Gen 1."""
    from .preview import generate_preview

    if out_path is None:
        out_path = trace_path.with_suffix(".png")

    click.echo(f"Generating preview for {trace_path.name}...")
    result = generate_preview(
        trace_path=trace_path,
        gen1_rom=rom,
        macro_path=macro_path,
        crystal_rom=crystal_rom,
        crystal_state=crystal_state,
        crystal_macro=crystal_macro,
        out_png=out_path,
    )
    click.echo(f"Preview saved to {result}")
```

- [ ] **Step 2: Verify CLI help works**

Run: `shiny-hunt preview --help`
Expected: Shows the preview command usage with all options listed.

- [ ] **Step 3: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/shiny_hunter/cli.py
git commit -m "Add preview CLI command for Crystal shiny screenshots"
```

---

### Task 8: Integration Test (needs_rom)

**Files:**
- Create: `tests/test_preview.py`

This test requires real ROM files and is marked `needs_rom`. It validates the full pipeline end-to-end.

- [ ] **Step 1: Write the integration test**

Create `tests/test_preview.py`:

```python
"""Integration test for the shiny preview pipeline.

Requires real ROM files — skipped unless roms/ directory is populated.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROMS_DIR = Path("roms")

needs_rom = pytest.mark.skipif(
    not ROMS_DIR.exists() or not any(ROMS_DIR.glob("*.gb")),
    reason="requires ROM files in roms/",
)


@needs_rom
def test_preview_pipeline_produces_png(tmp_path):
    """Smoke test: run the preview pipeline and verify a PNG is produced.

    This test is a skeleton that should be filled in once ROM files,
    a Crystal ROM, template state, and macros are available.
    """
    # To run this test:
    # 1. Place a Gen 1 ROM in roms/
    # 2. Place a Crystal ROM in roms/
    # 3. Create a trace JSON, Gen 1 state, Gen 1 macro, Crystal state, Crystal macro
    # 4. Update the paths below
    pytest.skip("requires manual setup — see comment above")
```

- [ ] **Step 2: Run the test to verify it is skipped gracefully**

Run: `pytest tests/test_preview.py -v`
Expected: test is SKIPPED (no ROM files)

- [ ] **Step 3: Commit**

```bash
git add tests/test_preview.py
git commit -m "Add integration test skeleton for preview pipeline"
```

---

### Task 9: Run Full Test Suite

- [ ] **Step 1: Run the complete test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS (integration test skipped if no ROMs)

- [ ] **Step 2: Verify no import errors by importing all new modules**

Run: `python -c "from shiny_hunter import gen1_party, gen2_data, gen2_convert, crystal, preview; print('all imports OK')"`
Expected: `all imports OK`

- [ ] **Step 3: Verify CLI command is registered**

Run: `shiny-hunt --help`
Expected: `preview` appears in the commands list
