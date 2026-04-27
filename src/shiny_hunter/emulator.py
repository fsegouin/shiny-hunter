"""PyBoy 2.x wrapper.

Encapsulates the things our hunter loop needs: load/save state from bytes,
read RAM, press buttons, advance frames, dump cartridge SRAM, stop. Keeps
the PyBoy import isolated so tests of pure modules don't pull it in.
"""
from __future__ import annotations

import io
from pathlib import Path


class Emulator:
    SRAM_BANK_SIZE = 0x2000  # 8 KiB; cart RAM is mapped at 0xA000-0xBFFF

    def __init__(
        self,
        rom_path: Path | str,
        *,
        headless: bool = True,
        sound: bool = False,
    ) -> None:
        from pyboy import PyBoy  # imported lazily

        window = "null" if headless else "SDL2"
        self._pyboy = PyBoy(str(rom_path), window=window, sound_emulated=sound)
        if headless:
            # null window defaults to unlimited speed already; explicit for clarity.
            self._pyboy.set_emulation_speed(0)

    # ---- frame / input ----

    def tick(self, frames: int = 1, *, render: bool = False) -> bool:
        return bool(self._pyboy.tick(frames, render))

    def button(self, key: str, hold_frames: int = 2) -> None:
        self._pyboy.button(key, hold_frames)

    def button_press(self, key: str) -> None:
        self._pyboy.button_press(key)

    def button_release(self, key: str) -> None:
        self._pyboy.button_release(key)

    def button_is_pressed(self, key: str) -> bool:
        return bool(self._pyboy.button_is_pressed(key))

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
