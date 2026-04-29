"""Pygame-based monitor grid for parallel shiny hunting."""
from __future__ import annotations

import math

import numpy as np

from . import pokemon
from .workers import WorkerFrame

GB_W, GB_H = 160, 144
SCALE = 2
CELL_W = GB_W * SCALE
CELL_H = GB_H * SCALE
BAR_H = 28
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
        import pygame
        self._pg = pygame
        pygame.init()
        pygame.display.set_caption("shiny-hunter monitor")

        self.num_workers = num_workers
        self.cols, self.rows = grid_size(num_workers)
        self.cell_w = CELL_W + BORDER * 2
        self.cell_h = CELL_H + BAR_H + BORDER * 2
        win_w = self.cols * self.cell_w
        win_h = self.rows * self.cell_h
        self._screen = pygame.display.set_mode((win_w, win_h))
        self._font = pygame.font.SysFont("monospace", 13)
        self._clock = pygame.time.Clock()
        self._frames: dict[int, WorkerFrame] = {}

    def update(self, frame: WorkerFrame) -> None:
        update_frames(self._frames, frame)

    def render(self) -> bool:
        """Draw the grid. Returns False if the user closed the window."""
        pg = self._pg
        for event in pg.event.get():
            if event.type == pg.QUIT:
                return False

        self._screen.fill(BG_COLOR)

        for worker_id in range(self.num_workers):
            col = worker_id % self.cols
            row = worker_id // self.cols
            x = col * self.cell_w
            y = row * self.cell_h

            wf = self._frames.get(worker_id)
            if wf is not None:
                if wf.is_shiny:
                    pg.draw.rect(self._screen, SHINY_BORDER_COLOR,
                                 (x, y, self.cell_w, self.cell_h), BORDER)

                surf = pg.surfarray.make_surface(
                    np.transpose(wf.screen, (1, 0, 2))
                )
                surf = pg.transform.scale(surf, (CELL_W, CELL_H))
                self._screen.blit(surf, (x + BORDER, y + BORDER))

                label = self._label(wf)
                color = SHINY_TEXT_COLOR if wf.is_shiny else TEXT_COLOR
                text_surf = self._font.render(label, True, color)
                self._screen.blit(text_surf, (x + BORDER + 4, y + BORDER + CELL_H + 4))
            else:
                label = f"Worker {worker_id} | waiting..."
                text_surf = self._font.render(label, True, TEXT_COLOR)
                self._screen.blit(text_surf, (x + BORDER + 4, y + BORDER + CELL_H + 4))

        pg.display.flip()
        self._clock.tick(15)
        return True

    def close(self) -> None:
        self._pg.quit()

    @staticmethod
    def _label(wf: WorkerFrame) -> str:
        name = pokemon.species_name(wf.species)
        a, d, s, c = wf.dvs
        shiny = "YES" if wf.is_shiny else "no"
        return f"W{wf.worker_id} | {name} | A={a} D={d} S={s} C={c} | Shiny: {shiny}"
