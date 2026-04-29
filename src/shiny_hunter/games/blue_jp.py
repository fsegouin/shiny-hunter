"""Pokémon Blue (Japan) — JP re-release, distinct from US Blue.

Same engine as JP Red/Green; ROM hash differs.
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="blue",
    region="jp",
    rom_sha1="b6cb22de23faa9c0afb13e89fd2eaa9aa78ed538",
    party_dv_addr=0xD171,
    party_species_addr=0xD14F,
    enemy_dv_addr=0xCFBF,
    enemy_species_addr=0xCFB3,
    sram_size=0x8000,
    starters={
        0x99: "bulbasaur",
        0xB0: "charmander",
        0xB1: "squirtle",
    },
    starter_macro="red_jp_starter.yaml",
    save_macro="red_jp_save.yaml",
)

register(CONFIG)
