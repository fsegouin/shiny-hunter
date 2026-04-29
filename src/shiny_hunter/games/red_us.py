"""Pokémon Red (US, Rev 0).

RAM offsets verified against pret/pokered (`ram/wram.asm`):
  wPartyCount        = 0xD163
  wPartySpecies[0]   = 0xD164
  wPartyMon1         = 0xD16B  (44-byte struct; DVs at offset 0x1B)
  wPartyMon1DVs      = 0xD186  (high byte: Atk<<4|Def; +1: Spd<<4|Spc)

Starter species IDs (Gen 1 internal hex, not Pokédex number):
  Bulbasaur = 0x99,  Charmander = 0xB0,  Squirtle = 0xB1
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="red",
    region="us",
    rom_sha1="ea9bcae617fdf159b045185467ae58b2e4a48b9a",
    party_dv_addr=0xD186,
    party_species_addr=0xD164,
    enemy_dv_addr=0xCFD8,
    enemy_species_addr=0xCFCC,
    sram_size=0x8000,
    starters={
        0x99: "bulbasaur",
        0xB0: "charmander",
        0xB1: "squirtle",
    },
    starter_macro="red_us_starter.yaml",
    save_macro="red_us_save.yaml",
)

register(CONFIG)
