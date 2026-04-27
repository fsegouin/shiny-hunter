"""Pokémon Green (Japan) — the original JP pair to Red, never released elsewhere.

Same engine and RAM layout as JP Red.
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="green",
    region="jp",
    rom_sha1="d68d1a1e6d6e7a3f93a1c0f7b7e8b4c6c4f2c6cc",  # placeholder; see TODO
    party_dv_addr=0xD171,
    party_species_addr=0xD14F,
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
