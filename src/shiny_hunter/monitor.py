"""Tkinter + PIL monitor grid for parallel shiny hunting."""
from __future__ import annotations

import math

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

        self._canvas = tk.Canvas(
            self._root, width=self._win_w, height=self._win_h,
            bg="#1e1e1e", highlightthickness=0,
        )
        self._canvas.pack()

        self._tk_image: ImageTk.PhotoImage | None = None

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
    def _make_textbox(wf: WorkerFrame) -> "Image.Image":
        from .gbfont import render_textbox, GB_SCREEN_TILES_W, SHINY_CHAR

        name = pokemon.species_name(wf.species).upper()
        a, d, s, c = wf.dvs
        inner_w = GB_SCREEN_TILES_W - 2
        dv_line = f"ATK {a:>2} DEF {d:>2} SPD {s:>2} SPC {c:>2}"
        if len(dv_line) > inner_w:
            lines = [
                f"W{wf.worker_id} {name}",
                f"ATK {a:>2} DEF {d:>2}",
                f"SPD {s:>2} SPC {c:>2}",
            ]
        else:
            lines = [
                f"W{wf.worker_id} {name}",
                dv_line,
            ]
        if wf.is_shiny:
            lines.append(f"{SHINY_CHAR}SHINY!")
        box = render_textbox(lines, width_tiles=GB_SCREEN_TILES_W)
        return box.resize((box.width * SCALE, box.height * SCALE), resample=0)
