"""Pocket Monsters Gin — Pokémon Silver (JP), Rev 1.

Identical WRAM layout to Kin/Gold (JP) — the opcode-literal frequency
analysis described in `gold_jp.py` produces the exact same reference
counts on this dump. JP Rev 0 is deliberately not registered (unverified).
"""
from __future__ import annotations

from ..config import GameConfig, register
from ._gen2 import GEN2_STARTERS

CONFIG = GameConfig(
    game="silver",
    region="jp",
    rom_sha1="a11d5ddc26eb826086593f82370b15d16404d33e",
    party_dv_addr=0xDA05,
    party_species_addr=0xD9E9,
    enemy_dv_addr=0xD0E7,
    enemy_species_addr=0xD0E1,
    sram_size=0x8000,
    starters=GEN2_STARTERS,
    starter_macro="silver_jp_starter.yaml",
    save_macro="silver_jp_save.yaml",
    generation=2,
)

register(CONFIG)
