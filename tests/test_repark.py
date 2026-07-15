"""Tests for the pure parts of repark (macro rebasing)."""
from shiny_hunter.macro import Event, EventMacro
from shiny_hunter.repark import _LEAD_FRAMES, _rebased_macro


def _macro():
    return EventMacro(
        name="t",
        events=(
            Event(frame=68, kind="press", button="b"),
            Event(frame=73, kind="release", button="b"),
            Event(frame=820, kind="press", button="a"),
            Event(frame=825, kind="release", button="a"),
            Event(frame=960, kind="press", button="a"),
            Event(frame=965, kind="release", button="a"),
        ),
        total_frames=1191,
        rom_sha1="abc",
        from_state="orig.state",
    )


def test_rebase_drops_past_events_and_shifts():
    m = _rebased_macro(_macro(), park_frame=819, name="parked")
    assert [(e.frame, e.kind, e.button) for e in m.events] == [
        (820 - 819 + _LEAD_FRAMES, "press", "a"),
        (825 - 819 + _LEAD_FRAMES, "release", "a"),
        (960 - 819 + _LEAD_FRAMES, "press", "a"),
        (965 - 819 + _LEAD_FRAMES, "release", "a"),
    ]
    assert m.total_frames == 1191 - 819 + _LEAD_FRAMES
    assert m.rom_sha1 == "abc"


def test_rebase_total_frames_never_before_last_event():
    m = EventMacro(
        name="t",
        events=(Event(frame=100, kind="press", button="a"),
                Event(frame=105, kind="release", button="a")),
        total_frames=105,
    )
    out = _rebased_macro(m, park_frame=99, name="parked")
    assert out.total_frames >= out.events[-1].frame
