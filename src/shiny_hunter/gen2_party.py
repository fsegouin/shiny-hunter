"""Gen 2 party data reader — reads the raw 48-byte party struct from WRAM.

Layout (pret/pokecrystal `ram/wram.asm`, identical relative layout in all
GSC variants):
    wPartyCount      = party_species_addr - 1
    wPartySpecies    = 6 slots + 0xFF terminator (7 bytes)
    wPartyMon1..6    = 6 x 48-byte party structs
    wPartyMonOT      = 6 x NAME_LENGTH
    wPartyMonNicks   = 6 x NAME_LENGTH

NAME_LENGTH is 11 in the international releases and 6 in the Japanese
ones. JP names use a different character encoding, so for JP games we
substitute a fixed EN-encoded placeholder instead of reading them —
the preview pipeline injects into an English Crystal ROM.
"""
from __future__ import annotations

from dataclasses import dataclass

STRUCT_SIZE = 48
DV_OFFSET = 0x15

# "SHINY" in the EN Gen 1/2 charset, 0x50-terminated and padded to 11.
_PLACEHOLDER_NAME = bytes([0x92, 0x87, 0x88, 0x8D, 0x98, 0x50, 0x50, 0x50, 0x50, 0x50, 0x50])


@dataclass(frozen=True)
class Gen2PartyMon:
    species: int
    struct_bytes: bytes  # raw 48-byte party struct
    dvs: tuple[int, int]  # raw bytes: [ATK|DEF], [SPD|SPC]
    ot_name: bytes  # 11 bytes, 0x50-terminated (placeholder for JP)
    nickname: bytes  # 11 bytes, 0x50-terminated (placeholder for JP)


def read_party_slot(emu, cfg, slot: int = 0) -> Gen2PartyMon:
    struct_base = cfg.party_species_addr + 7
    d = emu.read_bytes(struct_base + slot * STRUCT_SIZE, STRUCT_SIZE)

    if cfg.region == "jp":
        ot_name = _PLACEHOLDER_NAME
        nickname = _PLACEHOLDER_NAME
    else:
        name_len = 11
        ot_names_base = struct_base + 6 * STRUCT_SIZE
        nicknames_base = ot_names_base + 6 * name_len
        ot_name = bytes(emu.read_bytes(ot_names_base + slot * name_len, name_len))
        nickname = bytes(emu.read_bytes(nicknames_base + slot * name_len, name_len))

    return Gen2PartyMon(
        species=d[0],
        struct_bytes=bytes(d),
        dvs=(d[DV_OFFSET], d[DV_OFFSET + 1]),
        ot_name=ot_name,
        nickname=nickname,
    )
