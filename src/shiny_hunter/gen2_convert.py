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


def _effective_level(mon: Gen1Pokemon) -> int:
    if 1 <= mon.party_level <= 100:
        return mon.party_level
    if 1 <= mon.level <= 100:
        return mon.level
    raise ValueError(
        f"invalid Gen 1 level: party_level={mon.party_level}, box_level={mon.level}; "
        "the save-state may have been captured before the party struct finished updating"
    )


def _converted_current_hp(mon: Gen1Pokemon, max_hp: int) -> int:
    if mon.current_hp <= 0:
        return 0

    if mon.max_hp <= 0:
        return min(mon.current_hp, max_hp)

    missing_hp = max(0, mon.max_hp - min(mon.current_hp, mon.max_hp))
    return max(1, min(max_hp, max_hp - missing_hp))


def convert(mon: Gen1Pokemon) -> Gen2Pokemon:
    pokedex = GEN1_TO_POKEDEX[mon.species]
    held_item = CATCH_RATE_ITEMS.get(mon.catch_rate, mon.catch_rate)
    base = GEN2_BASE_STATS[pokedex]
    level = _effective_level(mon)

    if level > 1 and mon.experience == 0:
        raise ValueError(
            f"invalid Gen 1 experience for level {level}: 0; "
            "the save-state may have been captured before the party struct finished updating"
        )

    atk_dv = (mon.dvs[0] >> 4) & 0xF
    def_dv = mon.dvs[0] & 0xF
    spd_dv = (mon.dvs[1] >> 4) & 0xF
    spc_dv = mon.dvs[1] & 0xF
    hp_dv = ((atk_dv & 1) << 3) | ((def_dv & 1) << 2) | ((spd_dv & 1) << 1) | (spc_dv & 1)

    hp_stat_exp, atk_stat_exp, def_stat_exp, spd_stat_exp, spc_stat_exp = mon.stat_exp

    max_hp = calc_hp(base=base[0], dv=hp_dv, stat_exp=hp_stat_exp, level=level)
    attack = calc_stat(base=base[1], dv=atk_dv, stat_exp=atk_stat_exp, level=level)
    defense = calc_stat(base=base[2], dv=def_dv, stat_exp=def_stat_exp, level=level)
    speed = calc_stat(base=base[3], dv=spd_dv, stat_exp=spd_stat_exp, level=level)
    sp_attack = calc_stat(base=base[4], dv=spc_dv, stat_exp=spc_stat_exp, level=level)
    sp_defense = calc_stat(base=base[5], dv=spc_dv, stat_exp=spc_stat_exp, level=level)
    current_hp = _converted_current_hp(mon, max_hp)

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
        level=level,
        status=mon.status,
        current_hp=current_hp,
        max_hp=max_hp,
        attack=attack,
        defense=defense,
        speed=speed,
        sp_attack=sp_attack,
        sp_defense=sp_defense,
        ot_name=mon.ot_name,
        nickname=mon.nickname,
    )
