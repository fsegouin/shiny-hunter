"""Pocket Monsters Kin — Pokémon Gold (JP), Rev 1.

No pret disassembly targets the JP retail ROMs. Addresses below come from
the JP debug-build disassembly (pizdex/pokegold-debug `wram.asm`) and were
confirmed against this exact retail dump by opcode-literal frequency
analysis: the count of `ld a,[nn]` / `ld [nn],a` / `ld hl,nn` instructions
referencing each address matches the pret-verified EN Gold counts exactly
(e.g. wPartyCount: 137 refs in both ROMs).
  wPartyCount        = 0xD9E8
  wPartySpecies[0]   = 0xD9E9
  wPartyMon1         = 0xD9F0  (48-byte party struct; DVs at offset 0x15)
  wPartyMon1DVs      = 0xDA05
  wEnemyMon          = 0xD0E1  (battle struct; DVs at offset 0x06)
  wEnemyMonDVs       = 0xD0E7

The JP Rev 0 dump exists but its WRAM layout is unverified — it is
deliberately not registered here.
"""
from __future__ import annotations

from ..config import GameConfig, register
from ._gen2 import GEN2_STARTERS

CONFIG = GameConfig(
    game="gold",
    region="jp",
    rom_sha1="a222402235d484ee8e39f3f31bae57cf13daf585",
    party_dv_addr=0xDA05,
    party_species_addr=0xD9E9,
    enemy_dv_addr=0xD0E7,
    enemy_species_addr=0xD0E1,
    sram_size=0x8000,
    starters=GEN2_STARTERS,
    starter_macro="gold_jp_starter.yaml",
    save_macro="gold_jp_save.yaml",
    generation=2,
)

register(CONFIG)
