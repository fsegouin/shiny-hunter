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
