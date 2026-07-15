"""Tests for early-exit species polling."""
from __future__ import annotations

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


class _FakeGbcEmulator(_FakeEmulator):
    """CGB fake: SVBK maps a garbage bank for a window of frames."""

    def __init__(self, *args, banked_frames: range, **kwargs):
        super().__init__(*args, **kwargs)
        self.banked_frames = banked_frames

    def read_byte(self, addr: int) -> int:
        if addr == 0xFF70:
            return 5 if self.frame in self.banked_frames else 1
        if self.frame in self.banked_frames and 0xD000 <= addr <= 0xDFFF:
            return 0x7F  # garbage from the wrong WRAM bank
        return super().read_byte(addr)

    def read_bytes(self, addr: int, length: int) -> bytes:
        if self.frame in self.banked_frames and 0xD000 <= addr <= 0xDFFF:
            return b"\x7f" * length
        return super().read_bytes(addr, length)


def test_wram_bank_guard_skips_banked_frames():
    m = Macro(name="t", steps=(Step(button="a", hold=2, after=8),))
    # Garbage bank mapped from frame 50 until the species appears at 150.
    emu = _FakeGbcEmulator(
        species_at_frame=150, species=158, dv_bytes=(0xEA, 0xAA),
        banked_frames=range(50, 150),
    )
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
        guard_wram_bank=True,
    )
    assert species == 158  # not 0x7F garbage
    assert (dvs.atk, dvs.def_) == (14, 10)
    assert frames == 150


def test_without_guard_banked_frames_are_read():
    m = Macro(name="t", steps=(Step(button="a", hold=2, after=8),))
    emu = _FakeGbcEmulator(
        species_at_frame=150, species=158, dv_bytes=(0xEA, 0xAA),
        banked_frames=range(50, 150),
    )
    species, _, _ = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0x7F  # demonstrates why the guard exists


def test_early_exit_during_macro():
    # Species appears at frame 100, but the macro has trailing events out
    # to frame 500 — polling during the macro should exit at ~100.
    m = EventMacro(
        name="t",
        events=(
            Event(frame=10, kind="press", button="a"),
            Event(frame=12, kind="release", button="a"),
            Event(frame=500, kind="press", button="a"),
            Event(frame=502, kind="release", button="a"),
        ),
        total_frames=600,
    )
    emu = _FakeEmulator(species_at_frame=100, species=0x9B, dv_bytes=(0xEA, 0xAA))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0x9B
    assert frames == 100  # not 500+


def test_no_early_exit_when_slot_starts_occupied():
    # Static-hunt safety: if the slot already holds stale data at macro
    # start, mid-macro polling must be disabled — otherwise we'd latch the
    # stale mon instantly. Result is read only after the macro completes.
    m = EventMacro(
        name="t",
        events=(
            Event(frame=10, kind="press", button="a"),
            Event(frame=12, kind="release", button="a"),
            Event(frame=200, kind="press", button="a"),
            Event(frame=202, kind="release", button="a"),
        ),
        total_frames=300,
    )
    emu = _FakeEmulator(species_at_frame=0, species=0x42, dv_bytes=(0x11, 0x22))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0x42
    assert frames == 203  # macro end (202 events + 1 poll frame), no exit at frame 1


class _FakeEmptyPartyEmulator(_FakeEmulator):
    """Empty party reads the 0xFF species-list terminator, not 0."""

    def read_byte(self, addr: int) -> int:
        if addr == SPECIES_ADDR and self.frame < self.species_at_frame:
            return 0xFF
        return super().read_byte(addr)


def test_early_exit_with_empty_party_terminator():
    # An empty party shows 0xFF at wPartySpecies[0]; mid-macro polling must
    # still activate, and must not latch the terminator itself.
    m = EventMacro(
        name="t",
        events=(
            Event(frame=10, kind="press", button="a"),
            Event(frame=12, kind="release", button="a"),
            Event(frame=500, kind="press", button="a"),
            Event(frame=502, kind="release", button="a"),
        ),
        total_frames=600,
    )
    emu = _FakeEmptyPartyEmulator(species_at_frame=100, species=0x9B, dv_bytes=(0xEA, 0xAA))
    species, dvs, frames = run_until_species(
        emu, m, species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
    )
    assert species == 0x9B
    assert frames == 100


def test_gen2_never_latches_party_terminator_after_macro():
    # Gen 2: 0xFF at wPartySpecies[0] means an empty party, never a species.
    # Even with junk at the DV offset, the post-macro poll must not return it
    # (Gen 1 glitch hunts still may — see accept_ff_after_macro).
    m = EventMacro(
        name="t",
        events=(Event(frame=10, kind="press", button="a"),
                Event(frame=12, kind="release", button="a")),
        total_frames=20,
    )

    class _TerminatorEmu(_FakeEmulator):
        def read_byte(self, addr: int) -> int:
            if addr == 0xFF70:
                return 1  # WRAM bank 1 mapped
            if addr == SPECIES_ADDR:
                return 0xFF  # empty party
            return 0

        def read_bytes(self, addr: int, length: int) -> bytes:
            return b"\x7f" * length  # junk at the DV offset

    species, _, _ = run_until_species(
        _TerminatorEmu(species_at_frame=0), m,
        species_addr=SPECIES_ADDR, dv_addr=DV_ADDR,
        hard_cap=5, guard_wram_bank=True,
    )
    assert species == 0  # not 0xFF
