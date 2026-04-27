"""Input macro: a YAML-defined sequence of button presses for PyBoy."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml

VALID_BUTTONS = frozenset({"a", "b", "start", "select", "up", "down", "left", "right"})


class _PyBoyLike(Protocol):
    def button(self, key: str, delay: int = ...) -> None: ...
    def tick(self, count: int = ..., render: bool = ...) -> bool: ...


@dataclass(frozen=True)
class Step:
    button: str | None  # None means "no button, just tick `after` frames"
    hold: int = 2       # frames the button is held
    after: int = 8      # idle frames after release before the next step


@dataclass(frozen=True)
class Macro:
    name: str
    steps: tuple[Step, ...]

    def run(self, emu: _PyBoyLike) -> None:
        for step in self.steps:
            if step.button is not None:
                emu.button(step.button, step.hold)
                emu.tick(step.hold)
            if step.after:
                emu.tick(step.after)


def _coerce_step(raw: Any) -> Step:
    if not isinstance(raw, dict):
        raise ValueError(f"macro step must be a mapping, got {type(raw).__name__}")
    button = raw.get("button")
    if button is not None:
        button = str(button).lower()
        if button not in VALID_BUTTONS:
            raise ValueError(f"unknown button {button!r}; valid: {sorted(VALID_BUTTONS)}")
    hold = int(raw.get("hold", 2))
    after = int(raw.get("after", 8))
    if hold < 1:
        raise ValueError(f"hold must be >= 1, got {hold}")
    if after < 0:
        raise ValueError(f"after must be >= 0, got {after}")
    return Step(button=button, hold=hold, after=after)


def parse(steps: Iterable[Any], *, name: str = "<inline>") -> Macro:
    return Macro(name=name, steps=tuple(_coerce_step(s) for s in steps))


def load(path: Path | str) -> Macro:
    p = Path(path)
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{p}: top-level must be a list of steps")
    return parse(raw, name=p.name)
