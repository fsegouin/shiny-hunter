"""Pokémon Yellow (US, Rev 0).

RAM layout shifts slightly from Red/Blue (extra fields for Pikachu's
following-mon state, etc.). pret/pokeyellow's `ram/wram.asm` is the
authoritative source. The values below match pret/pokeyellow @ master:
  wPartyCount        = 0xD162
  wPartySpecies[0]   = 0xD163
  wPartyMon1DVs      = 0xD185

Yellow gives Pikachu (species 0x54) and only Pikachu — no choice.
"""
from __future__ import annotations

from ..config import GameConfig, register

CONFIG = GameConfig(
    game="yellow",
    region="us",
    rom_sha1="cc7d03262ebfaf2f06772c1a480c7d9d5f4a38e1",
    party_dv_addr=0xD185,
    party_species_addr=0xD163,
    sram_size=0x8000,
    starters={0x54: "pikachu"},
    starter_macro="yellow_us_starter.yaml",
    save_macro="yellow_us_save.yaml",
)

register(CONFIG)
