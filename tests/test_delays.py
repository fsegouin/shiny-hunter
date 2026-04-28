import pytest

from shiny_hunter.delays import seed_offset


def test_seed_offset_validates_window():
    with pytest.raises(ValueError):
        seed_offset(0, delay_window=0)
    with pytest.raises(ValueError):
        seed_offset(0, delay_window=-1)

    assert seed_offset(0, delay_window=10) == 0
    assert seed_offset(15, delay_window=10) == 5
    assert seed_offset(10, 4) == 2
