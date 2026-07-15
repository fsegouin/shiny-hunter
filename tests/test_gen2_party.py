"""Tests for the Gen 2 party reader (mirrors test_gen1_party.py's fakes)."""
from shiny_hunter.gen2_party import DV_OFFSET, STRUCT_SIZE, read_party_slot

# Crystal (US) addresses — arbitrary for the fake, but realistic.
SPECIES_ADDR = 0xDCD8
STRUCT_BASE = SPECIES_ADDR + 7  # 0xDCDF
OT_NAMES_BASE = STRUCT_BASE + 6 * STRUCT_SIZE
NICKNAMES_BASE = OT_NAMES_BASE + 6 * 11


def _make_gen2_struct(species: int = 158, dvs: tuple[int, int] = (0xEA, 0xAA)) -> bytes:
    d = bytearray(STRUCT_SIZE)
    d[0] = species
    d[DV_OFFSET] = dvs[0]
    d[DV_OFFSET + 1] = dvs[1]
    d[0x1F] = 5  # level
    return bytes(d)


def _en_name(text: str) -> bytes:
    name = bytearray([0x50] * 11)
    for i, ch in enumerate(text):
        name[i] = 0x80 + (ord(ch) - ord("A"))
    name[len(text)] = 0x50
    return bytes(name)


class _FakeEmu:
    def __init__(self, struct_bytes: bytes, ot_name: bytes, nickname: bytes, slot: int = 0):
        self._mem: dict[int, int] = {}
        for i, b in enumerate(struct_bytes):
            self._mem[STRUCT_BASE + slot * STRUCT_SIZE + i] = b
        for i, b in enumerate(ot_name):
            self._mem[OT_NAMES_BASE + slot * 11 + i] = b
        for i, b in enumerate(nickname):
            self._mem[NICKNAMES_BASE + slot * 11 + i] = b

    def read_byte(self, addr: int) -> int:
        return self._mem.get(addr, 0)

    def read_bytes(self, addr: int, length: int) -> bytes:
        return bytes(self._mem.get(addr + i, 0) for i in range(length))


class _FakeConfig:
    party_species_addr = SPECIES_ADDR
    region = "us"


class _FakeConfigJP:
    party_species_addr = SPECIES_ADDR
    region = "jp"


def test_read_party_slot_totodile():
    struct_bytes = _make_gen2_struct()
    emu = _FakeEmu(struct_bytes, _en_name("GOLD"), _en_name("TOTODILE"))

    mon = read_party_slot(emu, _FakeConfig(), slot=0)

    assert mon.species == 158
    assert mon.struct_bytes == struct_bytes
    assert mon.dvs == (0xEA, 0xAA)
    assert mon.ot_name == _en_name("GOLD")
    assert mon.nickname == _en_name("TOTODILE")


def test_read_party_slot_nonzero_slot():
    struct_bytes = _make_gen2_struct(species=155)
    emu = _FakeEmu(struct_bytes, _en_name("KRIS"), _en_name("CYNDAQUIL"), slot=2)

    mon = read_party_slot(emu, _FakeConfig(), slot=2)

    assert mon.species == 155
    assert mon.ot_name == _en_name("KRIS")


def test_jp_names_use_placeholder():
    struct_bytes = _make_gen2_struct()
    emu = _FakeEmu(struct_bytes, b"\x00" * 11, b"\x00" * 11)

    mon = read_party_slot(emu, _FakeConfigJP(), slot=0)

    assert mon.species == 158
    assert len(mon.ot_name) == 11
    assert mon.ot_name[5] == 0x50  # terminated
    assert mon.ot_name == mon.nickname  # both placeholder


def test_shiny_dv_bytes_roundtrip():
    # DVs 0xEA/0xAA = ATK 14, DEF 10, SPD 10, SPC 10 — a shiny spread.
    from shiny_hunter.dv import decode_dvs, is_shiny

    mon = read_party_slot(
        _FakeEmu(_make_gen2_struct(), _en_name("GOLD"), _en_name("A")),
        _FakeConfig(),
        slot=0,
    )
    assert is_shiny(decode_dvs(*mon.dvs))
