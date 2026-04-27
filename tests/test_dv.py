from shiny_hunter.dv import SHINY_ATK_VALUES, decode_dvs, is_shiny


def test_decode_nybble_split():
    # byte_atk_def = 0xAB → atk=0xA(10), def=0xB(11)
    # byte_spd_spc = 0xCD → spd=0xC(12), spc=0xD(13)
    dvs = decode_dvs(0xAB, 0xCD)
    assert dvs.atk == 10
    assert dvs.def_ == 11
    assert dvs.spd == 12
    assert dvs.spc == 13


def test_decode_boundary_values():
    dvs = decode_dvs(0x00, 0x00)
    assert (dvs.atk, dvs.def_, dvs.spd, dvs.spc) == (0, 0, 0, 0)
    dvs = decode_dvs(0xFF, 0xFF)
    assert (dvs.atk, dvs.def_, dvs.spd, dvs.spc) == (15, 15, 15, 15)


def test_hp_dv_lsb_concat():
    # Atk=15(1111), Def=10(1010), Spd=10(1010), Spc=10(1010)
    # HP = LSB(15)<<3 | LSB(10)<<2 | LSB(10)<<1 | LSB(10) = 1<<3 | 0 | 0 | 0 = 8
    dvs = decode_dvs(0xFA, 0xAA)
    assert dvs.hp == 8


def test_shiny_when_def_spd_spc_are_10_and_atk_in_set():
    for atk in SHINY_ATK_VALUES:
        byte_atk_def = (atk << 4) | 10  # def = 10
        byte_spd_spc = (10 << 4) | 10
        dvs = decode_dvs(byte_atk_def, byte_spd_spc)
        assert is_shiny(dvs), f"atk={atk} should be shiny"


def test_not_shiny_when_atk_outside_set():
    for atk in range(16):
        if atk in SHINY_ATK_VALUES:
            continue
        dvs = decode_dvs((atk << 4) | 10, (10 << 4) | 10)
        assert not is_shiny(dvs), f"atk={atk} should NOT be shiny"


def test_not_shiny_when_any_other_stat_not_10():
    base_atk_def = (10 << 4) | 10  # atk=10 (in set), def=10
    # def != 10
    for def_ in range(16):
        if def_ == 10:
            continue
        bad = (10 << 4) | def_
        assert not is_shiny(decode_dvs(bad, (10 << 4) | 10))
    # spd != 10
    for spd in range(16):
        if spd == 10:
            continue
        assert not is_shiny(decode_dvs(base_atk_def, (spd << 4) | 10))
    # spc != 10
    for spc in range(16):
        if spc == 10:
            continue
        assert not is_shiny(decode_dvs(base_atk_def, (10 << 4) | spc))


def test_shiny_atk_values_match_documented_set():
    assert SHINY_ATK_VALUES == frozenset({2, 3, 6, 7, 10, 11, 14, 15})
