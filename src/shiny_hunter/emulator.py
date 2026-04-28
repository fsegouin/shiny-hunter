"""PyBoy 2.x wrapper.

Encapsulates the things our hunter loop needs: load/save state from bytes,
read RAM, press buttons, advance frames, dump cartridge SRAM, stop. Keeps
the PyBoy import isolated so tests of pure modules don't pull it in.
"""
from __future__ import annotations

import io
import logging
import warnings
from pathlib import Path


class Emulator:
    SRAM_BANK_SIZE = 0x2000  # 8 KiB; cart RAM is mapped at 0xA000-0xBFFF

    def __init__(
        self,
        rom_path: Path | str,
        *,
        headless: bool = True,
        sound: bool = False,
        realtime: bool = False,
    ) -> None:
        if headless:
            warnings.filterwarnings("ignore")
            logging.getLogger("pyboy").setLevel(logging.CRITICAL)

        from pyboy import PyBoy  # imported lazily

        window = "null" if headless else "SDL2"
        self._pyboy = PyBoy(str(rom_path), window=window, sound_emulated=sound)
        self._realtime = realtime
        if headless:
            # null window defaults to unlimited speed already; explicit for clarity.
            self._pyboy.set_emulation_speed(0)

    # ---- frame / input ----

    def tick(self, frames: int = 1, *, render: bool = False) -> bool:
        if self._realtime or render:
            for _ in range(frames):
                if not self._pyboy.tick(1, True):
                    return False
            return True
        return bool(self._pyboy.tick(frames, render))

    def button(self, key: str, hold_frames: int = 2) -> None:
        self._pyboy.button(key, hold_frames)

    def button_press(self, key: str) -> None:
        self._pyboy.button_press(key)

    def button_release(self, key: str) -> None:
        self._pyboy.button_release(key)

    def button_is_pressed(self, key: str) -> bool:
        """Read the Game Boy joypad register to check if a button is pressed.

        Reads 0xFF00 directly — reflects PyBoy's internal state after it
        processes SDL key events during tick(). Works regardless of host
        keyboard layout.
        """
        key = key.lower()
        if key in ('a', 'b', 'select', 'start'):
            self._pyboy.memory[0xFF00] = 0x10
            val = self._pyboy.memory[0xFF00]
            bit = {'a': 0, 'b': 1, 'select': 2, 'start': 3}[key]
        elif key in ('right', 'left', 'up', 'down'):
            self._pyboy.memory[0xFF00] = 0x20
            val = self._pyboy.memory[0xFF00]
            bit = {'right': 0, 'left': 1, 'up': 2, 'down': 3}[key]
        else:
            raise ValueError(f"unknown button: {key}")
        return (val & (1 << bit)) == 0

    # ---- memory ----

    def read_byte(self, addr: int) -> int:
        return int(self._pyboy.memory[addr])

    def read_bytes(self, addr: int, length: int) -> bytes:
        return bytes(self._pyboy.memory[addr : addr + length])

    # ---- save state ----

    def save_state(self, dest: Path | io.IOBase) -> bytes:
        """Save state to `dest` (path or writable file-like). Returns the bytes."""
        buf = io.BytesIO()
        self._pyboy.save_state(buf)
        data = buf.getvalue()
        if isinstance(dest, (str, Path)):
            Path(dest).write_bytes(data)
        else:
            dest.write(data)
        return data

    def save_state_bytes(self) -> bytes:
        """Save state and return the raw bytes without writing to disk."""
        buf = io.BytesIO()
        self._pyboy.save_state(buf)
        return buf.getvalue()

    def load_state(self, source: Path | bytes | io.IOBase) -> None:
        if isinstance(source, (str, Path)):
            with open(source, "rb") as f:
                self._pyboy.load_state(f)
        elif isinstance(source, (bytes, bytearray, memoryview)):
            self._pyboy.load_state(io.BytesIO(bytes(source)))
        else:
            self._pyboy.load_state(source)

    # ---- cartridge SRAM ----

    def dump_sram(self, sram_size: int) -> bytes:
        """Read cart battery RAM, byte-for-byte equivalent to a real .sav file.

        Uses banked memory access (`pyboy.memory[bank, 0xA000:0xC000]`) so the
        emulator's current MBC bank isn't disturbed.
        """
        if sram_size % self.SRAM_BANK_SIZE != 0:
            raise ValueError(f"sram_size {sram_size} must be a multiple of {self.SRAM_BANK_SIZE}")
        banks = sram_size // self.SRAM_BANK_SIZE
        out = bytearray(sram_size)
        for bank in range(banks):
            start = bank * self.SRAM_BANK_SIZE
            chunk = self._pyboy.memory[bank, 0xA000:0xC000]
            out[start : start + self.SRAM_BANK_SIZE] = bytes(chunk)
        return bytes(out)

    # ---- lifecycle ----

    def stop(self, *, save: bool = False) -> None:
        self._pyboy.stop(save)

    def __enter__(self) -> "Emulator":
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop(save=False)
