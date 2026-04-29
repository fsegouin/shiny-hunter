"""Pokémon Yellow (Japan).

RAM offsets verified against pret/pokeyellow JP build target.
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="yellow",
    region="jp",
    rom_sha1="73df51640edcf85d5e95eddc9388762d1d3a7d8d",
    party_dv_addr=0xD170,
    party_species_addr=0xD14E,
    enemy_dv_addr=0xCFBE,
    enemy_species_addr=0xCFB2,
    sram_size=0x8000,
    starters={0x54: "pikachu"},
    starter_macro="yellow_jp_starter.yaml",
    save_macro="yellow_jp_save.yaml",
)

register(CONFIG)
