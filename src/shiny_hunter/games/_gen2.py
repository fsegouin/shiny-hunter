"""Shared constants for the Gen 2 (GSC) game configs.

Mirrors `GEN2_STARTERS` in web/src/lib/games.ts.
"""
from __future__ import annotations

# Gen 2 species bytes are National Pokédex numbers.
GEN2_STARTERS: dict[int, str] = {
    152: "chikorita",
    155: "cyndaquil",
    158: "totodile",
}
