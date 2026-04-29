"""Tkinter + PIL monitor grid for parallel shiny hunting."""
from __future__ import annotations

import math
import signal
import time
from pathlib import Path

from . import pokemon
from .workers import WorkerFrame

GB_W, GB_H = 160, 144
SCALE = 2
CELL_W = GB_W * SCALE
CELL_H = GB_H * SCALE
BORDER = 2
BG_COLOR = (30, 30, 30)
SHINY_BORDER_COLOR = (0, 220, 80)


def grid_size(n: int) -> tuple[int, int]:
    """Compute (cols, rows) for n workers. Prefer wider-than-tall layouts."""
    if n <= 0:
        return (1, 1)
    rows = max(1, math.floor(math.sqrt(n)))
    cols = math.ceil(n / rows)
    return (cols, rows)


def update_frames(frames: dict[int, WorkerFrame], new: WorkerFrame) -> None:
    """Update the frame dict. A non-shiny frame never overwrites a shiny one."""
    existing = frames.get(new.worker_id)
    if existing is not None and existing.is_shiny and not new.is_shiny:
        return
    frames[new.worker_id] = new


class MonitorWindow:
    def __init__(self, num_workers: int) -> None:
        import tkinter as tk
        from PIL import Image, ImageDraw, ImageTk

        self._tk = tk
        self._Image = Image
        self._ImageDraw = ImageDraw
        self._ImageTk = ImageTk

        self.num_workers = num_workers
        self.cols, self.rows = grid_size(num_workers)
        self.cell_w = CELL_W + BORDER * 2
        self.cell_h = CELL_H + BORDER * 2
        self._win_w = self.cols * self.cell_w
        self._win_h = self.rows * self.cell_h
        self._frames: dict[int, WorkerFrame] = {}
        self._closed = False

        self._root = tk.Tk()
        self._root.title("shiny-hunter monitor")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._root.bind("<Escape>", lambda _: self._on_close())
        self._root.focus_force()

        self._canvas = tk.Canvas(
            self._root, width=self._win_w, height=self._win_h,
            bg="#1e1e1e", highlightthickness=0,
        )
        self._canvas.pack()

        self._tk_image: ImageTk.PhotoImage | None = None
        self.last_image: Image.Image | None = None

    def update(self, frame: WorkerFrame) -> None:
        update_frames(self._frames, frame)

    def render(self) -> bool:
        """Composite the grid and update the tkinter window. Returns False if closed."""
        if self._closed:
            return False

        img = self._Image.new("RGB", (self._win_w, self._win_h), BG_COLOR)
        draw = self._ImageDraw.Draw(img)

        for worker_id in range(self.num_workers):
            col = worker_id % self.cols
            row = worker_id // self.cols
            x = col * self.cell_w
            y = row * self.cell_h

            wf = self._frames.get(worker_id)
            if wf is not None:
                screen_img = self._Image.fromarray(wf.screen).resize(
                    (CELL_W, CELL_H), self._Image.NEAREST,
                )
                img.paste(screen_img, (x + BORDER, y + BORDER))

                textbox = self._make_textbox(wf)
                textbox_rgb = self._Image.merge("RGB", (textbox, textbox, textbox))
                img.paste(textbox_rgb, (x + BORDER, y + BORDER))

                if wf.is_shiny:
                    draw.rectangle(
                        [x, y, x + self.cell_w - 1, y + self.cell_h - 1],
                        outline=SHINY_BORDER_COLOR, width=BORDER,
                    )

        self.last_image = img
        try:
            self._tk_image = self._ImageTk.PhotoImage(img)
            self._canvas.create_image(0, 0, anchor=self._tk.NW, image=self._tk_image)
            self._root.update_idletasks()
            self._root.update()
        except self._tk.TclError:
            self._closed = True
            return False
        return not self._closed

    def show_message(self, text: str) -> None:
        """Show a centered Pokemon-style textbox over the grid."""
        if self._closed:
            return
        from .gbfont import render_textbox

        box = render_textbox([text])
        scale = 4
        box_scaled = box.resize((box.width * scale, box.height * scale), resample=0)
        box_rgb = self._Image.merge("RGB", (box_scaled, box_scaled, box_scaled))
        cx = (self._win_w - box_rgb.width) // 2
        cy = (self._win_h - box_rgb.height) // 2

        if self.last_image is not None:
            overlay = self.last_image.copy()
            overlay.paste(box_rgb, (cx, cy))
        else:
            overlay = self._Image.new("RGB", (self._win_w, self._win_h), BG_COLOR)
            overlay.paste(box_rgb, (cx, cy))

        try:
            self._tk_image = self._ImageTk.PhotoImage(overlay)
            self._canvas.create_image(0, 0, anchor=self._tk.NW, image=self._tk_image)
            self._root.update_idletasks()
            self._root.update()
        except self._tk.TclError:
            pass

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._root.destroy()
            except Exception:
                pass

    def _on_close(self) -> None:
        if not self._closed:
            self._closed = True
            self._root.destroy()

    @staticmethod
    def _make_textbox(wf: WorkerFrame) -> "Image.Image":
        from .gbfont import render_textbox, GB_SCREEN_TILES_W, SHINY_CHAR

        name = pokemon.species_name(wf.species).upper()
        a, d, s, c = wf.dvs
        hp = ((a & 1) << 3) | ((d & 1) << 2) | ((s & 1) << 1) | (c & 1)
        lines = [
            f"W{wf.worker_id} {name}",
            f"ATK {a:>2} DEF {d:>2}",
            f"SPD {s:>2} SPC {c:>2} HP{hp:>2}",
        ]
        if wf.is_shiny:
            lines.append(f"{SHINY_CHAR}SHINY!")
        box = render_textbox(lines, width_tiles=GB_SCREEN_TILES_W)
        return box.resize((box.width * SCALE, box.height * SCALE), resample=0)


