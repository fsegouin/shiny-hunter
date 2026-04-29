"""Tkinter + PIL monitor grid for parallel shiny hunting."""
from __future__ import annotations

import math

from . import pokemon
from .workers import WorkerFrame

GB_W, GB_H = 160, 144
SCALE = 2
CELL_W = GB_W * SCALE
CELL_H = GB_H * SCALE
BAR_H = 20
BORDER = 2
BG_COLOR = (30, 30, 30)
SHINY_BORDER_COLOR = (0, 220, 80)
TEXT_COLOR = (220, 220, 220)
SHINY_TEXT_COLOR = (0, 255, 100)


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
        from PIL import Image, ImageDraw, ImageFont, ImageTk

        self._tk = tk
        self._Image = Image
        self._ImageDraw = ImageDraw
        self._ImageTk = ImageTk

        self.num_workers = num_workers
        self.cols, self.rows = grid_size(num_workers)
        self.cell_w = CELL_W + BORDER * 2
        self.cell_h = CELL_H + BAR_H + BORDER * 2
        self._win_w = self.cols * self.cell_w
        self._win_h = self.rows * self.cell_h
        self._frames: dict[int, WorkerFrame] = {}
        self._closed = False

        self._root = tk.Tk()
        self._root.title("shiny-hunter monitor")
        self._root.resizable(False, False)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._canvas = tk.Canvas(
            self._root, width=self._win_w, height=self._win_h,
            bg="#1e1e1e", highlightthickness=0,
        )
        self._canvas.pack()

        self._tk_image: ImageTk.PhotoImage | None = None

        try:
            self._font = ImageFont.truetype("DejaVuSansMono.ttf", 12)
        except OSError:
            self._font = ImageFont.load_default()

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
                if wf.is_shiny:
                    draw.rectangle(
                        [x, y, x + self.cell_w - 1, y + self.cell_h - 1],
                        outline=SHINY_BORDER_COLOR, width=BORDER,
                    )

                screen_img = self._Image.fromarray(wf.screen).resize(
                    (CELL_W, CELL_H), self._Image.NEAREST,
                )
                img.paste(screen_img, (x + BORDER, y + BORDER))

                label = self._label(wf)
                color = SHINY_TEXT_COLOR if wf.is_shiny else TEXT_COLOR
                draw.text((x + BORDER + 4, y + BORDER + CELL_H + 4), label, fill=color, font=self._font)
            else:
                label = f"Worker {worker_id} | waiting..."
                draw.text((x + BORDER + 4, y + BORDER + CELL_H + 4), label, fill=TEXT_COLOR, font=self._font)

        self._tk_image = self._ImageTk.PhotoImage(img)
        self._canvas.create_image(0, 0, anchor=self._tk.NW, image=self._tk_image)

        self._root.update_idletasks()
        self._root.update()
        return True

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._root.destroy()

    def _on_close(self) -> None:
        self._closed = True

    @staticmethod
    def _label(wf: WorkerFrame) -> str:
        name = pokemon.species_name(wf.species)
        a, d, s, c = wf.dvs
        shiny = "YES" if wf.is_shiny else "no"
        return f"W{wf.worker_id} | {name} | A={a} D={d} S={s} C={c} | Shiny: {shiny}"
