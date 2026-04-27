"""Gen 1 DV decoding and Gen 2 shiny predicate.

A Pokémon transferred from Gen 1 to Gen 2 is shiny iff:
    Def DV == 10  AND  Spd DV == 10  AND  Spc DV == 10
    AND  Atk DV ∈ {2, 3, 6, 7, 10, 11, 14, 15}

In Gen 1 RAM, the DVs of a party Pokémon are packed into 2 bytes:
    byte 0 (high):  upper nybble = Atk DV,  lower nybble = Def DV
    byte 1 (low):   upper nybble = Spd DV,  lower nybble = Spc DV
"""
from __future__ import annotations

from dataclasses import dataclass

SHINY_ATK_VALUES: frozenset[int] = frozenset({2, 3, 6, 7, 10, 11, 14, 15})


@dataclass(frozen=True)
class DVs:
    atk: int
    def_: int
    spd: int
    spc: int

    @property
    def hp(self) -> int:
        # HP DV is derived from the LSB of each other DV.
        return (
            ((self.atk & 1) << 3)
            | ((self.def_ & 1) << 2)
            | ((self.spd & 1) << 1)
            | (self.spc & 1)
        )

    def as_dict(self) -> dict[str, int]:
        return {"atk": self.atk, "def": self.def_, "spd": self.spd, "spc": self.spc, "hp": self.hp}


def decode_dvs(byte_atk_def: int, byte_spd_spc: int) -> DVs:
    return DVs(
        atk=(byte_atk_def >> 4) & 0xF,
        def_=byte_atk_def & 0xF,
        spd=(byte_spd_spc >> 4) & 0xF,
        spc=byte_spd_spc & 0xF,
    )


def is_shiny(dvs: DVs) -> bool:
    return (
        dvs.def_ == 10
        and dvs.spd == 10
        and dvs.spc == 10
        and dvs.atk in SHINY_ATK_VALUES
    )
