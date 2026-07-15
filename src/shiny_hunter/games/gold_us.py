"""Pokémon Gold (US/EU).

RAM offsets verified against pret/pokegold symbol file (`symbols` branch,
`pokegold.sym`, build-verified against this retail dump):
  wPartyCount        = 0xDA22
  wPartySpecies[0]   = 0xDA23
  wPartyMon1         = 0xDA2A  (48-byte party struct; DVs at offset 0x15)
  wPartyMon1DVs      = 0xDA3F  (high byte: Atk<<4|Def; +1: Spd<<4|Spc)
  wEnemyMon          = 0xD0EF  (battle struct; DVs at offset 0x06)
  wEnemyMonDVs       = 0xD0F5

Gen 2 species IDs are National Pokédex numbers:
  Chikorita = 152,  Cyndaquil = 155,  Totodile = 158
"""
from __future__ import annotations

from ..config import GameConfig, register
from ._gen2 import GEN2_STARTERS

CONFIG = GameConfig(
    game="gold",
    region="us",
    rom_sha1="d8b8a3600a465308c9953dfa04f0081c05bdcb94",
    party_dv_addr=0xDA3F,
    party_species_addr=0xDA23,
    enemy_dv_addr=0xD0F5,
    enemy_species_addr=0xD0EF,
    sram_size=0x8000,
    starters=GEN2_STARTERS,
    starter_macro="gold_us_starter.yaml",
    save_macro="gold_us_save.yaml",
    generation=2,
)

register(CONFIG)
