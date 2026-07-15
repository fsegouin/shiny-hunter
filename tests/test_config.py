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


def test_registry_has_gen2_us_and_jp():
    keys = {(c.game, c.region) for c in cfg_mod.all_configs()}
    for game in ("gold", "silver", "crystal"):
        assert (game, "us") in keys
        assert (game, "jp") in keys


def test_registry_size():
    assert len({(c.game, c.region) for c in cfg_mod.all_configs()}) == 13


def test_lookup_by_known_sha1():
    red_us = cfg_mod.by_sha1("ea9bcae617fdf159b045185467ae58b2e4a48b9a")
    assert red_us is not None
    assert red_us.game == "red"
    assert red_us.region == "us"


def test_lookup_gen2_by_known_sha1():
    gold_us = cfg_mod.by_sha1("d8b8a3600a465308c9953dfa04f0081c05bdcb94")
    assert gold_us is not None
    assert gold_us.game == "gold"
    assert gold_us.generation == 2


def test_lookup_by_alt_sha1():
    # Crystal (US) Rev 0 aliases the Rev 1 config (identical addresses).
    rev0 = cfg_mod.by_sha1("f4cd194bdee0d04ca4eac29e09b8e4e9d818c133")
    rev1 = cfg_mod.by_sha1("f2f52230b536214ef7c9924f483392993e226cfb")
    assert rev0 is not None
    assert rev0 is rev1


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
    # Gen 1: DVs at offset 0x0C of wEnemyMon; Gen 2 battle_struct: 0x06.
    for c in cfg_mod.all_configs():
        expected = 0x0C if c.generation == 1 else 0x06
        assert c.enemy_dv_addr - c.enemy_species_addr == expected


def test_gen2_party_dv_offset_is_consistent():
    # wPartyMon1 = wPartySpecies + 7; DVs at struct offset 0x15.
    for c in cfg_mod.all_configs():
        if c.generation == 2:
            assert c.party_dv_addr - c.party_species_addr == 7 + 0x15


def test_gen2_starters_are_dex_numbers():
    for c in cfg_mod.all_configs():
        if c.generation == 2:
            assert set(c.starters) == {152, 155, 158}


def test_generation_values():
    for c in cfg_mod.all_configs():
        assert c.generation in (1, 2)


def test_sram_size_is_bank_aligned():
    for c in cfg_mod.all_configs():
        assert c.sram_size % 0x2000 == 0
