"""GameConfig + ROM-hash-based registry."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Mapping

Region = Literal["us", "jp", "eu", "de", "fr", "it", "es"]
GameName = Literal["red", "blue", "green", "yellow"]


@dataclass(frozen=True)
class GameConfig:
    """Per-(game, region) configuration.

    All RAM addresses are absolute Game Boy memory addresses. SHA-1 must match
    the canonical ROM dump (otherwise the bot refuses to run).

    The party DV byte at `party_dv_addr` holds (Atk<<4 | Def); the next byte
    holds (Spd<<4 | Spc). For Pokémon Red/Blue (US), party slot 0 base is
    $D16B and the DV bytes are at offset 0x1B/0x1C → $D186/$D187.
    """

    game: GameName
    region: Region
    rom_sha1: str                          # lowercase hex, no separators
    party_dv_addr: int                     # high byte: Atk/Def; addr+1: Spd/Spc
    party_species_addr: int                # wPartySpecies[0]
    sram_size: int                         # bytes; Red/Blue MBC3 = 0x8000 (32KB)
    starters: Mapping[int, str]            # species_id -> canonical lowercase name
    starter_macro: str                     # filename under shiny_hunter/macros/
    save_macro: str                        # in-game SAVE macro (post-shiny commit)
    post_macro_settle_frames: int = 120


@dataclass(frozen=True)
class _RegistryEntry:
    config: GameConfig
    aliases: tuple[str, ...] = ()          # human-friendly names accepted on CLI


_BY_SHA1: dict[str, GameConfig] = {}
_BY_KEY: dict[tuple[str, str], GameConfig] = {}


def register(config: GameConfig) -> None:
    sha = config.rom_sha1.lower()
    if sha in _BY_SHA1:
        raise ValueError(f"duplicate ROM SHA-1 in registry: {sha}")
    key = (config.game, config.region)
    if key in _BY_KEY:
        raise ValueError(f"duplicate (game, region) in registry: {key}")
    _BY_SHA1[sha] = config
    _BY_KEY[key] = config


def by_sha1(sha1: str) -> GameConfig | None:
    return _BY_SHA1.get(sha1.lower())


def by_key(game: str, region: str) -> GameConfig | None:
    return _BY_KEY.get((game.lower(), region.lower()))


def all_configs() -> list[GameConfig]:
    return list(_BY_SHA1.values())


def _load_builtin() -> None:
    # Imported for side-effect: each module calls `register(...)`.
    from .games import red_us, blue_us, yellow_us  # noqa: F401
    from .games import red_jp, blue_jp, green_jp, yellow_jp  # noqa: F401


_load_builtin()
