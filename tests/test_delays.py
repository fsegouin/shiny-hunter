import pytest

from shiny_hunter.delays import attempt_cap, delay_for_attempt, seed_offset


def test_delay_for_attempt_walks_window_without_replacement():
    assert [delay_for_attempt(0, n, 4) for n in range(1, 5)] == [0, 1, 2, 3]
    assert [delay_for_attempt(2, n, 4) for n in range(1, 5)] == [2, 3, 0, 1]


def test_delay_for_attempt_rejects_invalid_attempt():
    with pytest.raises(ValueError, match="attempt"):
        delay_for_attempt(0, 0)


def test_seed_offset_and_attempt_cap_validate_window():
    assert seed_offset(10, 4) == 2
    assert attempt_cap(10, 4) == 4
    with pytest.raises(ValueError, match="delay_window"):
        seed_offset(0, 0)
