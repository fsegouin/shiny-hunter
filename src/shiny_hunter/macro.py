"""Input macros for PyBoy.

Two formats coexist:
  - YAML "step" macros: a list of {button, hold, after} entries. Hand-tuned;
    used by the per-region starter macros shipped under `macros/`.
  - JSON "event" macros: a frame-indexed log of press/release events,
    typically produced by `shiny-hunt record`. Replay is bit-identical
    against the same starting state because PyBoy is deterministic.

`load(path)` dispatches by extension. Both formats expose `.run(emu)` so
hunter.py doesn't care which it got.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import yaml

VALID_BUTTONS = frozenset({"a", "b", "start", "select", "up", "down", "left", "right"})


class _PyBoyLike(Protocol):
    def button(self, key: str, delay: int = ...) -> None: ...
    def button_press(self, key: str) -> None: ...
    def button_release(self, key: str) -> None: ...
    def tick(self, count: int = ..., render: bool = ...) -> bool: ...


# ---------------- YAML "step" format ----------------


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


def load_yaml(path: Path | str) -> Macro:
    p = Path(path)
    raw = yaml.safe_load(p.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{p}: top-level must be a list of steps")
    return parse(raw, name=p.name)


# ---------------- JSON "event" format ----------------


@dataclass(frozen=True)
class Event:
    frame: int
    kind: str            # "press" or "release"
    button: str

    def to_dict(self) -> dict[str, Any]:
        return {"frame": self.frame, self.kind: self.button}


@dataclass(frozen=True)
class EventMacro:
    name: str
    events: tuple[Event, ...]
    total_frames: int
    rom_sha1: str | None = None
    from_state: str | None = None

    def run(self, emu: _PyBoyLike) -> None:
        cur = 0
        for ev in self.events:
            if ev.frame < cur:
                raise ValueError(f"event frames must be non-decreasing; {ev.frame} < {cur}")
            if ev.frame > cur:
                emu.tick(ev.frame - cur)
                cur = ev.frame
            if ev.kind == "press":
                emu.button_press(ev.button)
            else:
                emu.button_release(ev.button)
        if self.total_frames > cur:
            emu.tick(self.total_frames - cur)


def _coerce_event(raw: Any) -> Event:
    if not isinstance(raw, dict):
        raise ValueError(f"event must be a mapping, got {type(raw).__name__}")
    if "frame" not in raw:
        raise ValueError(f"event missing 'frame': {raw}")
    frame = int(raw["frame"])
    if frame < 0:
        raise ValueError(f"event frame must be >= 0, got {frame}")
    if "press" in raw and "release" in raw:
        raise ValueError(f"event has both 'press' and 'release': {raw}")
    if "press" in raw:
        kind, button = "press", str(raw["press"]).lower()
    elif "release" in raw:
        kind, button = "release", str(raw["release"]).lower()
    else:
        raise ValueError(f"event must have 'press' or 'release': {raw}")
    if button not in VALID_BUTTONS:
        raise ValueError(f"unknown button {button!r}; valid: {sorted(VALID_BUTTONS)}")
    return Event(frame=frame, kind=kind, button=button)


def parse_events(doc: dict[str, Any], *, name: str = "<inline>") -> EventMacro:
    raw_events = doc.get("events", [])
    if not isinstance(raw_events, list):
        raise ValueError("'events' must be a list")
    events = tuple(_coerce_event(e) for e in raw_events)
    total = int(doc.get("total_frames", events[-1].frame if events else 0))
    if total < (events[-1].frame if events else 0):
        raise ValueError("total_frames is before the last event frame")
    return EventMacro(
        name=name,
        events=events,
        total_frames=total,
        rom_sha1=doc.get("rom_sha1"),
        from_state=doc.get("from_state"),
    )


def load_events(path: Path | str) -> EventMacro:
    p = Path(path)
    doc = json.loads(p.read_text())
    return parse_events(doc, name=p.name)


def dump_events(macro: EventMacro) -> dict[str, Any]:
    out: dict[str, Any] = {
        "events": [e.to_dict() for e in macro.events],
        "total_frames": macro.total_frames,
    }
    if macro.rom_sha1:
        out["rom_sha1"] = macro.rom_sha1
    if macro.from_state:
        out["from_state"] = macro.from_state
    return out


# ---------------- dispatch ----------------


def load(path: Path | str) -> Macro | EventMacro:
    """Load a macro by extension: .yaml -> Macro, .json -> EventMacro."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in (".yaml", ".yml"):
        return load_yaml(p)
    if suffix == ".json":
        return load_events(p)
    raise ValueError(f"{p}: unknown macro extension {suffix!r}; expected .yaml or .json")
