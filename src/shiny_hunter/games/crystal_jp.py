"""Pocket Monsters Crystal (JP).

No pret disassembly targets the JP ROM. Addresses were derived by aligning
opcode-literal reference profiles (`ld a,[nn]` / `ld [nn],a` / `ld hl,nn`
operands) between this dump and the pret-verified EN Crystal: the party
region is shifted −0x3A and the battle region +0x31, with per-address
reference counts matching the EN ground truth (e.g. wPartyMon1DVs: 15 refs
in both ROMs).
  wPartyCount        = 0xDC9D
  wPartySpecies[0]   = 0xDC9E
  wPartyMon1         = 0xDCA5  (48-byte party struct; DVs at offset 0x15)
  wPartyMon1DVs      = 0xDCBA
  wEnemyMon          = 0xD237  (battle struct; DVs at offset 0x06)
  wEnemyMonDVs       = 0xD23D

The JP cart is MBC30 with 64 KB SRAM (header ramsize 0x05) for the
Mobile Adapter feature — unlike every other Gen 1/2 cart (32 KB).
"""
from __future__ import annotations

from ..config import GameConfig, register
from ._gen2 import GEN2_STARTERS

CONFIG = GameConfig(
    game="crystal",
    region="jp",
    rom_sha1="95127b901bbce2407daf43cce9f45d4c27ef635d",
    party_dv_addr=0xDCBA,
    party_species_addr=0xDC9E,
    enemy_dv_addr=0xD23D,
    enemy_species_addr=0xD237,
    sram_size=0x10000,
    starters=GEN2_STARTERS,
    starter_macro="crystal_jp_starter.yaml",
    save_macro="crystal_jp_save.yaml",
    generation=2,
)

register(CONFIG)
