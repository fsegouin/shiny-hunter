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
    assert result.species == 1


def test_held_item_catch_rate_remapping():
    mon = _make_bulbasaur()
    assert mon.catch_rate == 45
    result = convert(mon)
    assert result.held_item == 0x2E


def test_held_item_passthrough():
    mon = Gen1Pokemon(
        species=0x54, current_hp=20, level=5, status=0, type1=0, type2=0,
        catch_rate=163, moves=(0x21, 0, 0, 0), ot_id=1, experience=125,
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
    assert calc_stat(base=49, dv=10, stat_exp=0, level=5) == 10


def test_hp_calculation():
    assert calc_hp(base=45, dv=0, stat_exp=0, level=5) == 19


def test_sp_atk_sp_def_split():
    mon = _make_bulbasaur()
    result = convert(mon)
    assert result.sp_attack == 12
    assert result.sp_defense == 12


def test_stats_recalculated_with_gen2_base_stats():
    mon = _make_bulbasaur()
    result = convert(mon)
    assert result.attack == 10
    assert result.defense == 10
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
    assert data[0x00] == 1


def test_to_bytes_held_item_at_offset_1():
    mon = _make_bulbasaur()
    result = convert(mon)
    data = result.to_struct_bytes()
    assert data[0x01] == 0x2E


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
        species=0x1F, current_hp=20, level=5, status=0, type1=0, type2=0,
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