class GifRecorder:
    """Captures monitor frames and assembles a speed-adjusted GIF."""

    def __init__(
        self,
        target_duration: float = 10.0,
        post_shiny_duration: float = 2.0,
        capture_interval: float = 0.15,
    ) -> None:
        self._target_duration = target_duration
        self._post_shiny_duration = post_shiny_duration
        self._capture_interval = capture_interval
        self._frames: list = []
        self._timestamps: list[float] = []
        self._shiny_time: float | None = None
        self._last_capture: float = 0.0
        self._done = False

    @property
    def should_stop(self) -> bool:
        return self._done

    def capture(self, img: "Image.Image") -> None:
        if self._done:
            return
        now = time.monotonic()
        if now - self._last_capture < self._capture_interval:
            return
        self._frames.append(img.copy())
        self._timestamps.append(now)
        self._last_capture = now

        if self._shiny_time is not None and now - self._shiny_time >= self._post_shiny_duration:
            self._done = True

    def mark_shiny(self) -> None:
        if self._shiny_time is None:
            self._shiny_time = time.monotonic()

    def save(self, path: Path) -> None:
        from PIL import Image

        if not self._frames:
            return

        prev_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        try:
            self._write_gif(path, Image)
        finally:
            signal.signal(signal.SIGINT, prev_handler)

    def _write_gif(self, path: Path, Image: type) -> None:
        if self._shiny_time is not None:
            shiny_idx = next(
                (i for i, t in enumerate(self._timestamps) if t >= self._shiny_time),
                len(self._frames),
            )
            pre_count = max(shiny_idx, 1)
            post_count = len(self._frames) - pre_count

            pre_target = self._target_duration - self._post_shiny_duration
            durations: list[int] = []
            if pre_count:
                ms = max(int(pre_target * 1000 / pre_count), 20)
                durations.extend([ms] * pre_count)
            if post_count:
                ms = max(int(self._post_shiny_duration * 1000 / post_count), 20)
                durations.extend([ms] * post_count)
            durations[-1] = 3000
        else:
            ms = max(int(self._target_duration * 1000 / len(self._frames)), 20)
            durations = [ms] * len(self._frames)
            durations[-1] = 2000

        palette_frames = [f.quantize(colors=256, method=Image.Quantize.MEDIANCUT) for f in self._frames]
        palette_frames[0].save(
            path,
            save_all=True,
            append_images=palette_frames[1:],
            duration=durations,
            loop=0,
        )
