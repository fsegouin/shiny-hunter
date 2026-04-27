from pathlib import Path

import pytest
import yaml

from shiny_hunter import macro


def test_parse_minimal():
    m = macro.parse([{"button": "a"}])
    assert len(m.steps) == 1
    assert m.steps[0].button == "a"
    assert m.steps[0].hold == 2
    assert m.steps[0].after == 8


def test_parse_full_step():
    m = macro.parse([{"button": "start", "hold": 5, "after": 100}])
    s = m.steps[0]
    assert s.button == "start"
    assert s.hold == 5
    assert s.after == 100


def test_parse_no_button_is_pure_idle():
    m = macro.parse([{"after": 30}])
    assert m.steps[0].button is None
    assert m.steps[0].after == 30


def test_parse_rejects_unknown_button():
    with pytest.raises(ValueError, match="unknown button"):
        macro.parse([{"button": "x"}])


def test_parse_rejects_bad_hold():
    with pytest.raises(ValueError):
        macro.parse([{"button": "a", "hold": 0}])


def test_parse_rejects_negative_after():
    with pytest.raises(ValueError):
        macro.parse([{"button": "a", "after": -1}])


def test_parse_rejects_non_mapping_step():
    with pytest.raises(ValueError, match="must be a mapping"):
        macro.parse(["not-a-dict"])


def test_load_round_trip(tmp_path: Path):
    src = [
        {"button": "a", "hold": 2, "after": 30},
        {"button": "b", "hold": 3, "after": 60},
    ]
    p = tmp_path / "m.yaml"
    p.write_text(yaml.safe_dump(src))
    m = macro.load(p)
    assert m.name == "m.yaml"
    assert [s.button for s in m.steps] == ["a", "b"]
    assert [s.hold for s in m.steps] == [2, 3]


class _FakePyBoy:
    def __init__(self):
        self.events: list = []

    def button(self, key, delay):
        self.events.append(("button", key, delay))

    def tick(self, count=1, render=True):
        self.events.append(("tick", count))
        return True


def test_run_pushes_button_then_idles():
    fake = _FakePyBoy()
    m = macro.parse([{"button": "a", "hold": 2, "after": 30}, {"after": 60}])
    m.run(fake)
    # First step: button + tick(2) + tick(30); second step: tick(60)
    assert fake.events == [
        ("button", "a", 2),
        ("tick", 2),
        ("tick", 30),
        ("tick", 60),
    ]


# ---------- EventMacro (JSON event-log format) ----------


class _FakeEventPyBoy:
    def __init__(self):
        self.events: list = []

    def tick(self, count=1, render=False):
        self.events.append(("tick", count))
        return True

    def button(self, key, delay):
        self.events.append(("button", key, delay))

    def button_press(self, key):
        self.events.append(("press", key))

    def button_release(self, key):
        self.events.append(("release", key))


def test_parse_events_minimal():
    em = macro.parse_events({
        "events": [
            {"frame": 10, "press": "a"},
            {"frame": 12, "release": "a"},
        ],
        "total_frames": 100,
    })
    assert len(em.events) == 2
    assert em.events[0].kind == "press" and em.events[0].button == "a"
    assert em.events[1].kind == "release" and em.events[0].frame == 10
    assert em.total_frames == 100


def test_parse_events_rejects_both_press_and_release():
    with pytest.raises(ValueError, match="both 'press' and 'release'"):
        macro.parse_events({"events": [{"frame": 0, "press": "a", "release": "a"}]})


def test_parse_events_rejects_unknown_button():
    with pytest.raises(ValueError, match="unknown button"):
        macro.parse_events({"events": [{"frame": 0, "press": "x"}]})


def test_parse_events_rejects_negative_frame():
    with pytest.raises(ValueError, match="frame must be >= 0"):
        macro.parse_events({"events": [{"frame": -1, "press": "a"}]})


def test_parse_events_total_frames_default_to_last():
    em = macro.parse_events({"events": [{"frame": 42, "press": "a"}]})
    assert em.total_frames == 42


def test_parse_events_total_frames_must_be_at_least_last():
    with pytest.raises(ValueError, match="total_frames"):
        macro.parse_events({
            "events": [{"frame": 50, "press": "a"}],
            "total_frames": 10,
        })


def test_event_macro_run_ticks_to_each_frame():
    em = macro.parse_events({
        "events": [
            {"frame": 10, "press": "a"},
            {"frame": 12, "release": "a"},
            {"frame": 50, "press": "b"},
            {"frame": 52, "release": "b"},
        ],
        "total_frames": 100,
    })
    fake = _FakeEventPyBoy()
    em.run(fake)
    assert fake.events == [
        ("tick", 10),
        ("press", "a"),
        ("tick", 2),
        ("release", "a"),
        ("tick", 38),
        ("press", "b"),
        ("tick", 2),
        ("release", "b"),
        ("tick", 48),
    ]


def test_event_macro_run_rejects_decreasing_frames():
    em = macro.EventMacro(
        name="x",
        events=(macro.Event(10, "press", "a"), macro.Event(5, "release", "a")),
        total_frames=10,
    )
    fake = _FakeEventPyBoy()
    with pytest.raises(ValueError, match="non-decreasing"):
        em.run(fake)


def test_load_dispatches_by_extension(tmp_path: Path):
    yp = tmp_path / "m.yaml"
    yp.write_text(yaml.safe_dump([{"button": "a"}]))
    jp = tmp_path / "m.json"
    jp.write_text('{"events": [{"frame": 0, "press": "a"}], "total_frames": 1}')
    assert isinstance(macro.load(yp), macro.Macro)
    assert isinstance(macro.load(jp), macro.EventMacro)


def test_load_rejects_unknown_extension(tmp_path: Path):
    p = tmp_path / "m.txt"
    p.write_text("nope")
    with pytest.raises(ValueError, match="unknown macro extension"):
        macro.load(p)


def test_dump_events_round_trips():
    src = macro.parse_events({
        "events": [
            {"frame": 1, "press": "start"},
            {"frame": 3, "release": "start"},
        ],
        "total_frames": 10,
        "rom_sha1": "deadbeef",
        "from_state": "states/red_us_bulbasaur.state",
    })
    doc = macro.dump_events(src)
    out = macro.parse_events(doc)
    assert out.events == src.events
    assert out.total_frames == src.total_frames
    assert out.rom_sha1 == "deadbeef"
    assert out.from_state == "states/red_us_bulbasaur.state"
