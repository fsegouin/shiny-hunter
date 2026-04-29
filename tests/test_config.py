from shiny_hunter import config as cfg_mod


def test_registry_has_us_and_jp():
    keys = {(c.game, c.region) for c in cfg_mod.all_configs()}
    assert ("red", "us") in keys
    assert ("blue", "us") in keys
    assert ("yellow", "us") in keys
    assert ("red", "jp") in keys
    assert ("blue", "jp") in keys
    assert ("green", "jp") in keys
    assert ("yellow", "jp") in keys


def test_lookup_by_known_sha1():
    red_us = cfg_mod.by_sha1("ea9bcae617fdf159b045185467ae58b2e4a48b9a")
    assert red_us is not None
    assert red_us.game == "red"
    assert red_us.region == "us"


def test_lookup_by_unknown_sha1_returns_none():
    assert cfg_mod.by_sha1("0" * 40) is None


def test_lookup_by_key():
    c = cfg_mod.by_key("yellow", "us")
    assert c is not None
    assert "pikachu" in c.starters.values()


def test_starter_species_ids_all_in_byte_range():
    for c in cfg_mod.all_configs():
        for sid in c.starters:
            assert 0 <= sid <= 0xFF


def test_party_dv_addr_in_wram_range():
    for c in cfg_mod.all_configs():
        assert 0xC000 <= c.party_dv_addr <= 0xDFFF


def test_enemy_dv_addr_in_wram_range():
    for c in cfg_mod.all_configs():
        assert 0xC000 <= c.enemy_dv_addr <= 0xDFFF


def test_enemy_species_addr_in_wram_range():
    for c in cfg_mod.all_configs():
        assert 0xC000 <= c.enemy_species_addr <= 0xDFFF


def test_enemy_dv_species_offset_is_consistent():
    for c in cfg_mod.all_configs():
        assert c.enemy_dv_addr - c.enemy_species_addr == 0x0C


def test_sram_size_is_bank_aligned():
    for c in cfg_mod.all_configs():
        assert c.sram_size % 0x2000 == 0
