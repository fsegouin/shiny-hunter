"""Spot-check Gen 2 data tables against known values."""
from shiny_hunter.gen2_data import GEN1_TO_POKEDEX, CATCH_RATE_ITEMS, GEN2_BASE_STATS


def test_gen1_to_pokedex_bulbasaur():
    assert GEN1_TO_POKEDEX[0x99] == 1

def test_gen1_to_pokedex_charmander():
    assert GEN1_TO_POKEDEX[0xB0] == 4

def test_gen1_to_pokedex_squirtle():
    assert GEN1_TO_POKEDEX[0xB1] == 7

def test_gen1_to_pokedex_pikachu():
    assert GEN1_TO_POKEDEX[0x54] == 25

def test_gen1_to_pokedex_mewtwo():
    assert GEN1_TO_POKEDEX[0x83] == 150

def test_gen1_to_pokedex_mew():
    assert GEN1_TO_POKEDEX[0x15] == 151

def test_gen1_to_pokedex_eevee():
    assert GEN1_TO_POKEDEX[0x66] == 133

def test_gen1_to_pokedex_covers_151():
    pokedex_nums = set(GEN1_TO_POKEDEX.values())
    assert pokedex_nums == set(range(1, 152))

def test_catch_rate_items_berry_mappings():
    assert CATCH_RATE_ITEMS[90] == 0xAD
    assert CATCH_RATE_ITEMS[100] == 0xAD
    assert CATCH_RATE_ITEMS[120] == 0xAD
    assert CATCH_RATE_ITEMS[135] == 0xAD
    assert CATCH_RATE_ITEMS[190] == 0xAD
    assert CATCH_RATE_ITEMS[195] == 0xAD
    assert CATCH_RATE_ITEMS[220] == 0xAD
    assert CATCH_RATE_ITEMS[250] == 0xAD
    assert CATCH_RATE_ITEMS[255] == 0xAD

def test_catch_rate_items_special():
    assert CATCH_RATE_ITEMS[25] == 0x92
    assert CATCH_RATE_ITEMS[45] == 0x53
    assert CATCH_RATE_ITEMS[50] == 0xAE

def test_catch_rate_items_count():
    assert len(CATCH_RATE_ITEMS) == 12

def test_base_stats_bulbasaur():
    hp, atk, def_, spd, sp_atk, sp_def = GEN2_BASE_STATS[1]
    assert (hp, atk, def_, spd, sp_atk, sp_def) == (45, 49, 49, 45, 65, 65)

def test_base_stats_pikachu():
    hp, atk, def_, spd, sp_atk, sp_def = GEN2_BASE_STATS[25]
    assert (hp, atk, def_, spd, sp_atk, sp_def) == (35, 55, 30, 90, 50, 40)

def test_base_stats_mewtwo():
    hp, atk, def_, spd, sp_atk, sp_def = GEN2_BASE_STATS[150]
    assert (hp, atk, def_, spd, sp_atk, sp_def) == (106, 110, 90, 130, 154, 90)

def test_base_stats_covers_151():
    assert set(GEN2_BASE_STATS.keys()) == set(range(1, 152))
