"""Pokémon Blue (US, Rev 0).

Shares the same RAM layout as Red (US) — same disassembly target in
pret/pokered. Only the ROM SHA-1 differs.
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="blue",
    region="us",
    rom_sha1="d7037c83e1ae5b39bde3c30787637ba1d4c48ce2",
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
    starter_macro="red_us_starter.yaml",  # identical menu flow
    save_macro="red_us_save.yaml",
)

register(CONFIG)
