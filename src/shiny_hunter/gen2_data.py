"""Static data tables for Gen 1 → Gen 2 conversion.

All data sourced from pret/pokecrystal disassembly:
  - GEN1_TO_POKEDEX: data/pokemon/gen1_order.asm
  - CATCH_RATE_ITEMS: data/items/catch_rate_items.asm
  - GEN2_BASE_STATS: data/pokemon/base_stats/*.asm
"""
from __future__ import annotations

# Gen 1 internal species index → Pokedex number (151 entries).
GEN1_TO_POKEDEX: dict[int, int] = {
    0x01: 112,  # Rhydon
    0x02: 115,  # Kangaskhan
    0x03: 32,   # Nidoran♂
    0x04: 35,   # Clefairy
    0x05: 21,   # Spearow
    0x06: 100,  # Voltorb
    0x07: 34,   # Nidoking
    0x08: 80,   # Slowbro
    0x09: 2,    # Ivysaur
    0x0A: 103,  # Exeggutor
    0x0B: 108,  # Lickitung
    0x0C: 102,  # Exeggcute
    0x0D: 88,   # Grimer
    0x0E: 94,   # Gengar
    0x0F: 29,   # Nidoran♀
    0x10: 31,   # Nidoqueen
    0x11: 104,  # Cubone
    0x12: 111,  # Rhyhorn
    0x13: 131,  # Lapras
    0x14: 59,   # Arcanine
    0x15: 151,  # Mew
    0x16: 130,  # Gyarados
    0x17: 90,   # Shellder
    0x18: 72,   # Tentacool
    0x19: 92,   # Gastly
    0x1A: 123,  # Scyther
    0x1B: 120,  # Staryu
    0x1C: 9,    # Blastoise
    0x1D: 127,  # Pinsir
    0x1E: 114,  # Tangela
    0x21: 58,   # Growlithe
    0x22: 95,   # Onix
    0x23: 22,   # Fearow
    0x24: 16,   # Pidgey
    0x25: 79,   # Slowpoke
    0x26: 64,   # Kadabra
    0x27: 75,   # Graveler
    0x28: 113,  # Chansey
    0x29: 67,   # Machoke
    0x2A: 122,  # Mr. Mime
    0x2B: 106,  # Hitmonlee
    0x2C: 107,  # Hitmonchan
    0x2D: 24,   # Arbok
    0x2E: 47,   # Parasect
    0x2F: 54,   # Psyduck
    0x30: 96,   # Drowzee
    0x31: 76,   # Golem
    0x33: 126,  # Magmar
    0x35: 125,  # Electabuzz
    0x36: 82,   # Magneton
    0x37: 109,  # Koffing
    0x39: 56,   # Mankey
    0x3A: 86,   # Seel
    0x3B: 50,   # Diglett
    0x3C: 128,  # Tauros
    0x40: 83,   # Farfetch'd
    0x41: 48,   # Venonat
    0x42: 149,  # Dragonite
    0x46: 84,   # Doduo
    0x47: 60,   # Poliwag
    0x48: 124,  # Jynx
    0x49: 146,  # Moltres
    0x4A: 144,  # Articuno
    0x4B: 145,  # Zapdos
    0x4C: 132,  # Ditto
    0x4D: 52,   # Meowth
    0x4E: 98,   # Krabby
    0x52: 37,   # Vulpix
    0x53: 38,   # Ninetales
    0x54: 25,   # Pikachu
    0x55: 26,   # Raichu
    0x58: 147,  # Dratini
    0x59: 148,  # Dragonair
    0x5A: 140,  # Kabuto
    0x5B: 141,  # Kabutops
    0x5C: 116,  # Horsea
    0x5D: 117,  # Seadra
    0x60: 27,   # Sandshrew
    0x61: 28,   # Sandslash
    0x62: 138,  # Omanyte
    0x63: 139,  # Omastar
    0x64: 39,   # Jigglypuff
    0x65: 40,   # Wigglytuff
    0x66: 133,  # Eevee
    0x67: 136,  # Flareon
    0x68: 135,  # Jolteon
    0x69: 134,  # Vaporeon
    0x6A: 66,   # Machop
    0x6B: 41,   # Zubat
    0x6C: 23,   # Ekans
    0x6D: 46,   # Paras
    0x6E: 61,   # Poliwhirl
    0x6F: 62,   # Poliwrath
    0x70: 13,   # Weedle
    0x71: 14,   # Kakuna
    0x72: 15,   # Beedrill
    0x74: 85,   # Dodrio
    0x75: 57,   # Primeape
    0x76: 51,   # Dugtrio
    0x77: 49,   # Venomoth
    0x78: 87,   # Dewgong
    0x7B: 10,   # Caterpie
    0x7C: 11,   # Metapod
    0x7D: 12,   # Butterfree
    0x7E: 68,   # Machamp
    0x80: 55,   # Golduck
    0x81: 97,   # Hypno
    0x82: 42,   # Golbat
    0x83: 150,  # Mewtwo
    0x84: 143,  # Snorlax
    0x85: 129,  # Magikarp
    0x88: 89,   # Muk
    0x8A: 99,   # Kingler
    0x8B: 91,   # Cloyster
    0x8D: 101,  # Electrode
    0x8E: 36,   # Clefable
    0x8F: 110,  # Weezing
    0x90: 53,   # Persian
    0x91: 105,  # Marowak
    0x93: 93,   # Haunter
    0x94: 63,   # Abra
    0x95: 65,   # Alakazam
    0x96: 17,   # Pidgeotto
    0x97: 18,   # Pidgeot
    0x98: 121,  # Starmie
    0x99: 1,    # Bulbasaur
    0x9A: 3,    # Venusaur
    0x9B: 73,   # Tentacruel
    0x9D: 118,  # Goldeen
    0x9E: 119,  # Seaking
    0xA3: 77,   # Ponyta
    0xA4: 78,   # Rapidash
    0xA5: 19,   # Rattata
    0xA6: 20,   # Raticate
    0xA7: 33,   # Nidorino
    0xA8: 30,   # Nidorina
    0xA9: 74,   # Geodude
    0xAA: 137,  # Porygon
    0xAB: 142,  # Aerodactyl
    0xAD: 81,   # Magnemite
    0xB0: 4,    # Charmander
    0xB1: 7,    # Squirtle
    0xB2: 5,    # Charmeleon
    0xB3: 8,    # Wartortle
    0xB4: 6,    # Charizard
    0xB9: 43,   # Oddish
    0xBA: 44,   # Gloom
    0xBB: 45,   # Vileplume
    0xBC: 69,   # Bellsprout
    0xBD: 70,   # Weepinbell
    0xBE: 71,   # Victreebel
}


