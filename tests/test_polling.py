"""Tests for early-exit species polling."""
from __future__ import annotations

from shiny_hunter.dv import DVs, decode_dvs
from shiny_hunter.macro import Macro, Step, EventMacro, Event
from shiny_hunter.polling import run_until_species

SPECIES_ADDR = 0xD164
DV_ADDR = 0xD186


class _FakeEmulator:
    """Fake that sets species at a known frame and tracks total ticks."""

    def __init__(self, species_at_frame: int, species: int = 0x99,
                 dv_bytes: tuple[int, int] = (0xAA, 0xAA)):
        self.species_at_frame = species_at_frame
        self._species = species
        self._dv_bytes = dv_bytes
        self.frame = 0
        self.buttons_pressed: list[tuple[int, str]] = []

    def tick(self, frames: int = 1, *, render: bool = False) -> bool:
        self.frame += frames
        return True

    def button(self, key: str, hold_frames: int = 2) -> None:
        self.buttons_pressed.append((self.frame, key))

    def button_press(self, key: str) -> None:
        self.buttons_pressed.append((self.frame, f"+{key}"))

    def button_release(self, key: str) -> None:
        self.buttons_pressed.append((self.frame, f"-{key}"))

    def read_byte(self, addr: int) -> int:
        if addr == SPECIES_ADDR and self.frame >= self.species_at_frame:
            return self._species
        return 0

    def read_bytes(self, addr: int, length: int) -> bytes:
        if addr == DV_ADDR and self.frame >= self.species_at_frame:
            return bytes(self._dv_bytes)
        return b"\x00" * length


def test_polls_until_species_appears():
    m = Macro(name="t", steps=(
        Step(button="a", hold=2, after=60),
        Step(button="a", hold=2, after=60),
    ))
    emu = _FakeEmulator(species_at_frame=150, species=0x99, dv_bytes=(0xAA, 0xAA))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0x99
    assert dvs.atk == 10
    assert dvs.def_ == 10
    assert frames == 150


def test_polls_with_event_macro():
    m = EventMacro(
        name="t",
        events=(
            Event(frame=10, kind="press", button="a"),
            Event(frame=12, kind="release", button="a"),
        ),
        total_frames=500,
    )
    emu = _FakeEmulator(species_at_frame=80, species=0xB0, dv_bytes=(0x2A, 0xAA))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0xB0
    assert frames == 80


def test_hard_cap_returns_zero_species():
    m = Macro(name="t", steps=(Step(button="a", hold=2, after=8),))
    emu = _FakeEmulator(species_at_frame=99999)
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR, hard_cap=100,
    )
    assert species == 0
    assert frames <= 100 + 10  # button frames + hard_cap
