"""Recorder unit tests using a scripted fake PyBoy."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shiny_hunter import macro, recorder


class _ScriptedPyBoy:
    """Plays back a frame-by-frame button-press script.

    `script[i]` is the dict of {button: bool} active during frame i+1
    (frame numbering starts at 1, matching the recorder). After the
    script is exhausted, `tick` returns False to signal "window closed".
    """

    def __init__(self, script: list[dict[str, bool]]):
        self._script = script
        self._frame = 0
        self._cur: dict[str, bool] = {b: False for b in recorder.BUTTONS}

    def tick(self, count: int = 1, render: bool = False) -> bool:
        assert count == 1, "recorder must single-step"
        if self._frame >= len(self._script):
            return False
        self._cur = {b: self._script[self._frame].get(b, False) for b in recorder.BUTTONS}
        self._frame += 1
        return True

    def button_is_pressed(self, key: str) -> bool:
        return self._cur.get(key, False)


def test_record_logs_press_then_release():
    """A single press held for two frames yields exactly one press + one release."""
    script = [
        {"a": False},
        {"a": True},
        {"a": True},
        {"a": False},
        {"a": False},
    ]
    em = recorder.record(_ScriptedPyBoy(script), name="t")
    assert em.total_frames == 5
    assert [(e.frame, e.kind, e.button) for e in em.events] == [
        (2, "press", "a"),
        (4, "release", "a"),
    ]


def test_record_handles_overlapping_buttons():
    script = [
        {"a": True},
        {"a": True, "b": True},
        {"b": True},
        {},
    ]
    em = recorder.record(_ScriptedPyBoy(script), name="t")
    kinds = [(e.frame, e.kind, e.button) for e in em.events]
    assert kinds == [
        (1, "press", "a"),
        (2, "press", "b"),
        (3, "release", "a"),
        (4, "release", "b"),
    ]


def test_record_emits_release_for_button_held_at_end():
    """If a button is still held when the window closes, recorder appends a final release."""
    script = [
        {"a": True},
        {"a": True},
    ]
    em = recorder.record(_ScriptedPyBoy(script), name="t")
    assert em.total_frames == 2
    assert [(e.frame, e.kind, e.button) for e in em.events] == [
        (1, "press", "a"),
        (2, "release", "a"),
    ]


def test_record_max_frames_caps_recording():
    script = [{"a": True}] * 1000
    em = recorder.record(_ScriptedPyBoy(script), name="t", max_frames=10)
    assert em.total_frames == 10


def test_record_embeds_metadata():
    em = recorder.record(
        _ScriptedPyBoy([{}]),
        name="x",
        rom_sha1="deadbeef",
        from_state="states/foo.state",
    )
    assert em.rom_sha1 == "deadbeef"
    assert em.from_state == "states/foo.state"


def test_record_invokes_on_frame_callback():
    seen: list[tuple[int, int]] = []
    script = [{"a": True}, {"a": True}, {"a": False}]
    recorder.record(
        _ScriptedPyBoy(script),
        name="t",
        on_frame=lambda f, evs: seen.append((f, len(evs))),
    )
    # Callback fires only on frames where events occurred (1 and 3).
    assert seen == [(1, 1), (3, 1)]


def test_write_round_trips_through_load_events(tmp_path: Path):
    em = recorder.record(
        _ScriptedPyBoy([{}, {"a": True}, {}]),
        name="t",
        rom_sha1="abc123",
        from_state="states/r.state",
    )
    out = tmp_path / "rec.json"
    recorder.write(em, out)

    doc = json.loads(out.read_text())
    assert doc["rom_sha1"] == "abc123"
    assert doc["from_state"] == "states/r.state"

    reloaded = macro.load_events(out)
    assert reloaded.events == em.events
    assert reloaded.total_frames == em.total_frames


def test_recording_replays_against_fresh_emulator():
    """End-to-end: record a script, then replay the macro through a logging fake;
    verify the replay produces the same press/release ordering at the same frames."""
    script = [
        {},
        {"a": True},
        {"a": True},
        {},
        {"start": True},
        {},
    ]
    em = recorder.record(_ScriptedPyBoy(script), name="t")

    class _ReplayFake:
        def __init__(self):
            self.log: list = []
            self.frame = 0

        def tick(self, count=1, render=False):
            self.frame += count
            self.log.append(("tick", count))
            return True

        def button(self, key, delay):  # not used by EventMacro
            self.log.append(("button", key, delay))

        def button_press(self, key):
            self.log.append(("press", self.frame, key))

        def button_release(self, key):
            self.log.append(("release", self.frame, key))

    fake = _ReplayFake()
    em.run(fake)

    presses = [(e[1], e[2]) for e in fake.log if e[0] in ("press", "release")]
    expected = [(e.frame, e.button) for e in em.events]
    assert presses == expected
