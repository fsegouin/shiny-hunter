"""Pokémon Silver (US/EU).

Identical WRAM layout to Gold (US) — verified against pret/pokegold
`pokesilver.sym` (symbols branch); see `gold_us.py` for the address map.
"""
from __future__ import annotations

from ..config import GameConfig, register
from ._gen2 import GEN2_STARTERS

CONFIG = GameConfig(
    game="silver",
    region="us",
    rom_sha1="49b163f7e57702bc939d642a18f591de55d92dae",
    party_dv_addr=0xDA3F,
    party_species_addr=0xDA23,
    enemy_dv_addr=0xD0F5,
    enemy_species_addr=0xD0EF,
    sram_size=0x8000,
    starters=GEN2_STARTERS,
    starter_macro="silver_us_starter.yaml",
    save_macro="silver_us_save.yaml",
    generation=2,
)

register(CONFIG)
