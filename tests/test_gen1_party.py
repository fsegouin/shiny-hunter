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
        for i, b in enumerate(struct_bytes):
            self._mem[PARTY_STRUCT_BASE + i] = b
        for i, b in enumerate(ot_name):
            self._mem[OT_NAMES_BASE + i] = b
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
