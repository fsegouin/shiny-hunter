"""Record an event-log macro by polling PyBoy joypad state in windowed mode.

The user runs `shiny-hunt record --rom ... --from-state ...`. PyBoy opens
in windowed mode with the supplied save-state already loaded. On every
frame, we diff the joypad bitmap against the previous frame and append a
press/release event to the log along with the running frame index. When
the user closes the window, we serialize the log to a JSON file. Because
PyBoy is deterministic, replaying the log against the same starting
state reproduces the in-game sequence bit-for-bit.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Protocol

from .macro import VALID_BUTTONS, Event, EventMacro

BUTTONS: tuple[str, ...] = ("a", "b", "start", "select", "up", "down", "left", "right")


class _PyBoyLike(Protocol):
    def tick(self, count: int = ..., render: bool = ...) -> bool: ...
    def button_is_pressed(self, key: str) -> bool: ...
    def load_state(self, source: object) -> None: ...


def record(
    emu: _PyBoyLike,
    *,
    name: str = "<recording>",
    rom_sha1: str | None = None,
    from_state: str | None = None,
    max_frames: int | None = None,
    on_frame: Callable[[int, list[Event]], None] | None = None,
) -> EventMacro:
    """Run the emulator until the window closes (or `max_frames` elapses).

    The supplied `emu` must already have its starting state loaded; this
    keeps the recorder agnostic of how the state was obtained.

    Args:
        emu: Emulator-like object exposing `tick(1, render=True) -> bool`
             and `button_is_pressed(key) -> bool`.
        name: Macro name (used for diagnostics; not serialized).
        rom_sha1: Optional ROM SHA-1 to embed in the resulting macro for
                  later validation during replay.
        from_state: Optional path string of the starting state, embedded
                    for replay validation.
        max_frames: Hard cap on frames recorded; None means "until window
                    closes".
        on_frame: Optional callback invoked once per frame with the
                  current frame index and the list of events emitted on
                  that frame. Useful for live UI updates.

    Returns:
        EventMacro with the captured events and total_frames = the frame
        index at which recording stopped.
    """
    events: list[Event] = []
    prev: dict[str, bool] = {b: False for b in BUTTONS}
    frame = 0

    while True:
        if max_frames is not None and frame >= max_frames:
            break
        running = emu.tick(1, render=True)
        if not running:
            break
        frame += 1

        per_frame: list[Event] = []
        for b in BUTTONS:
            now = bool(emu.button_is_pressed(b))
            if now != prev[b]:
                ev = Event(frame=frame, kind=("press" if now else "release"), button=b)
                events.append(ev)
                per_frame.append(ev)
                prev[b] = now
        if on_frame is not None and per_frame:
            on_frame(frame, per_frame)

    # Release any buttons left held at end of recording so replay leaves
    # the joypad clean.
    for b, held in prev.items():
        if held:
            events.append(Event(frame=frame, kind="release", button=b))

    return EventMacro(
        name=name,
        events=tuple(events),
        total_frames=frame,
        rom_sha1=rom_sha1,
        from_state=from_state,
    )


def write(macro: EventMacro, out_path: Path) -> None:
    """Serialize an EventMacro to a JSON file consumable by `macro.load_events`."""
    import json
    from .macro import dump_events

    out_path.write_text(json.dumps(dump_events(macro), indent=2))


# Sanity: every name in BUTTONS is a valid button.
assert set(BUTTONS) <= VALID_BUTTONS
