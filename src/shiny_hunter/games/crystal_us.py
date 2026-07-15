"""Pokémon Crystal (US/EU), Rev 1 (primary) and Rev 0 (alt SHA-1).

RAM offsets verified against pret/pokecrystal symbol files (`symbols`
branch); `pokecrystal.sym` (Rev 0) and `pokecrystal11.sym` (Rev 1) agree
on every address used here:
  wPartyCount        = 0xDCD7
  wPartySpecies[0]   = 0xDCD8
  wPartyMon1         = 0xDCDF  (48-byte party struct; DVs at offset 0x15)
  wPartyMon1DVs      = 0xDCF4
  wEnemyMon          = 0xD206  (battle struct; DVs at offset 0x06)
  wEnemyMonDVs       = 0xD20C
"""
from __future__ import annotations

from ..config import GameConfig, register
from ._gen2 import GEN2_STARTERS

CONFIG = GameConfig(
    game="crystal",
    region="us",
    rom_sha1="f2f52230b536214ef7c9924f483392993e226cfb",
    alt_sha1s=("f4cd194bdee0d04ca4eac29e09b8e4e9d818c133",),  # Rev 0
    party_dv_addr=0xDCF4,
    party_species_addr=0xDCD8,
    enemy_dv_addr=0xD20C,
    enemy_species_addr=0xD206,
    sram_size=0x8000,
    starters=GEN2_STARTERS,
    starter_macro="crystal_us_starter.yaml",
    save_macro="crystal_us_save.yaml",
    generation=2,
)

register(CONFIG)
