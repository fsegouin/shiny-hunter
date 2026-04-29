"""Pokémon Red (Japan).

JP RAM offsets shift downward vs US because the JP version has shorter
text engine state. Values below come from pret/pokered's JP build target
(`make pokered_jp`) and should be verified against that disassembly's
`sym/pokered_jp.sym` symbol file before relying on them in production.

The JP starter selection flow uses the same dialog structure but kana
text rolls faster, so the post-A `after` durations in
`red_jp_starter.yaml` are tuned shorter than the US macro.
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="red",
    region="jp",
    # Two known JP Red dumps exist (rev 0 / rev 1). We ship rev 1 (more common).
    rom_sha1="b29f73ac86c39e2024dee03c2dca35a4ea03df41",
    # JP wRAM shifts: confirm against pret/pokered JP build's sym file.
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
