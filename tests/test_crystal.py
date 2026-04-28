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


def test_inject_supports_one_pokemon_template_for_slot_2():
    emu = _FakeEmu()
    emu._mem[PARTY_COUNT_ADDR] = 1
    emu._mem[PARTY_SPECIES_ADDR] = 25
    emu._mem[PARTY_SPECIES_ADDR + 1] = 0xFF

    mon = _make_gen2_mon()
    inject_party_slot(emu, mon, slot=1)

    assert emu._mem[PARTY_COUNT_ADDR] == 2
    assert emu._mem[PARTY_SPECIES_ADDR] == 25
    assert emu._mem[PARTY_SPECIES_ADDR + 1] == 1
    assert emu._mem[PARTY_SPECIES_ADDR + 2] == 0xFF


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
