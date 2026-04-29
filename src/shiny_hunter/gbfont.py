"""Pokemon Red/Blue bitmap font renderer.

Loads the 8x8 1bpp font tiles from pokered's font.png and renders text
with the same look as in-game dialog boxes.

font.png covers tile indices $80-$FF (A-Z, a-z, digits, punctuation).
font_extra.png covers tile indices $60-$7F (border tiles, space, bold chars).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

TILE_SIZE = 8
FONT_COLS = 16
GB_SCREEN_TILES_W = 20  # 160px / 8px per tile

_DATA_DIR = Path(__file__).parent / "data"
_FONT_PNG = _DATA_DIR / "pokered_font.png"
_FONT_EXTRA_PNG = _DATA_DIR / "pokered_font_extra.png"
_SHINY_ICON_PNG = _DATA_DIR / "shiny_icon.png"

SHINY_CHAR = "⁂"  # ⁂ — same placeholder as pokecrystal

_CHARMAP: dict[str, int] = {
    "A": 0x80, "B": 0x81, "C": 0x82, "D": 0x83, "E": 0x84,
    "F": 0x85, "G": 0x86, "H": 0x87, "I": 0x88, "J": 0x89,
    "K": 0x8A, "L": 0x8B, "M": 0x8C, "N": 0x8D, "O": 0x8E,
    "P": 0x8F, "Q": 0x90, "R": 0x91, "S": 0x92, "T": 0x93,
    "U": 0x94, "V": 0x95, "W": 0x96, "X": 0x97, "Y": 0x98,
    "Z": 0x99,
    "(": 0x9A, ")": 0x9B, ":": 0x9C, ";": 0x9D, "[": 0x9E, "]": 0x9F,
    "a": 0xA0, "b": 0xA1, "c": 0xA2, "d": 0xA3, "e": 0xA4,
    "f": 0xA5, "g": 0xA6, "h": 0xA7, "i": 0xA8, "j": 0xA9,
    "k": 0xAA, "l": 0xAB, "m": 0xAC, "n": 0xAD, "o": 0xAE,
    "p": 0xAF, "q": 0xB0, "r": 0xB1, "s": 0xB2, "t": 0xB3,
    "u": 0xB4, "v": 0xB5, "w": 0xB6, "x": 0xB7, "y": 0xB8,
    "z": 0xB9,
    "'": 0xE0,
    "-": 0xE3,
    "?": 0xE6, "!": 0xE7, ".": 0xE8,
    "/": 0xF3, ",": 0xF4,
    "0": 0xF6, "1": 0xF7, "2": 0xF8, "3": 0xF9, "4": 0xFA,
    "5": 0xFB, "6": 0xFC, "7": 0xFD, "8": 0xFE, "9": 0xFF,
    " ": 0x7F,
    "=": 0xE3,  # reuse hyphen tile as "=" stand-in
    SHINY_CHAR: 0x3F,  # Crystal's shiny sparkle icon
}

_BORDER_TL = 0x79  # ┌
_BORDER_H = 0x7A   # ─
_BORDER_TR = 0x7B  # ┐
_BORDER_V = 0x7C   # │
_BORDER_BL = 0x7D  # └
_BORDER_BR = 0x7E  # ┘

_tiles: dict[int, Image.Image] | None = None


def _load_tiles() -> dict[int, Image.Image]:
    global _tiles
    if _tiles is not None:
        return _tiles
    _tiles = {}

    # font.png: tiles $80-$FF
    sheet = Image.open(_FONT_PNG).convert("L")
    n_tiles = (sheet.width // TILE_SIZE) * (sheet.height // TILE_SIZE)
    for i in range(n_tiles):
        col = i % FONT_COLS
        row = i // FONT_COLS
        x, y = col * TILE_SIZE, row * TILE_SIZE
        _tiles[0x80 + i] = sheet.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))

    # font_extra.png: tiles $60-$7F
    extra = Image.open(_FONT_EXTRA_PNG).convert("L")
    n_extra = (extra.width // TILE_SIZE) * (extra.height // TILE_SIZE)
    for i in range(n_extra):
        col = i % FONT_COLS
        row = i // FONT_COLS
        x, y = col * TILE_SIZE, row * TILE_SIZE
        _tiles[0x60 + i] = extra.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))

    # shiny_icon.png: Crystal's shiny sparkle at tile $3F
    shiny = Image.open(_SHINY_ICON_PNG).convert("L")
    _tiles[0x3F] = shiny.crop((0, 0, TILE_SIZE, TILE_SIZE))

    return _tiles


def _get_tile(idx: int) -> Image.Image:
    tiles = _load_tiles()
    return tiles.get(idx, tiles.get(0x7F, Image.new("L", (TILE_SIZE, TILE_SIZE), 255)))


def render_textbox(lines: list[str], width_tiles: int | None = None) -> Image.Image:
    """Render lines of text inside a Pokemon-style bordered text box.

    Returns a grayscale image (white background, dark text/border).
    """
    max_len = max((len(line) for line in lines), default=0)
    if width_tiles is None:
        width_tiles = max_len + 4  # content + 1 padding each side + 2 borders
    total_w = width_tiles
    inner_w = total_w - 2
    total_h = len(lines) + 2

    img = Image.new("L", (total_w * TILE_SIZE, total_h * TILE_SIZE), 255)

    def paste(tile_idx: int, tx: int, ty: int) -> None:
        img.paste(_get_tile(tile_idx), (tx * TILE_SIZE, ty * TILE_SIZE))

    paste(_BORDER_TL, 0, 0)
    for x in range(1, total_w - 1):
        paste(_BORDER_H, x, 0)
    paste(_BORDER_TR, total_w - 1, 0)

    for row_i, line in enumerate(lines):
        y = row_i + 1
        paste(_BORDER_V, 0, y)
        for x in range(1, total_w - 1):
            paste(0x7F, x, y)
        for ci, ch in enumerate(line):
            idx = _CHARMAP.get(ch, 0x7F)
            paste(idx, ci + 1, y)
        paste(_BORDER_V, total_w - 1, y)

    paste(_BORDER_BL, 0, total_h - 1)
    for x in range(1, total_w - 1):
        paste(_BORDER_H, x, total_h - 1)
    paste(_BORDER_BR, total_w - 1, total_h - 1)

    return img
