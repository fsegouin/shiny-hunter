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
