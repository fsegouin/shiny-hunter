'use client';

import { useEffect, useRef } from 'react';
import { renderTextbox, GB_SCREEN_TILES_W, SHINY_CHAR } from '@/lib/gbfont';

const GB_W = 160;
const GB_H = 144;
const SCALE = 2;
const CELL_W = GB_W * SCALE;
const CELL_H = GB_H * SCALE;

export interface AttemptResult {
  workerId: number;
  attempt: number;
  delay: number;
  speciesName: string;
  dvs: { atk: number; def: number; spd: number; spc: number; hp: number };
  shiny: boolean;
  pixels: Uint8Array;
}

interface MonitorGridProps {
  attempts: AttemptResult[];
}

function pad(n: number, width: number): string {
  return String(n).padStart(width, ' ');
}

function buildLines(a: AttemptResult): string[] {
  const name = a.speciesName.toUpperCase();
  const lines = [
    `W${a.workerId} ${name}`,
    `ATK ${pad(a.dvs.atk, 2)} DEF ${pad(a.dvs.def, 2)}`,
    `SPD ${pad(a.dvs.spd, 2)} SPC ${pad(a.dvs.spc, 2)} HP${pad(a.dvs.hp, 2)}`,
  ];
  if (a.shiny) lines.push(`${SHINY_CHAR}SHINY!`);
  return lines;
}

function MonitorCell({ attempt }: { attempt: AttemptResult }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let cancelled = false;

    (async () => {
      // 1. Draw the framebuffer at native 160x144 then scale up via canvas.
      const off = document.createElement('canvas');
      off.width = GB_W;
      off.height = GB_H;
      const offCtx = off.getContext('2d');
      if (!offCtx) return;
      const imageData = offCtx.createImageData(GB_W, GB_H);
      const dst = imageData.data;
      const src = attempt.pixels;
      for (let i = 0; i < GB_W * GB_H; i++) {
        const s = i * 3;
        const d = i * 4;
        dst[d] = src[s];
        dst[d + 1] = src[s + 1];
        dst[d + 2] = src[s + 2];
        dst[d + 3] = 255;
      }
      offCtx.putImageData(imageData, 0, 0);

      ctx.imageSmoothingEnabled = false;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(off, 0, 0, CELL_W, CELL_H);

      // 2. Render textbox and overlay at top-left, same scale as the screen.
      const textbox = await renderTextbox(buildLines(attempt), GB_SCREEN_TILES_W);
      if (cancelled) return;
      ctx.drawImage(textbox, 0, 0, textbox.width * SCALE, textbox.height * SCALE);
    })();

    return () => {
      cancelled = true;
    };
  }, [attempt]);

  return (
    <canvas
      ref={canvasRef}
      className={`monitor-cell${attempt.shiny ? ' monitor-cell-shiny' : ''}`}
      width={CELL_W}
      height={CELL_H}
    />
  );
}

export default function MonitorGrid({ attempts }: MonitorGridProps) {
  // Cap at 2 rows so every worker is visible at once. For very small worker
  // counts we still want at least 2 columns to avoid an awkwardly tall stack.
  const cols = Math.max(2, Math.ceil(attempts.length / 2));
  return (
    <div className="monitor-grid-wrap">
      <div
        className="monitor-grid"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {attempts.map((a) => (
          <MonitorCell key={a.workerId} attempt={a} />
        ))}
      </div>
    </div>
  );
}
