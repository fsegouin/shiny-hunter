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
    """Write a Gen 2 Pokemon into the given party slot in Crystal WRAM."""
    inject_party_slot_bytes(
        emu,
        struct_bytes=mon.to_struct_bytes(),
        species=mon.species,
        ot_name=mon.ot_name,
        nickname=mon.nickname,
        slot=slot,
    )


def inject_party_slot_bytes(
    emu,
    *,
    struct_bytes: bytes,
    species: int,
    ot_name: bytes,
    nickname: bytes,
    slot: int = 1,
) -> None:
    """Write a raw 48-byte party struct into the given Crystal party slot.

    Updates the party count if needed (never decreases it), writes the
    species list entry with terminator, the 48-byte struct, OT name,
    and nickname.
    """
    if len(struct_bytes) != STRUCT_SIZE:
        raise ValueError(f"expected {STRUCT_SIZE}-byte struct, got {len(struct_bytes)}")

    current_count = emu.read_byte(PARTY_COUNT_ADDR)
    needed = slot + 1
    if needed > current_count:
        emu.write_byte(PARTY_COUNT_ADDR, needed)

    emu.write_byte(PARTY_SPECIES_ADDR + slot, species)
    emu.write_byte(PARTY_SPECIES_ADDR + slot + 1, 0xFF)

    struct_addr = PARTY_MON1_ADDR + (slot * STRUCT_SIZE)
    emu.write_bytes(struct_addr, struct_bytes)

    ot_addr = PARTY_OT_ADDR + (slot * NAME_SIZE)
    emu.write_bytes(ot_addr, ot_name)

    nick_addr = PARTY_NICK_ADDR + (slot * NAME_SIZE)
    emu.write_bytes(nick_addr, nickname)