# Catch rate values that get remapped to specific items during Time Capsule transfer.
# From pret/pokecrystal data/items/catch_rate_items.asm.
# Item IDs: BERRY=0x2D, BITTER_BERRY=0x2E, GOLD_BERRY=0x53, LEFTOVERS=0xAC
CATCH_RATE_ITEMS: dict[int, int] = {
    25:  0xAC,  # LEFTOVERS
    45:  0x2E,  # BITTER_BERRY
    50:  0x53,  # GOLD_BERRY
    90:  0x2D,  # BERRY
    100: 0x2D,  # BERRY
    120: 0x2D,  # BERRY
    135: 0x2D,  # BERRY
    190: 0x2D,  # BERRY
    195: 0x2D,  # BERRY
    220: 0x2D,  # BERRY
    250: 0x2D,  # BERRY
    255: 0x2D,  # BERRY
}


# Gen 2 base stats for the original 151 Pokemon, indexed by Pokedex number.
# Tuple order: (HP, ATK, DEF, SPD, SP_ATK, SP_DEF)
# From pret/pokecrystal data/pokemon/base_stats/.
GEN2_BASE_STATS: dict[int, tuple[int, int, int, int, int, int]] = {
    1:   (45, 49, 49, 45, 65, 65),      # Bulbasaur
    2:   (60, 62, 63, 60, 80, 80),      # Ivysaur
    3:   (80, 82, 83, 80, 100, 100),    # Venusaur
    4:   (39, 52, 43, 65, 60, 50),      # Charmander
    5:   (58, 64, 58, 80, 80, 65),      # Charmeleon
    6:   (78, 84, 78, 100, 109, 85),    # Charizard
    7:   (44, 48, 65, 43, 50, 64),      # Squirtle
    8:   (59, 63, 80, 58, 65, 80),      # Wartortle
    9:   (79, 83, 100, 78, 85, 105),    # Blastoise
    10:  (45, 30, 35, 45, 20, 20),      # Caterpie
    11:  (50, 20, 55, 30, 25, 25),      # Metapod
    12:  (60, 45, 50, 70, 80, 80),      # Butterfree
    13:  (40, 35, 30, 50, 20, 20),      # Weedle
    14:  (45, 25, 50, 35, 25, 25),      # Kakuna
    15:  (65, 80, 40, 75, 45, 80),      # Beedrill
    16:  (40, 45, 40, 56, 35, 35),      # Pidgey
    17:  (63, 60, 55, 71, 50, 50),      # Pidgeotto
    18:  (83, 80, 75, 91, 70, 70),      # Pidgeot
    19:  (30, 56, 35, 72, 25, 35),      # Rattata
    20:  (55, 81, 60, 97, 50, 70),      # Raticate
    21:  (40, 60, 30, 70, 31, 31),      # Spearow
    22:  (65, 90, 65, 100, 61, 61),     # Fearow
    23:  (35, 60, 44, 55, 40, 54),      # Ekans
    24:  (60, 85, 69, 80, 65, 79),      # Arbok
    25:  (35, 55, 30, 90, 50, 40),      # Pikachu
    26:  (60, 90, 55, 100, 90, 80),     # Raichu
    27:  (50, 75, 85, 40, 20, 30),      # Sandshrew
    28:  (75, 100, 110, 65, 45, 55),    # Sandslash
    29:  (55, 47, 52, 41, 40, 40),      # Nidoran♀
    30:  (70, 62, 67, 56, 55, 55),      # Nidorina
    31:  (90, 82, 87, 76, 75, 85),      # Nidoqueen
    32:  (46, 57, 40, 50, 40, 40),      # Nidoran♂
    33:  (61, 72, 57, 65, 55, 55),      # Nidorino
    34:  (81, 92, 77, 85, 85, 75),      # Nidoking
    35:  (70, 45, 48, 35, 60, 65),      # Clefairy
    36:  (95, 70, 73, 60, 85, 90),      # Clefable
    37:  (38, 41, 40, 65, 50, 65),      # Vulpix
    38:  (73, 76, 75, 100, 81, 100),    # Ninetales
    39:  (115, 45, 20, 20, 45, 25),     # Jigglypuff
    40:  (140, 70, 45, 45, 75, 50),     # Wigglytuff
    41:  (40, 45, 35, 55, 30, 40),      # Zubat
    42:  (75, 80, 70, 90, 65, 75),      # Golbat
    43:  (45, 50, 55, 30, 75, 65),      # Oddish
    44:  (60, 65, 70, 40, 85, 75),      # Gloom
    45:  (75, 80, 85, 50, 100, 90),     # Vileplume
    46:  (35, 70, 55, 25, 45, 55),      # Paras
    47:  (60, 95, 80, 30, 60, 80),      # Parasect
    48:  (60, 55, 50, 45, 40, 55),      # Venonat
    49:  (70, 65, 60, 90, 90, 75),      # Venomoth
    50:  (10, 55, 25, 95, 35, 45),      # Diglett
    51:  (35, 80, 50, 120, 50, 70),     # Dugtrio
    52:  (40, 45, 35, 90, 40, 40),      # Meowth
    53:  (65, 70, 60, 115, 65, 65),     # Persian
    54:  (50, 52, 48, 55, 65, 50),      # Psyduck
    55:  (80, 82, 78, 85, 95, 80),      # Golduck
    56:  (40, 80, 35, 70, 35, 45),      # Mankey
    57:  (65, 105, 60, 95, 60, 70),     # Primeape
    58:  (55, 70, 45, 60, 70, 50),      # Growlithe
    59:  (90, 110, 80, 95, 100, 80),    # Arcanine
    60:  (40, 50, 40, 90, 40, 40),      # Poliwag
    61:  (65, 65, 65, 90, 50, 50),      # Poliwhirl
    62:  (90, 85, 95, 70, 70, 90),      # Poliwrath
    63:  (25, 20, 15, 90, 105, 55),     # Abra
    64:  (40, 35, 30, 105, 120, 70),    # Kadabra
    65:  (55, 50, 45, 120, 135, 85),    # Alakazam
    66:  (70, 80, 50, 35, 35, 35),      # Machop
    67:  (80, 100, 70, 45, 50, 60),     # Machoke
    68:  (90, 130, 80, 55, 65, 85),     # Machamp
    69:  (50, 75, 35, 40, 70, 30),      # Bellsprout
    70:  (65, 90, 50, 55, 85, 45),      # Weepinbell
    71:  (80, 105, 65, 70, 100, 60),    # Victreebel
    72:  (40, 40, 35, 70, 50, 100),     # Tentacool
    73:  (80, 70, 65, 100, 80, 120),    # Tentacruel
    74:  (40, 80, 100, 20, 30, 30),     # Geodude
    75:  (55, 95, 115, 35, 45, 45),     # Graveler
    76:  (80, 110, 130, 45, 55, 65),    # Golem
    77:  (50, 85, 55, 90, 65, 65),      # Ponyta
    78:  (65, 100, 70, 105, 80, 80),    # Rapidash
    79:  (90, 65, 65, 15, 40, 40),      # Slowpoke
    80:  (95, 75, 110, 30, 100, 80),    # Slowbro
    81:  (25, 35, 70, 45, 95, 55),      # Magnemite
    82:  (50, 60, 95, 70, 120, 70),     # Magneton
    83:  (52, 65, 55, 60, 58, 62),      # Farfetch'd
    84:  (35, 85, 45, 75, 35, 35),      # Doduo
    85:  (60, 110, 70, 100, 60, 60),    # Dodrio
    86:  (65, 45, 55, 45, 45, 70),      # Seel
    87:  (90, 70, 80, 70, 70, 95),      # Dewgong
    88:  (80, 80, 50, 25, 40, 50),      # Grimer
    89:  (105, 105, 75, 50, 65, 100),   # Muk
    90:  (30, 65, 100, 40, 45, 25),     # Shellder
    91:  (50, 95, 180, 70, 85, 45),     # Cloyster
    92:  (30, 35, 30, 80, 100, 35),     # Gastly
    93:  (45, 50, 45, 95, 115, 55),     # Haunter
    94:  (60, 65, 60, 110, 130, 75),    # Gengar
    95:  (35, 45, 160, 70, 30, 45),     # Onix
    96:  (60, 48, 45, 42, 43, 90),      # Drowzee
    97:  (85, 73, 70, 67, 73, 115),     # Hypno
    98:  (30, 105, 90, 50, 25, 25),     # Krabby
    99:  (55, 130, 115, 75, 50, 50),    # Kingler
    100: (40, 30, 50, 100, 55, 55),     # Voltorb
    101: (60, 50, 70, 140, 80, 80),     # Electrode
    102: (60, 40, 80, 40, 60, 45),      # Exeggcute
    103: (95, 95, 85, 55, 125, 65),     # Exeggutor
    104: (50, 50, 95, 35, 40, 50),      # Cubone
    105: (60, 80, 110, 45, 50, 80),     # Marowak
    106: (50, 120, 53, 87, 35, 110),    # Hitmonlee
    107: (50, 105, 79, 76, 35, 110),    # Hitmonchan
    108: (90, 55, 75, 30, 60, 75),      # Lickitung
    109: (40, 65, 95, 35, 60, 45),      # Koffing
    110: (65, 90, 120, 60, 85, 70),     # Weezing
    111: (80, 85, 95, 25, 30, 30),      # Rhyhorn
    112: (105, 130, 120, 40, 45, 45),   # Rhydon
    113: (250, 5, 5, 50, 35, 105),      # Chansey
    114: (65, 55, 115, 60, 100, 40),    # Tangela
    115: (105, 95, 80, 90, 40, 80),     # Kangaskhan
    116: (30, 40, 70, 60, 70, 25),      # Horsea
    117: (55, 65, 95, 85, 95, 45),      # Seadra
    118: (45, 67, 60, 63, 35, 50),      # Goldeen
    119: (80, 92, 65, 68, 65, 80),      # Seaking
    120: (30, 45, 55, 85, 70, 55),      # Staryu
    121: (60, 75, 85, 115, 100, 85),    # Starmie
    122: (40, 45, 65, 90, 100, 120),    # Mr. Mime
    123: (70, 110, 80, 105, 55, 80),    # Scyther
    124: (65, 50, 35, 95, 115, 95),     # Jynx
    125: (65, 83, 57, 105, 95, 85),     # Electabuzz
    126: (65, 95, 57, 93, 100, 85),     # Magmar
    127: (65, 125, 100, 85, 55, 70),    # Pinsir
    128: (75, 100, 95, 110, 40, 70),    # Tauros
    129: (20, 10, 55, 80, 15, 20),      # Magikarp
    130: (95, 125, 79, 81, 60, 100),    # Gyarados
    131: (130, 85, 80, 60, 85, 95),     # Lapras
    132: (48, 48, 48, 48, 48, 48),      # Ditto
    133: (55, 55, 50, 55, 45, 65),      # Eevee
    134: (130, 65, 60, 65, 110, 95),    # Vaporeon
    135: (65, 65, 60, 130, 110, 95),    # Jolteon
    136: (65, 130, 60, 65, 95, 110),    # Flareon
    137: (65, 60, 70, 40, 85, 75),      # Porygon
    138: (35, 40, 100, 35, 90, 55),     # Omanyte
    139: (70, 60, 125, 55, 115, 70),    # Omastar
    140: (30, 80, 90, 55, 55, 45),      # Kabuto
    141: (60, 115, 105, 80, 65, 70),    # Kabutops
    142: (80, 105, 65, 130, 60, 75),    # Aerodactyl
    143: (160, 110, 65, 30, 65, 110),   # Snorlax
    144: (90, 85, 100, 85, 95, 125),    # Articuno
    145: (90, 90, 85, 100, 125, 90),    # Zapdos
    146: (90, 100, 90, 90, 125, 85),    # Moltres
    147: (41, 64, 45, 50, 50, 50),      # Dratini
    148: (61, 84, 65, 70, 70, 70),      # Dragonair
    149: (91, 134, 95, 80, 100, 100),   # Dragonite
    150: (106, 110, 90, 130, 154, 90),  # Mewtwo
    151: (100, 100, 100, 100, 100, 100),# Mew
}
