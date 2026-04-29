import numpy as np

from shiny_hunter.monitor import grid_size, update_frames
from shiny_hunter.workers import WorkerFrame


def test_grid_size_1():
    assert grid_size(1) == (1, 1)


def test_grid_size_2():
    assert grid_size(2) == (2, 1)


def test_grid_size_3():
    assert grid_size(3) == (3, 1)


def test_grid_size_4():
    assert grid_size(4) == (2, 2)


def test_grid_size_5():
    assert grid_size(5) == (3, 2)


def test_grid_size_8():
    assert grid_size(8) == (4, 2)


def test_grid_size_9():
    assert grid_size(9) == (3, 3)


def test_grid_size_16():
    assert grid_size(16) == (4, 4)


def _make_frame(worker_id: int, is_shiny: bool = False, species: int = 0xB1) -> WorkerFrame:
    return WorkerFrame(
        worker_id=worker_id,
        screen=np.zeros((144, 160, 3), dtype=np.uint8),
        species=species,
        dvs=(10, 10, 10, 10),
        is_shiny=is_shiny,
    )


def test_update_frames_inserts_new():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0))
    assert 0 in frames
    assert frames[0].is_shiny is False


def test_update_frames_overwrites_non_shiny():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0, is_shiny=False, species=0x01))
    update_frames(frames, _make_frame(0, is_shiny=False, species=0x02))
    assert frames[0].species == 0x02


def test_update_frames_shiny_not_overwritten_by_non_shiny():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0, is_shiny=True, species=0x01))
    update_frames(frames, _make_frame(0, is_shiny=False, species=0x02))
    assert frames[0].species == 0x01
    assert frames[0].is_shiny is True


def test_update_frames_shiny_overwritten_by_shiny():
    frames: dict[int, WorkerFrame] = {}
    update_frames(frames, _make_frame(0, is_shiny=True, species=0x01))
    update_frames(frames, _make_frame(0, is_shiny=True, species=0x02))
    assert frames[0].species == 0x02
    assert frames[0].is_shiny is True
